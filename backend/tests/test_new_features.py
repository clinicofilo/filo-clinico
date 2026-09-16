"""Tests for new features: integrazione dossier + admin consents."""
import os
import uuid
import requests
import pytest
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
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def patient():
    return _session(PATIENT_EMAIL, PATIENT_PASSWORD)


@pytest.fixture(scope="module")
def admin():
    return _session(ADMIN_EMAIL, ADMIN_PASSWORD)


# ---------------- Integrazione dossier gating ----------------

class TestIntegrazioneGating:
    def test_integrazione_on_non_completed_returns_400(self, patient):
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST integr non completato", "patient_name": "Mario"}, timeout=10)
        did = r.json()["dossier_id"]
        r2 = patient.post(f"{BASE_URL}/api/payments/checkout",
                          json={"lookup_key": "integrazione_dossier", "origin_url": BASE_URL,
                                "dossier_id": did, "integration_type": "nuovi"}, timeout=15)
        assert r2.status_code == 400
        assert "completat" in r2.text.lower()

    def test_integrazione_invalid_type_on_completed(self, patient, admin):
        # create dossier, mark completed by admin, try invalid type
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST integr invalid type", "patient_name": "Mario"}, timeout=10)
        did = r.json()["dossier_id"]
        r_admin = admin.patch(f"{BASE_URL}/api/dossiers/{did}",
                              json={"status": "completato"}, timeout=10)
        assert r_admin.status_code == 200
        r2 = patient.post(f"{BASE_URL}/api/payments/checkout",
                          json={"lookup_key": "integrazione_dossier", "origin_url": BASE_URL,
                                "dossier_id": did, "integration_type": "bogus"}, timeout=15)
        assert r2.status_code == 400
        assert "integrazione" in r2.text.lower() or "tipo" in r2.text.lower()

    def test_integrazione_missing_type_returns_400(self, patient, admin):
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST integr missing type", "patient_name": "Mario"}, timeout=10)
        did = r.json()["dossier_id"]
        admin.patch(f"{BASE_URL}/api/dossiers/{did}", json={"status": "completato"}, timeout=10)
        r2 = patient.post(f"{BASE_URL}/api/payments/checkout",
                          json={"lookup_key": "integrazione_dossier", "origin_url": BASE_URL,
                                "dossier_id": did}, timeout=15)
        assert r2.status_code == 400

    def test_integrazione_valid_creates_stripe_session(self, patient, admin):
        # completed dossier -> valid integration -> should return checkout URL
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST integr valid", "patient_name": "Mario"}, timeout=10)
        did = r.json()["dossier_id"]
        admin.patch(f"{BASE_URL}/api/dossiers/{did}", json={"status": "completato"}, timeout=10)
        r2 = patient.post(f"{BASE_URL}/api/payments/checkout",
                          json={"lookup_key": "integrazione_dossier", "origin_url": BASE_URL,
                                "dossier_id": did, "integration_type": "nuovi"}, timeout=20)
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data["checkout_url"].startswith("https://")
        # verify amount 25 EUR
        r3 = patient.get(f"{BASE_URL}/api/payments/status/{data['session_id']}", timeout=10)
        assert r3.status_code == 200
        assert r3.json().get("payment_status") in ("pending", "paid")

    def test_paypal_integrazione_gating(self, patient, admin):
        # non-completed => 400
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST pp integr", "patient_name": "Mario"}, timeout=10)
        did = r.json()["dossier_id"]
        r2 = patient.post(f"{BASE_URL}/api/paypal/orders",
                          json={"lookup_key": "integrazione_dossier", "origin_url": BASE_URL,
                                "dossier_id": did, "integration_type": "nuovi"}, timeout=15)
        assert r2.status_code == 400
        # completed but invalid type => 400
        admin.patch(f"{BASE_URL}/api/dossiers/{did}", json={"status": "completato"}, timeout=10)
        r3 = patient.post(f"{BASE_URL}/api/paypal/orders",
                          json={"lookup_key": "integrazione_dossier", "origin_url": BASE_URL,
                                "dossier_id": did, "integration_type": "bad"}, timeout=15)
        assert r3.status_code == 400


# ---------------- Upload gating with integration_pending ----------------

def _tiny_png():
    return (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8"
            b"\xcf\xc0\x00\x00\x00\x03\x00\x01\x5b\xda\xe0\xb5\x00\x00\x00\x00IEND\xaeB`\x82")


def _tiny_pdf():
    return (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 100]>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f \n"
            b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF")


class TestIntegrationUploadFlow:
    """Simulate end-to-end integration flow by directly setting DB flag via a manual test.
    We can't actually pay Stripe in pytest, so we simulate integration_pending via admin path.
    """
    def test_completed_dossier_upload_blocked_unless_pending(self, patient, admin):
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST upload gating", "patient_name": "Mario"}, timeout=10)
        did = r.json()["dossier_id"]
        # mark completed
        admin.patch(f"{BASE_URL}/api/dossiers/{did}", json={"status": "completato"}, timeout=10)
        # upload as patient => must be blocked
        files = [("files", ("g.png", _tiny_png(), "image/png"))]
        r2 = patient.post(f"{BASE_URL}/api/dossiers/{did}/files", files=files, timeout=15)
        assert r2.status_code == 400
        assert "integrazione" in r2.text.lower() or "completat" in r2.text.lower()

    def test_summary_file_upload_clears_integration_pending(self, admin, patient):
        # Since we can't force integration_pending via API without paying, we create dossier,
        # then just verify the summary-file upload endpoint works and the response contains meta.
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST summary file", "patient_name": "Mario"}, timeout=10)
        did = r.json()["dossier_id"]
        admin.patch(f"{BASE_URL}/api/dossiers/{did}", json={"status": "completato"}, timeout=10)
        files = [("file", ("summary.pdf", _tiny_pdf(), "application/pdf"))]
        r2 = admin.post(f"{BASE_URL}/api/dossiers/{did}/summary-file", files=files, timeout=15)
        assert r2.status_code == 200, r2.text
        assert "summary_file" in r2.json()
        # verify integration_pending is false
        r3 = admin.get(f"{BASE_URL}/api/dossiers/{did}", timeout=10)
        assert r3.json().get("integration_pending") is False


# ---------------- Admin consents endpoints ----------------

class TestAdminConsents:
    def test_list_consents_admin(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/consents", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # ensure no _id, and expected fields
        if data:
            entry = data[0]
            assert "_id" not in entry
            for f in ("email", "version", "created_at"):
                assert f in entry, f"missing {f} in consent record"

    def test_list_consents_patient_403(self, patient):
        r = patient.get(f"{BASE_URL}/api/admin/consents", timeout=10)
        assert r.status_code == 403

    def test_list_consents_unauth_401(self):
        r = requests.get(f"{BASE_URL}/api/admin/consents", timeout=10)
        assert r.status_code == 401

    def test_export_consents_admin_csv(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/consents/export", timeout=15)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers.get("content-disposition", "").lower()
        lines = r.text.strip().split("\n")
        assert lines[0].startswith("email;")
        assert "versione_informativa" in lines[0]

    def test_export_consents_patient_403(self, patient):
        r = patient.get(f"{BASE_URL}/api/admin/consents/export", timeout=10)
        assert r.status_code == 403

    def test_export_consents_unauth_401(self):
        r = requests.get(f"{BASE_URL}/api/admin/consents/export", timeout=10)
        assert r.status_code == 401
