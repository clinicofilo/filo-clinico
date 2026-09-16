"""Backend tests: Google Drive OAuth graceful error handling + auth/dossier regression."""
import os
import pytest
import requests
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8000").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
PATIENT_EMAIL = os.environ.get("TEST_PATIENT_EMAIL", "")
PATIENT_PASSWORD = os.environ.get("TEST_PATIENT_PASSWORD", "")


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def patient_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": PATIENT_EMAIL, "password": PATIENT_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Patient login failed: {r.status_code} {r.text}"
    return s


# ---------------- auth regression ----------------
class TestAuthRegression:
    def test_admin_login(self, admin_session):
        r = admin_session.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("email") == ADMIN_EMAIL
        assert data.get("role") == "admin"

    def test_patient_login(self, patient_session):
        r = patient_session.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("email") == PATIENT_EMAIL
        assert data.get("role") == "patient"

    def test_health(self):
        r = requests.get(f"{API}/health", timeout=15)
        assert r.status_code == 200

    def test_dossiers_with_patient(self, patient_session):
        r = patient_session.get(f"{API}/dossiers", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------- Google Drive OAuth ----------------
class TestDriveOAuth:
    def test_drive_connect_returns_auth_url(self, admin_session):
        r = admin_session.get(f"{API}/drive/connect", timeout=15)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "authorization_url" in data
        url = data["authorization_url"]
        assert url.startswith("https://accounts.google.com/o/oauth2/auth")
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        # client_id must be present and non-empty
        assert "client_id" in qs and qs["client_id"][0]
        # redirect_uri must be present
        assert "redirect_uri" in qs and qs["redirect_uri"][0]
        # scope must include drive.file
        assert "scope" in qs
        assert "drive.file" in qs["scope"][0]
        # PKCE disabled: no code_challenge param
        assert "code_challenge" not in qs, f"code_challenge should not be present (PKCE disabled): {qs.get('code_challenge')}"
        # access_type=offline required for refresh tokens
        assert qs.get("access_type", [""])[0] == "offline", f"access_type must be offline: {qs.get('access_type')}"

    def test_drive_status_admin(self, admin_session):
        r = admin_session.get(f"{API}/drive/status", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("configured") is True
        assert data.get("connected") is True, f"Drive should be connected after user consent: {data}"

    def test_callback_with_error_redirects_gracefully(self):
        # Do NOT follow redirects; ensure 3xx redirect to /admin?drive=error, not 500
        r = requests.get(f"{API}/drive/callback",
                         params={"error": "access_denied", "state": "test"},
                         allow_redirects=False, timeout=15)
        assert r.status_code in (302, 307), f"Expected redirect, got {r.status_code}: {r.text[:300]}"
        loc = r.headers.get("location", "")
        assert "/admin" in loc and "drive=error" in loc, f"Unexpected redirect: {loc}"

    def test_callback_with_invalid_code_redirects_gracefully(self):
        r = requests.get(f"{API}/drive/callback",
                         params={"code": "invalid_fake_code", "state": "test"},
                         allow_redirects=False, timeout=30)
        assert r.status_code in (302, 307), f"Expected redirect, got {r.status_code}: {r.text[:300]}"
        loc = r.headers.get("location", "")
        assert "/admin" in loc and "drive=error" in loc, f"Unexpected redirect: {loc}"

    def test_callback_no_params_redirects_gracefully(self):
        r = requests.get(f"{API}/drive/callback", allow_redirects=False, timeout=15)
        assert r.status_code in (302, 307)
        loc = r.headers.get("location", "")
        assert "drive=error" in loc



# ---------------- Drive upload success path (patient) ----------------
@pytest.fixture(scope="class")
def drive_dossier_id(request):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": PATIENT_EMAIL, "password": PATIENT_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    d = s.post(f"{API}/dossiers", json={"title": "TEST drive upload", "patient_name": "Mario Rossi"}, timeout=15)
    assert d.status_code == 200, d.text
    did = d.json()["dossier_id"]
    q = s.post(f"{API}/dossiers/{did}/questionnaire-done", timeout=15)
    assert q.status_code == 200, q.text
    return did

# 1x1 PNG bytes
_PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
    b"\xc0\x00\x00\x00\x03\x00\x01\x5c\xcd\xff\x69\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestDriveUploadSuccess:
    def test_patient_upload_creates_drive_file(self, patient_session, drive_dossier_id):
        files = {"files": ("referto_prova_test.png", _PNG_1x1, "image/png")}
        r = patient_session.post(
            f"{API}/dossiers/{drive_dossier_id}/files",
            files=files,
            timeout=60,
        )
        assert r.status_code in (200, 201), f"Upload failed: {r.status_code} {r.text[:500]}"
        data = r.json()
        uploaded = None
        if isinstance(data, dict) and "files" in data:
            for f in reversed(data["files"]):
                name = f.get("filename") or f.get("original_name") or ""
                if name.startswith("referto_prova_test"):
                    uploaded = f
                    break
            if uploaded is None and data["files"]:
                uploaded = data["files"][-1]
        elif isinstance(data, list) and data:
            uploaded = data[-1]
        elif isinstance(data, dict) and ("file_id" in data or "id" in data):
            uploaded = data
        assert uploaded is not None, f"Could not find uploaded file entry: {data}"
        assert uploaded.get("drive_file_id"), f"drive_file_id must be non-null: {uploaded}"
        pytest.uploaded_file_id = uploaded.get("file_id") or uploaded.get("id")
        assert pytest.uploaded_file_id, f"No file_id in entry: {uploaded}"

    def test_patient_download_uploaded_file(self, patient_session, drive_dossier_id):
        file_id = getattr(pytest, "uploaded_file_id", None)
        if not file_id:
            pytest.skip("Upload test did not run/succeed")
        r = patient_session.get(
            f"{API}/dossiers/{drive_dossier_id}/files/{file_id}",
            timeout=30,
            allow_redirects=True,
        )
        assert r.status_code == 200, f"Download failed: {r.status_code} {r.text[:300]}"
        assert len(r.content) > 0
