"""Backend API tests for FiloClinico."""
import io
import os
import time
import uuid

import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8000").rstrip("/")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
PATIENT_EMAIL = os.environ.get("TEST_PATIENT_EMAIL", "")
PATIENT_PASSWORD = os.environ.get("TEST_PATIENT_PASSWORD", "")


def _session(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def patient():
    return _session(PATIENT_EMAIL, PATIENT_PASSWORD)


@pytest.fixture(scope="session")
def admin():
    return _session(ADMIN_EMAIL, ADMIN_PASSWORD)


# ---------------- Health & Auth ----------------

class TestHealth:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestAuth:
    def test_login_admin_role(self, admin):
        r = admin.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"

    def test_login_patient_role(self, patient):
        r = patient.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == PATIENT_EMAIL
        assert data["role"] == "patient"

    def test_login_wrong_password(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": PATIENT_EMAIL, "password": "wrongpass"}, timeout=10)
        assert r.status_code == 401

    def test_me_unauthenticated(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert r.status_code == 401

    def test_register_new_and_login(self):
        email = f"TEST_user_{uuid.uuid4().hex[:8]}@test.it"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json={"name": "Test", "email": email, "password": "TestSicuro2026!",
                                "consent_privacy": True, "consent_health_data": True,
                                "consent_declaration": True}, timeout=10)
        assert r.status_code == 200
        assert r.json()["email"] == email.lower()
        assert r.json()["role"] == "patient"
        assert "password_hash" not in r.json()

    def test_register_duplicate_email(self):
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json={"name": "Dup", "email": PATIENT_EMAIL, "password": PATIENT_PASSWORD,
                                "consent_privacy": True, "consent_health_data": True,
                                "consent_declaration": True}, timeout=10)
        assert r.status_code == 400

    def test_logout(self, patient):
        # separate session so we don't kill the fixture
        s = _session(PATIENT_EMAIL, PATIENT_PASSWORD)
        r = s.post(f"{BASE_URL}/api/auth/logout", timeout=10)
        assert r.status_code == 200
        r2 = s.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert r2.status_code == 401


# ---------------- Dossier CRUD ----------------

class TestDossier:
    def test_create_and_get_dossier(self, patient):
        payload = {"title": "TEST Dossier", "patient_name": "Mario Rossi",
                   "relationship": "me", "notes": "Test notes"}
        r = patient.post(f"{BASE_URL}/api/dossiers", json=payload, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["title"] == "TEST Dossier"
        assert d["status"] == "bozza"
        assert d["revisione_paid"] is False
        assert "dossier_id" in d
        assert "_id" not in d

        # GET
        r2 = patient.get(f"{BASE_URL}/api/dossiers/{d['dossier_id']}", timeout=10)
        assert r2.status_code == 200
        assert r2.json()["title"] == "TEST Dossier"

    def test_list_dossiers_patient(self, patient):
        r = patient.get(f"{BASE_URL}/api/dossiers", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_dossiers_admin_sees_all(self, admin):
        r = admin.get(f"{BASE_URL}/api/dossiers", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_patient_cannot_patch_dossier(self, patient):
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST x", "patient_name": "Mario"}, timeout=10)
        did = r.json()["dossier_id"]
        r2 = patient.patch(f"{BASE_URL}/api/dossiers/{did}",
                           json={"status": "completato"}, timeout=10)
        assert r2.status_code == 403

    def test_admin_patch_dossier(self, patient, admin):
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST patch", "patient_name": "Mario"}, timeout=10)
        did = r.json()["dossier_id"]
        r2 = admin.patch(f"{BASE_URL}/api/dossiers/{did}",
                         json={"status": "in_lavorazione", "summary_text": "Summary here"}, timeout=10)
        assert r2.status_code == 200
        assert r2.json()["status"] == "in_lavorazione"
        assert r2.json()["summary_text"] == "Summary here"

        # verify persisted via GET
        r3 = admin.get(f"{BASE_URL}/api/dossiers/{did}", timeout=10)
        assert r3.json()["status"] == "in_lavorazione"

    def test_admin_invalid_status(self, patient, admin):
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST inv", "patient_name": "Mario"}, timeout=10)
        did = r.json()["dossier_id"]
        r2 = admin.patch(f"{BASE_URL}/api/dossiers/{did}",
                         json={"status": "invalido"}, timeout=10)
        assert r2.status_code == 400

    def test_get_dossier_404(self, patient):
        r = patient.get(f"{BASE_URL}/api/dossiers/doss_nonexistent", timeout=10)
        assert r.status_code == 404


# ---------------- File upload ----------------

def _tiny_png():
    # minimal valid 1x1 PNG
    return (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8"
            b"\xcf\xc0\x00\x00\x00\x03\x00\x01\x5b\xda\xe0\xb5\x00\x00\x00\x00IEND\xaeB`\x82")


class TestFiles:
    @pytest.fixture(scope="class")
    def dossier_id(self):
        s = _session(PATIENT_EMAIL, PATIENT_PASSWORD)
        r = s.post(f"{BASE_URL}/api/dossiers",
                   json={"title": "TEST Files", "patient_name": "Mario"}, timeout=10)
        did = r.json()["dossier_id"]
        s.post(f"{BASE_URL}/api/dossiers/{did}/questionnaire-done", timeout=10)
        return s, did

    def test_upload_image(self, dossier_id):
        s, did = dossier_id
        files = [("files", ("test.png", _tiny_png(), "image/png"))]
        r = s.post(f"{BASE_URL}/api/dossiers/{did}/files", files=files, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["files"]) == 1
        assert data["files"][0]["filename"] == "test.png"

        # verify persisted
        r2 = s.get(f"{BASE_URL}/api/dossiers/{did}", timeout=10)
        assert len(r2.json()["files"]) >= 1

    def test_upload_invalid_extension(self, dossier_id):
        s, did = dossier_id
        files = [("files", ("bad.exe", b"data", "application/octet-stream"))]
        r = s.post(f"{BASE_URL}/api/dossiers/{did}/files", files=files, timeout=10)
        assert r.status_code == 400

    def test_get_file(self, dossier_id):
        s, did = dossier_id
        r = s.get(f"{BASE_URL}/api/dossiers/{did}", timeout=10)
        files = r.json()["files"]
        if files:
            fid = files[0]["file_id"]
            r2 = s.get(f"{BASE_URL}/api/dossiers/{did}/files/{fid}", timeout=10)
            assert r2.status_code == 200
            assert r2.headers["content-type"].startswith("image/")

    def test_delete_file(self, dossier_id):
        s, did = dossier_id
        # upload first
        files = [("files", ("del.png", _tiny_png(), "image/png"))]
        r = s.post(f"{BASE_URL}/api/dossiers/{did}/files", files=files, timeout=15)
        fid = r.json()["files"][0]["file_id"]
        r2 = s.delete(f"{BASE_URL}/api/dossiers/{did}/files/{fid}", timeout=10)
        assert r2.status_code == 200
        r3 = s.get(f"{BASE_URL}/api/dossiers/{did}/files/{fid}", timeout=10)
        assert r3.status_code == 404


# ---------------- Payments ----------------

class TestPayments:
    def test_checkout_creates_session(self, patient):
        # create dossier with a file first
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST Pay", "patient_name": "Mario"}, timeout=10)
        did = r.json()["dossier_id"]
        patient.post(f"{BASE_URL}/api/dossiers/{did}/questionnaire-done", timeout=10)
        patient.post(f"{BASE_URL}/api/dossiers/{did}/files",
                     files=[("files", ("p.png", _tiny_png(), "image/png"))], timeout=15)

        r2 = patient.post(f"{BASE_URL}/api/payments/checkout",
                          json={"lookup_key": "revisione_referti",
                                "origin_url": BASE_URL, "dossier_id": did}, timeout=20)
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert "checkout_url" in data
        assert "session_id" in data
        assert data["checkout_url"].startswith("https://")

        # status endpoint
        r3 = patient.get(f"{BASE_URL}/api/payments/status/{data['session_id']}", timeout=10)
        assert r3.status_code == 200
        assert r3.json()["payment_status"] in ("pending", "paid")

    def test_checkout_invalid_lookup(self, patient):
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST inv pay", "patient_name": "Mario"}, timeout=10)
        did = r.json()["dossier_id"]
        r2 = patient.post(f"{BASE_URL}/api/payments/checkout",
                          json={"lookup_key": "invalid_key",
                                "origin_url": BASE_URL, "dossier_id": did}, timeout=10)
        assert r2.status_code == 400

    def test_checkout_consult_requires_slot(self, patient):
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST consult", "patient_name": "Mario"}, timeout=10)
        did = r.json()["dossier_id"]
        r2 = patient.post(f"{BASE_URL}/api/payments/checkout",
                          json={"lookup_key": "consulto_video",
                                "origin_url": BASE_URL, "dossier_id": did}, timeout=10)
        assert r2.status_code == 400


# ---------------- Slots ----------------

class TestSlots:
    def test_admin_create_slot_and_patient_sees(self, admin, patient):
        future = "2027-06-15T10:00:00"
        r = admin.post(f"{BASE_URL}/api/slots",
                       json={"datetime": future, "meet_link": "https://meet.google.com/test-abc"}, timeout=10)
        assert r.status_code == 200
        slot_id = r.json()["slot_id"]
        assert r.json()["status"] == "available"

        r2 = patient.get(f"{BASE_URL}/api/slots", timeout=10)
        assert r2.status_code == 200
        assert any(s["slot_id"] == slot_id for s in r2.json())

        # cleanup
        r3 = admin.delete(f"{BASE_URL}/api/slots/{slot_id}", timeout=10)
        assert r3.status_code == 200

    def test_patient_cannot_create_slot(self, patient):
        r = patient.post(f"{BASE_URL}/api/slots",
                        json={"datetime": "2027-06-15T10:00:00"}, timeout=10)
        assert r.status_code == 403


# ---------------- Drive status ----------------

class TestDrive:
    def test_drive_status_configured_and_connected(self, admin):
        r = admin.get(f"{BASE_URL}/api/drive/status", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["configured"] is True
        assert data["connected"] is True

    def test_drive_connect_returns_authorization_url(self, admin):
        r = admin.get(f"{BASE_URL}/api/drive/connect", timeout=10)
        assert r.status_code == 200
        assert "accounts.google.com" in r.json()["authorization_url"]
