"""Tests for password reset feature (forgot-password / reset-password) + recovery_email + password rules."""
import os
import time
import uuid
import requests
import pytest
from dotenv import load_dotenv
from pathlib import Path
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8000").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
PATIENT_EMAIL = os.environ.get("TEST_PATIENT_EMAIL", "")
PATIENT_PASSWORD = os.environ.get("TEST_PATIENT_PASSWORD", "")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


# ---------- Sanity / regression ----------
def test_health():
    r = requests.get(f"{BASE_URL}/api/health", timeout=10)
    assert r.status_code == 200


def test_admin_login():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("role") == "admin"


def test_patient_login():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": PATIENT_EMAIL, "password": PATIENT_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text


def test_admin_dossiers():
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login",
           json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    r = s.get(f"{BASE_URL}/api/dossiers", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_patient_dossiers():
    s = requests.Session()
    s.post(f"{BASE_URL}/api/auth/login",
           json={"email": PATIENT_EMAIL, "password": PATIENT_PASSWORD}, timeout=15)
    r = s.get(f"{BASE_URL}/api/dossiers", timeout=15)
    assert r.status_code == 200


# ---------- Forgot-password ----------
class TestForgotPassword:
    def test_forgot_unknown_email_returns_200_no_leak(self):
        fake = f"test.reset.nonexistent.{uuid.uuid4().hex[:8]}@test.it"
        r = requests.post(f"{BASE_URL}/api/auth/forgot-password",
                          json={"email": fake}, timeout=15)
        assert r.status_code == 200
        # verify no token created in DB
        rec = db.password_resets.find_one({"email": fake})
        assert rec is None, "Token should NOT be created for unknown email"

    def test_forgot_invalid_email_format_422(self):
        r = requests.post(f"{BASE_URL}/api/auth/forgot-password",
                          json={"email": "not-an-email"}, timeout=10)
        assert r.status_code == 422

    def test_forgot_undeliverable_real_user_should_return_200(self):
        """SECURITY: forgot-password must ALWAYS return 200 (no account leak) even if email delivery fails.
        Currently returns 502 when Resend rejects the recipient as undeliverable — this leaks that the
        email is on a bogus domain and differs from the response for unknown emails."""
        db.login_attempts.delete_many({"identifier": {"$regex": "^forgot:"}})
        r = requests.post(f"{BASE_URL}/api/auth/forgot-password",
                          json={"email": PATIENT_EMAIL}, timeout=45)
        # Ideally 200; documenting current behavior
        assert r.status_code == 200, (
            f"Expected 200 (no leak) but got {r.status_code}. "
            f"Email delivery failure should be swallowed to avoid leaking account state.")


# ---------- Reset-password ----------
class TestResetPassword:
    def test_reset_invalid_token_400(self):
        r = requests.post(f"{BASE_URL}/api/auth/reset-password",
                          json={"token": "invalidtoken" + uuid.uuid4().hex,
                                "password": "ValidPass2026!"}, timeout=10)
        assert r.status_code == 400
        assert "non valido" in r.text.lower() or "invalid" in r.text.lower()

    def test_reset_expired_token_400(self):
        """Insert expired token directly, verify rejection."""
        token = "expired_" + uuid.uuid4().hex
        db.password_resets.insert_one({
            "token": token, "email": "mario.rossi@test.it",
            "user_id": "user_expired_test",
            "expires_at": "2020-01-01T00:00:00+00:00",
            "used": False, "created_at": "2020-01-01T00:00:00+00:00"})
        try:
            r = requests.post(f"{BASE_URL}/api/auth/reset-password",
                              json={"token": token, "password": "ValidPass2026!"}, timeout=10)
            assert r.status_code == 400
            assert "scad" in r.text.lower()
        finally:
            db.password_resets.delete_one({"token": token})

    def test_reset_used_token_400(self):
        """Insert used token, verify rejection."""
        token = "used_" + uuid.uuid4().hex
        db.password_resets.insert_one({
            "token": token, "email": "mario.rossi@test.it",
            "user_id": "user_used_test",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "used": True, "created_at": "2099-01-01T00:00:00+00:00"})
        try:
            r = requests.post(f"{BASE_URL}/api/auth/reset-password",
                              json={"token": token, "password": "ValidPass2026!"}, timeout=10)
            assert r.status_code == 400
        finally:
            db.password_resets.delete_one({"token": token})

    def test_reset_full_flow_temp_user(self):
        """Full flow su utente temporaneo: weak pwd rifiutata, reset valido, token monouso.
        NON usare il paziente condiviso: il reset incrementa token_version e invaliderebbe
        le sessioni degli altri test in parallelo."""
        email = f"test.flow.{uuid.uuid4().hex[:8]}@test.it"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json={"name": "TEST Flow", "email": email, "password": "TestSicuro2026!",
                                "consent_privacy": True, "consent_health_data": True,
                                "consent_declaration": True}, timeout=15)
        assert r.status_code == 200, r.text
        user = db.users.find_one({"email": email})
        token = "flowtest_" + uuid.uuid4().hex
        from datetime import datetime, timezone, timedelta
        db.password_resets.insert_one({
            "token": token, "email": email, "user_id": user["user_id"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            "used": False, "created_at": datetime.now(timezone.utc).isoformat()})
        new_pwd = "TempReset2026!"
        try:
            # reset con password debole -> 400
            r_weak = requests.post(f"{BASE_URL}/api/auth/reset-password",
                                   json={"token": token, "password": "weak1!"}, timeout=10)
            assert r_weak.status_code == 400
            # reset con password valida
            r_ok = requests.post(f"{BASE_URL}/api/auth/reset-password",
                                 json={"token": token, "password": new_pwd}, timeout=10)
            assert r_ok.status_code == 200, r_ok.text
            # login con nuova password
            r_login = requests.post(f"{BASE_URL}/api/auth/login",
                                    json={"email": email, "password": new_pwd}, timeout=15)
            assert r_login.status_code == 200
            # riuso token -> 400
            r_reuse = requests.post(f"{BASE_URL}/api/auth/reset-password",
                                    json={"token": token, "password": "AnotherPass2026!"}, timeout=10)
            assert r_reuse.status_code == 400
        finally:
            db.users.delete_many({"email": email})
            db.consents.delete_many({"email": email})
            db.password_resets.delete_many({"email": email})


# ---------- Password strength in register ----------
class TestPasswordStrengthRegister:
    def _payload(self, email, password, recovery=None):
        p = {"name": "TEST User", "email": email, "password": password,
             "consent_privacy": True, "consent_health_data": True, "consent_declaration": True}
        if recovery is not None:
            p["recovery_email"] = recovery
        return p

    def test_register_weak_pwd_no_special(self):
        email = f"test.pwd.{uuid.uuid4().hex[:8]}@test.it"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json=self._payload(email, "abcdefg1"), timeout=10)
        assert r.status_code == 400
        assert "password" in r.text.lower()

    def test_register_weak_pwd_no_digit(self):
        email = f"test.pwd.{uuid.uuid4().hex[:8]}@test.it"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json=self._payload(email, "abcdefgh!"), timeout=10)
        assert r.status_code == 400

    def test_register_weak_pwd_too_few_letters(self):
        email = f"test.pwd.{uuid.uuid4().hex[:8]}@test.it"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json=self._payload(email, "abc12345!"), timeout=10)
        assert r.status_code == 400

    def test_register_strong_pwd_with_recovery(self):
        email = f"test.pwd.{uuid.uuid4().hex[:8]}@test.it"
        recovery = f"backup.{uuid.uuid4().hex[:6]}@test.it"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json=self._payload(email, "TestSicuro2026!", recovery=recovery), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("recovery_email") == recovery
        # cleanup
        db.users.delete_one({"email": email})
        db.consents.delete_many({"email": email})

    def test_register_strong_pwd_no_recovery(self):
        email = f"test.pwd.{uuid.uuid4().hex[:8]}@test.it"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json=self._payload(email, "TestSicuro2026!"), timeout=15)
        assert r.status_code == 200, r.text
        # cleanup
        db.users.delete_one({"email": email})
        db.consents.delete_many({"email": email})

    def test_register_empty_recovery_email_422(self):
        """As noted in the request: register endpoint returns 422 if recovery_email sent as empty string."""
        email = f"test.pwd.{uuid.uuid4().hex[:8]}@test.it"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json=self._payload(email, "TestSicuro2026!", recovery=""), timeout=10)
        assert r.status_code == 422
