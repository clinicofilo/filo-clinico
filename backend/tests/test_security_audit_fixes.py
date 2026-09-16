"""Security audit fixes verification tests."""
import os
import io
import struct
import zlib
import uuid
import requests
import pytest
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8000").rstrip("/")
API = f"{BASE_URL}/api"

PATIENT = {"email": os.environ.get("TEST_PATIENT_EMAIL", ""), "password": os.environ.get("TEST_PATIENT_PASSWORD", "")}
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", ""), "password": os.environ.get("ADMIN_PASSWORD", "")}


def _min_png_bytes() -> bytes:
    # Minimal valid 1x1 PNG
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def patient_session():
    return _login(**PATIENT)


@pytest.fixture(scope="module")
def admin_session():
    return _login(**ADMIN)


@pytest.fixture(scope="module")
def dossier_id(patient_session, admin_session):
    r = patient_session.post(f"{API}/dossiers",
                             json={"title": "TEST security audit", "patient_name": "Mario Rossi"}, timeout=15)
    assert r.status_code == 200, r.text
    did = r.json()["dossier_id"]
    q = patient_session.post(f"{API}/dossiers/{did}/questionnaire-done", timeout=15)
    assert q.status_code == 200, q.text
    yield did
    admin_session.delete(f"{API}/dossiers/{did}", timeout=15)


# ---------- Health regression ----------
def test_health():
    r = requests.get(f"{API}/health", timeout=10)
    assert r.status_code == 200


# ---------- Admin login regression ----------
def test_admin_login(admin_session):
    r = admin_session.get(f"{API}/auth/me", timeout=10)
    assert r.status_code == 200
    assert r.json().get("role") == "admin"


# ---------- Patient list dossiers regression ----------
def test_patient_can_list_dossiers(patient_session):
    r = patient_session.get(f"{API}/dossiers", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------- XSS FIX: html-content file with .png ext served as attachment ----------
def test_xss_upload_html_as_png(patient_session, dossier_id):
    marker = "INERT-XSS-MARKER-" + uuid.uuid4().hex[:6]
    html_payload = f"<html><body>{marker}<script>alert(1)</script></body></html>".encode()
    files = {"files": ("evil.png", io.BytesIO(html_payload), "text/html")}
    r = patient_session.post(f"{API}/dossiers/{dossier_id}/files", files=files, timeout=30)
    assert r.status_code == 200, r.text
    file_id = r.json()["files"][0]["file_id"]

    g = patient_session.get(f"{API}/dossiers/{dossier_id}/files/{file_id}", timeout=20)
    assert g.status_code == 200
    assert g.headers.get("X-Content-Type-Options", "").lower() == "nosniff"
    cd = g.headers.get("Content-Disposition", "")
    assert "attachment" in cd.lower(), f"Expected attachment CD, got: {cd}"
    ct = g.headers.get("Content-Type", "")
    assert ct.startswith("application/octet-stream"), f"Expected octet-stream, got: {ct}"
    assert "text/html" not in ct.lower()
    assert marker.encode() in g.content

    # cleanup
    patient_session.delete(f"{API}/dossiers/{dossier_id}/files/{file_id}", timeout=10)


# ---------- Legit PNG served inline ----------
def test_legit_png_served_inline(patient_session, dossier_id):
    png = _min_png_bytes()
    files = {"files": ("legit.png", io.BytesIO(png), "image/png")}
    r = patient_session.post(f"{API}/dossiers/{dossier_id}/files", files=files, timeout=30)
    assert r.status_code == 200, r.text
    file_id = r.json()["files"][0]["file_id"]

    g = patient_session.get(f"{API}/dossiers/{dossier_id}/files/{file_id}", timeout=20)
    assert g.status_code == 200
    assert g.headers.get("X-Content-Type-Options", "").lower() == "nosniff"
    ct = g.headers.get("Content-Type", "")
    assert ct.startswith("image/png"), f"Expected image/png, got: {ct}"
    cd = g.headers.get("Content-Disposition", "")
    assert "attachment" not in cd.lower(), f"Should be inline, got CD: {cd}"

    patient_session.delete(f"{API}/dossiers/{dossier_id}/files/{file_id}", timeout=10)


# ---------- PDF served as attachment ----------
def test_pdf_served_as_attachment(patient_session, dossier_id):
    pdf = b"%PDF-1.4\n%test\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    files = {"files": ("doc.pdf", io.BytesIO(pdf), "application/pdf")}
    r = patient_session.post(f"{API}/dossiers/{dossier_id}/files", files=files, timeout=30)
    assert r.status_code == 200, r.text
    file_id = r.json()["files"][0]["file_id"]

    g = patient_session.get(f"{API}/dossiers/{dossier_id}/files/{file_id}", timeout=20)
    assert g.status_code == 200
    assert g.headers.get("X-Content-Type-Options", "").lower() == "nosniff"
    cd = g.headers.get("Content-Disposition", "")
    assert "attachment" in cd.lower(), f"Expected attachment, got: {cd}"
    ct = g.headers.get("Content-Type", "")
    assert ct.startswith("application/octet-stream"), f"Expected octet-stream, got: {ct}"

    patient_session.delete(f"{API}/dossiers/{dossier_id}/files/{file_id}", timeout=10)


# ---------- Admin can view existing image file inline ----------
def test_admin_gallery_image_inline(admin_session, patient_session, dossier_id):
    # Ensure an image exists: upload one as patient
    png = _min_png_bytes()
    files = {"files": ("adminview.png", io.BytesIO(png), "image/png")}
    r = patient_session.post(f"{API}/dossiers/{dossier_id}/files", files=files, timeout=30)
    assert r.status_code == 200
    file_id = r.json()["files"][0]["file_id"]

    g = admin_session.get(f"{API}/dossiers/{dossier_id}/files/{file_id}", timeout=20)
    assert g.status_code == 200
    assert g.headers.get("Content-Type", "").startswith("image/")
    assert g.headers.get("X-Content-Type-Options", "").lower() == "nosniff"
    assert "attachment" not in g.headers.get("Content-Disposition", "").lower()

    patient_session.delete(f"{API}/dossiers/{dossier_id}/files/{file_id}", timeout=10)


# ---------- Payment status auth required ----------
def test_payment_status_requires_auth():
    r = requests.get(f"{API}/payments/status/cs_test_fake_unauth_123", timeout=15)
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_payment_status_ownership(patient_session, admin_session, dossier_id):
    # patient creates a checkout session
    body = {
        "lookup_key": "revisione_referti",
        "dossier_id": dossier_id,
        "origin_url": BASE_URL,
    }
    r = patient_session.post(f"{API}/payments/checkout", json=body, timeout=30)
    assert r.status_code == 200, r.text
    session_id = r.json()["session_id"]

    # Patient can read own
    own = patient_session.get(f"{API}/payments/status/{session_id}", timeout=15)
    assert own.status_code == 200

    # Second patient (create fresh user) should get 403
    other_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    reg = requests.Session()
    rr = reg.post(f"{API}/auth/register", json={
        "email": other_email, "name": "Other Tester", "password": "Password123!",
        "consent_privacy": True, "consent_health_data": True, "consent_declaration": True,
    }, timeout=20)
    assert rr.status_code == 200, rr.text
    other = reg.get(f"{API}/payments/status/{session_id}", timeout=15)
    assert other.status_code == 403, f"Expected 403 for other user, got {other.status_code}: {other.text}"

    # Admin should be allowed
    adm = admin_session.get(f"{API}/payments/status/{session_id}", timeout=15)
    assert adm.status_code == 200


# ---------- PayPal capture binding ----------
def test_paypal_capture_nonexistent_order(patient_session):
    fake = f"NONEXISTENT_{uuid.uuid4().hex}"
    r = patient_session.post(f"{API}/paypal/orders/{fake}/capture", timeout=20)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_paypal_capture_forbidden_for_other_user(patient_session, dossier_id):
    # Seed a fake paypal transaction owned by admin, then attempt capture as patient => 403
    from pymongo import MongoClient
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        # try reading backend env
        try:
            with open("/app/backend/.env") as f:
                for line in f:
                    if line.startswith("MONGO_URL="):
                        mongo_url = line.split("=", 1)[1].strip().strip('"')
                    if line.startswith("DB_NAME="):
                        db_name = line.split("=", 1)[1].strip().strip('"')
        except Exception:
            pytest.skip("no mongo access")
    if not mongo_url or not db_name:
        pytest.skip("no mongo config")

    client = MongoClient(mongo_url)
    db = client[db_name]
    fake_order = f"FAKE_PP_{uuid.uuid4().hex[:10]}"
    db.payment_transactions.insert_one({
        "session_id": fake_order, "provider": "paypal",
        "user_id": "user_other_owner_xyz", "dossier_id": dossier_id,
        "lookup_key": "revisione_referti", "amount": 1.0, "currency": "eur",
        "status": "initiated", "payment_status": "pending",
    })
    try:
        r = patient_session.post(f"{API}/paypal/orders/{fake_order}/capture", timeout=15)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
    finally:
        db.payment_transactions.delete_one({"session_id": fake_order})


# ---------- Password minimum 8 chars ----------
def test_register_short_password_rejected():
    email = f"test_short_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "name": "Short Pwd", "password": "abc123",
        "consent_privacy": True, "consent_health_data": True, "consent_declaration": True,
    }, timeout=15)
    assert r.status_code == 400
    assert "8 caratteri" in r.text or "almeno 8" in r.text.lower()


def test_register_valid_password_ok():
    email = f"test_ok_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "name": "Valid Pwd", "password": "Abcdef12!",
        "consent_privacy": True, "consent_health_data": True, "consent_declaration": True,
    }, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("email") == email
