"""Tests for account deletion: patient self-service (password confirm) + admin delete patient."""
import os
import uuid
import requests
from dotenv import load_dotenv
from pathlib import Path
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8000").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]

PASSWORD = "TestSicuro2026!"


def make_user():
    email = f"test.del.{uuid.uuid4().hex[:8]}@test.it"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": "TEST Delete", "email": email, "password": PASSWORD,
        "consent_privacy": True, "consent_health_data": True, "consent_declaration": True,
    }, timeout=15)
    assert r.status_code == 200, r.text
    return email, r.cookies


def cleanup(email):
    db.users.delete_many({"email": email})
    db.consents.delete_many({"email": email})
    db.dossiers.delete_many({"patient_email": email})


def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return s


class TestSelfDelete:
    def test_wrong_password_401(self):
        email, cookies = make_user()
        try:
            r = requests.post(f"{BASE_URL}/api/auth/delete-account",
                              json={"password": "Sbagliata2026!"}, cookies=cookies, timeout=15)
            assert r.status_code == 401
            assert db.users.find_one({"email": email}) is not None
        finally:
            cleanup(email)

    def test_unauthenticated_401(self):
        r = requests.post(f"{BASE_URL}/api/auth/delete-account",
                          json={"password": PASSWORD}, timeout=10)
        assert r.status_code == 401

    def test_full_self_delete_keeps_consents(self):
        email, cookies = make_user()
        user = db.users.find_one({"email": email})
        # create a dossier
        r = requests.post(f"{BASE_URL}/api/dossiers",
                          json={"title": "Dossier da eliminare", "patient_name": "TEST Delete"},
                          cookies=cookies, timeout=15)
        assert r.status_code == 200, r.text
        dossier_id = r.json()["dossier_id"]
        try:
            r = requests.post(f"{BASE_URL}/api/auth/delete-account",
                              json={"password": PASSWORD}, cookies=cookies, timeout=30)
            assert r.status_code == 200, r.text
            assert db.users.find_one({"email": email}) is None, "user doc should be removed"
            assert db.dossiers.find_one({"dossier_id": dossier_id}) is None, "dossier should be removed"
            assert db.consents.find_one({"email": email}) is not None, "consents must be kept"
            # login must fail now
            r_login = requests.post(f"{BASE_URL}/api/auth/login",
                                    json={"email": email, "password": PASSWORD}, timeout=15)
            assert r_login.status_code == 401
        finally:
            cleanup(email)

    def test_admin_cannot_self_delete(self):
        s = admin_session()
        r = s.post(f"{BASE_URL}/api/auth/delete-account",
                   json={"password": ADMIN_PASSWORD}, timeout=15)
        assert r.status_code == 400


class TestAdminDelete:
    def test_admin_lists_patients(self):
        s = admin_session()
        r = s.get(f"{BASE_URL}/api/admin/patients", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        for p in r.json():
            assert "password_hash" not in p

    def test_patient_cannot_list_patients(self):
        email, cookies = make_user()
        try:
            r = requests.get(f"{BASE_URL}/api/admin/patients", cookies=cookies, timeout=10)
            assert r.status_code == 403
        finally:
            cleanup(email)

    def test_admin_deletes_patient(self):
        email, cookies = make_user()
        user = db.users.find_one({"email": email})
        s = admin_session()
        try:
            r = s.delete(f"{BASE_URL}/api/admin/patients/{user['user_id']}", timeout=30)
            assert r.status_code == 200, r.text
            assert db.users.find_one({"email": email}) is None
        finally:
            cleanup(email)

    def test_admin_delete_unknown_404(self):
        s = admin_session()
        r = s.delete(f"{BASE_URL}/api/admin/patients/user_nonexistent123", timeout=10)
        assert r.status_code == 404

    def test_admin_cannot_delete_admin(self):
        s = admin_session()
        admin = db.users.find_one({"email": ADMIN_EMAIL})
        r = s.delete(f"{BASE_URL}/api/admin/patients/{admin['user_id']}", timeout=10)
        assert r.status_code == 400

    def test_deletion_succeeds_even_if_email_undeliverable(self):
        """Email di conferma è best-effort: dominio test.it non recapitabile, eliminazione ok."""
        email, cookies = make_user()
        try:
            r = requests.post(f"{BASE_URL}/api/auth/delete-account",
                              json={"password": PASSWORD}, cookies=cookies, timeout=45)
            assert r.status_code == 200, r.text
            assert db.users.find_one({"email": email}) is None
        finally:
            cleanup(email)


class TestGoogleAccountDelete:
    """Utenti Google (senza password): conferma con email invece che password."""

    def _make_google_user(self):
        email = f"test.google.{uuid.uuid4().hex[:8]}@test.it"
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        session_token = f"sess_{uuid.uuid4().hex}"
        db.users.insert_one({
            "user_id": user_id, "email": email, "name": "TEST Google",
            "role": "patient", "auth_provider": "google",
            "created_at": "2026-09-15T00:00:00+00:00"})
        db.user_sessions.insert_one({
            "user_id": user_id, "session_token": session_token,
            "expires_at": "2099-01-01T00:00:00+00:00",
            "created_at": "2026-09-15T00:00:00+00:00"})
        return email, user_id, session_token

    def _cleanup(self, email, session_token):
        db.users.delete_many({"email": email})
        db.user_sessions.delete_many({"session_token": session_token})
        db.consents.delete_many({"email": email})

    def test_me_reports_has_password(self):
        email, _, token = self._make_google_user()
        try:
            r = requests.get(f"{BASE_URL}/api/auth/me", cookies={"session_token": token}, timeout=10)
            assert r.status_code == 200
            assert r.json()["has_password"] is False
            assert "password_hash" not in r.json()
        finally:
            self._cleanup(email, token)

    def test_google_user_wrong_email_400(self):
        email, _, token = self._make_google_user()
        try:
            r = requests.post(f"{BASE_URL}/api/auth/delete-account",
                              json={"confirm_email": "altra@test.it"},
                              cookies={"session_token": token}, timeout=15)
            assert r.status_code == 400
            assert db.users.find_one({"email": email}) is not None
        finally:
            self._cleanup(email, token)

    def test_google_user_correct_email_deletes(self):
        email, _, token = self._make_google_user()
        try:
            r = requests.post(f"{BASE_URL}/api/auth/delete-account",
                              json={"confirm_email": email},
                              cookies={"session_token": token}, timeout=30)
            assert r.status_code == 200, r.text
            assert db.users.find_one({"email": email}) is None
        finally:
            self._cleanup(email, token)
