"""Tests for security audit round 2 fixes:
SEC-001 CSV formula injection, SEC-002 register enumeration message,
SEC-003 token revocation on password reset, SEC-004 slot double-booking race."""
import os
import sys
import uuid
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pathlib import Path
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _async import run as run_async

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8000").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
PATIENT_EMAIL = os.environ.get("TEST_PATIENT_EMAIL", "")
PATIENT_PASSWORD = os.environ.get("TEST_PATIENT_PASSWORD", "")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


def session_for(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return s


class TestCSVFormulaInjection:
    def test_user_agent_escaped_in_export(self):
        email = f"test.csv.{uuid.uuid4().hex[:8]}@test.it"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json={"name": "TEST CSV", "email": email, "password": "TestSicuro2026!",
                                "consent_privacy": True, "consent_health_data": True,
                                "consent_declaration": True},
                          headers={"User-Agent": "=HYPERLINK evil"}, timeout=15)
        assert r.status_code == 200, r.text
        admin = session_for(ADMIN_EMAIL, ADMIN_PASSWORD)
        try:
            r = admin.get(f"{BASE_URL}/api/admin/consents/export", timeout=15)
            assert r.status_code == 200
            line = next(l for l in r.text.splitlines() if email in l)
            ua_cell = line.split(";")[-1]
            assert ua_cell.startswith("'"), f"Cella formula non neutralizzata: {ua_cell!r}"
        finally:
            db.users.delete_many({"email": email})
            db.consents.delete_many({"email": email})


class TestRegisterEnumeration:
    def test_duplicate_email_generic_message(self):
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json={"name": "Dup", "email": PATIENT_EMAIL, "password": "TestSicuro2026!",
                                "consent_privacy": True, "consent_health_data": True,
                                "consent_declaration": True}, timeout=15)
        assert r.status_code == 400
        assert "già registrata" not in r.text.lower()


class TestResetRevokesTokens:
    def test_old_token_rejected_after_reset(self):
        """SEC-003: dopo il reset password i token esistenti devono essere invalidati.
        Usa un utente temporaneo per non invalidare le sessioni degli altri test."""
        email = f"test.revoke.{uuid.uuid4().hex[:8]}@test.it"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json={"name": "TEST Revoke", "email": email, "password": "TestSicuro2026!",
                                "consent_privacy": True, "consent_health_data": True,
                                "consent_declaration": True}, timeout=15)
        assert r.status_code == 200, r.text
        try:
            s = session_for(email, "TestSicuro2026!")
            r = s.get(f"{BASE_URL}/api/auth/me", timeout=10)
            assert r.status_code == 200
            user = db.users.find_one({"email": email})
            token = "revoke_" + uuid.uuid4().hex
            db.password_resets.insert_one({
                "token": token, "email": email, "user_id": user["user_id"],
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
                "used": False, "created_at": datetime.now(timezone.utc).isoformat()})
            r = requests.post(f"{BASE_URL}/api/auth/reset-password",
                              json={"token": token, "password": "TempReset2026!"}, timeout=15)
            assert r.status_code == 200, r.text
            # il vecchio access token deve essere rifiutato (token_version incrementata)
            r2 = s.get(f"{BASE_URL}/api/auth/me", timeout=10)
            assert r2.status_code == 401, "Vecchio token ancora valido dopo il reset"
        finally:
            db.users.delete_many({"email": email})
            db.consents.delete_many({"email": email})
            db.password_resets.delete_many({"email": email})


class TestSlotRace:
    def test_fulfil_on_taken_slot_does_not_steal(self):
        """Due pagamenti sullo stesso slot: il secondo non deve sovrascrivere la prenotazione
        né segnare il consulto come pagato."""
        import server
        slot_id = f"slot_{uuid.uuid4().hex[:12]}"
        dossier_id = f"doss_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        db.slots.insert_one({
            "slot_id": slot_id, "datetime": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "meet_link": "", "status": "booked", "booked_by": "primo_paziente",
            "dossier_id": "doss_primo", "created_at": now, "updated_at": now})
        db.dossiers.insert_one({
            "dossier_id": dossier_id, "patient_id": "secondo_paziente",
            "patient_email": "secondo@test.it", "patient_name": "Test Race",
            "title": "TEST race", "status": "pagato", "files": [],
            "consult_paid": False, "created_at": now, "updated_at": now})
        try:
            run_async(server.fulfil_payment({
                "lookup_key": "consulto_video", "slot_id": slot_id,
                "user_id": "secondo_paziente", "dossier_id": dossier_id,
                "session_id": "sess_race_test"}))
            slot = db.slots.find_one({"slot_id": slot_id})
            assert slot["booked_by"] == "primo_paziente", "Slot sovrascritto dal secondo pagamento"
            dossier = db.dossiers.find_one({"dossier_id": dossier_id})
            assert not dossier.get("consult_paid"), "Consulto segnato pagato senza slot"
        finally:
            db.slots.delete_one({"slot_id": slot_id})
            db.dossiers.delete_one({"dossier_id": dossier_id})
