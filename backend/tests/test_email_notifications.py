"""Tests for email notifications + tracking: dossier pronto, consulto reminders, admin email log."""
import os
import time
import uuid
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pathlib import Path
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8000").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
PATIENT_EMAIL = os.environ.get("TEST_PATIENT_EMAIL", "")
PATIENT_PASSWORD = os.environ.get("TEST_PATIENT_PASSWORD", "")
CRON_SECRET = os.environ.get("WEBHOOK_CRON_SECRET", "")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


def session_for(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return s


class TestEmailTracking:
    def test_dossier_ready_email_logged(self):
        patient = session_for(PATIENT_EMAIL, PATIENT_PASSWORD)
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST dossier email", "patient_name": "Mario Rossi"}, timeout=15)
        assert r.status_code == 200, r.text
        dossier_id = r.json()["dossier_id"]
        admin = session_for(ADMIN_EMAIL, ADMIN_PASSWORD)
        try:
            r = admin.post(f"{BASE_URL}/api/dossiers/{dossier_id}/summary-file",
                           files={"file": ("riassunto.pdf", b"%PDF-1.4 test", "application/pdf")}, timeout=30)
            assert r.status_code == 200, r.text
            time.sleep(1)
            entry = db.email_log.find_one(
                {"template": "dossier_pronto", "to": PATIENT_EMAIL},
                sort=[("created_at", -1)])
            assert entry is not None, "Email dossier_pronto non tracciata"
            assert entry["status"] in ("inviata", "fallita")
        finally:
            admin.delete(f"{BASE_URL}/api/dossiers/{dossier_id}", timeout=15)
            db.email_log.delete_many({"template": "dossier_pronto", "to": PATIENT_EMAIL})

    def test_admin_emails_requires_admin(self):
        patient = session_for(PATIENT_EMAIL, PATIENT_PASSWORD)
        r = patient.get(f"{BASE_URL}/api/admin/emails", timeout=10)
        assert r.status_code == 403
        admin = session_for(ADMIN_EMAIL, ADMIN_PASSWORD)
        r = admin.get(f"{BASE_URL}/api/admin/emails", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestConsultReminderCron:
    def test_cron_requires_secret(self):
        r = requests.post(f"{BASE_URL}/api/cron/consult-reminders", json={}, timeout=10)
        assert r.status_code == 401
        r = requests.post(f"{BASE_URL}/api/cron/consult-reminders", json={},
                          headers={"Authorization": "Bearer sbagliato"}, timeout=10)
        assert r.status_code == 401

    def test_cron_sends_reminder_and_marks_slot(self):
        assert CRON_SECRET, "WEBHOOK_CRON_SECRET mancante in .env"
        patient = session_for(PATIENT_EMAIL, PATIENT_PASSWORD)
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST dossier reminder", "patient_name": "Mario Rossi"}, timeout=15)
        dossier_id = r.json()["dossier_id"]
        slot_id = f"slot_{uuid.uuid4().hex[:12]}"
        dt = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        db.slots.insert_one({
            "slot_id": slot_id, "datetime": dt, "meet_link": "https://meet.google.com/test-rem",
            "status": "booked", "booked_by": "test", "dossier_id": dossier_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()})
        run_id = f"test_run_{uuid.uuid4().hex[:12]}"
        admin = session_for(ADMIN_EMAIL, ADMIN_PASSWORD)
        try:
            r = requests.post(f"{BASE_URL}/api/cron/consult-reminders",
                              json={"event": "schedule.triggered", "run_id": run_id, "data": None},
                              headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=10)
            assert r.status_code == 200, r.text
            # duplicate run_id -> no double work
            r2 = requests.post(f"{BASE_URL}/api/cron/consult-reminders",
                               json={"event": "schedule.triggered", "run_id": run_id, "data": None},
                               headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=10)
            assert r2.status_code == 200 and r2.json().get("duplicate") is True
            # wait for background task
            marked = False
            for _ in range(15):
                if db.slots.find_one({"slot_id": slot_id}).get("reminder_sent"):
                    marked = True
                    break
                time.sleep(1)
            assert marked, "Slot non marcato come reminder_sent"
            entry = db.email_log.find_one({"template": "consulto_promemoria", "to": PATIENT_EMAIL},
                                          sort=[("created_at", -1)])
            assert entry is not None, "Promemoria non tracciato nel registro email"
        finally:
            db.slots.delete_one({"slot_id": slot_id})
            db.cron_runs.delete_many({"run_id": run_id})
            db.email_log.delete_many({"template": "consulto_promemoria", "to": PATIENT_EMAIL})
            admin.delete(f"{BASE_URL}/api/dossiers/{dossier_id}", timeout=15)

    def test_cron_ignores_far_slots(self):
        """Slot oltre le 24h non devono ricevere promemoria."""
        assert CRON_SECRET
        slot_id = f"slot_{uuid.uuid4().hex[:12]}"
        dt = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
        db.slots.insert_one({
            "slot_id": slot_id, "datetime": dt, "meet_link": "",
            "status": "booked", "booked_by": "test", "dossier_id": "none",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()})
        run_id = f"test_run_{uuid.uuid4().hex[:12]}"
        try:
            r = requests.post(f"{BASE_URL}/api/cron/consult-reminders",
                              json={"event": "schedule.triggered", "run_id": run_id, "data": None},
                              headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=10)
            assert r.status_code == 200
            time.sleep(3)
            assert not db.slots.find_one({"slot_id": slot_id}).get("reminder_sent")
        finally:
            db.slots.delete_one({"slot_id": slot_id})
            db.cron_runs.delete_many({"run_id": run_id})


class TestEmailExport:
    def test_export_csv_admin(self):
        admin = session_for(ADMIN_EMAIL, ADMIN_PASSWORD)
        r = admin.get(f"{BASE_URL}/api/admin/emails/export", timeout=15)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("Content-Type", "")
        assert "destinatario" in r.text

    def test_export_csv_patient_403(self):
        patient = session_for(PATIENT_EMAIL, PATIENT_PASSWORD)
        r = patient.get(f"{BASE_URL}/api/admin/emails/export", timeout=10)
        assert r.status_code == 403


class TestSlotMeetLinkEmail:
    def _make_booked_slot(self):
        patient = session_for(PATIENT_EMAIL, PATIENT_PASSWORD)
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST dossier meet link", "patient_name": "Mario Rossi"}, timeout=15)
        assert r.status_code == 200, r.text
        dossier_id = r.json()["dossier_id"]
        slot_id = f"slot_{uuid.uuid4().hex[:12]}"
        db.slots.insert_one({
            "slot_id": slot_id,
            "datetime": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "meet_link": "", "status": "booked", "booked_by": "test",
            "dossier_id": dossier_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()})
        return dossier_id, slot_id

    def test_meet_link_on_booked_slot_sends_confirmation(self):
        """Aggiungendo il link Meet a uno slot prenotato parte la mail di conferma al paziente."""
        admin = session_for(ADMIN_EMAIL, ADMIN_PASSWORD)
        dossier_id, slot_id = self._make_booked_slot()
        try:
            r = admin.put(f"{BASE_URL}/api/slots/{slot_id}",
                          json={"meet_link": "https://meet.google.com/abc-defg-hij"}, timeout=15)
            assert r.status_code == 200, r.text
            assert r.json()["meet_link"] == "https://meet.google.com/abc-defg-hij"
            entry = db.email_log.find_one({"template": "consulto_conferma", "to": PATIENT_EMAIL},
                                          sort=[("created_at", -1)])
            assert entry is not None, "Conferma con link Meet non tracciata"
        finally:
            db.slots.delete_one({"slot_id": slot_id})
            db.email_log.delete_many({"template": "consulto_conferma", "to": PATIENT_EMAIL})
            admin.delete(f"{BASE_URL}/api/dossiers/{dossier_id}", timeout=15)

    def test_meet_link_on_available_slot_no_email(self):
        """Slot non prenotato: nessuna email al salvataggio del link."""
        admin = session_for(ADMIN_EMAIL, ADMIN_PASSWORD)
        slot_id = f"slot_{uuid.uuid4().hex[:12]}"
        db.slots.insert_one({
            "slot_id": slot_id,
            "datetime": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "meet_link": "", "status": "available", "booked_by": None, "dossier_id": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()})
        try:
            before = db.email_log.count_documents({"template": "consulto_conferma"})
            r = admin.put(f"{BASE_URL}/api/slots/{slot_id}",
                          json={"meet_link": "https://meet.google.com/xyz-abcd-efg"}, timeout=15)
            assert r.status_code == 200
            assert db.email_log.count_documents({"template": "consulto_conferma"}) == before
        finally:
            db.slots.delete_one({"slot_id": slot_id})

    def test_patient_cannot_update_slot(self):
        patient = session_for(PATIENT_EMAIL, PATIENT_PASSWORD)
        r = patient.put(f"{BASE_URL}/api/slots/slot_inesistente",
                        json={"meet_link": "https://meet.google.com/x"}, timeout=10)
        assert r.status_code == 403


class TestConsentsDelete:
    def test_patient_cannot_delete_consents(self):
        patient = session_for(PATIENT_EMAIL, PATIENT_PASSWORD)
        r = patient.post(f"{BASE_URL}/api/admin/consents/delete", json={"items": []}, timeout=10)
        assert r.status_code == 403

    def test_admin_deletes_selected_consents(self):
        email = f"test.cons.{uuid.uuid4().hex[:8]}@test.it"
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "name": "TEST Cons", "email": email, "password": "TestSicuro2026!",
            "consent_privacy": True, "consent_health_data": True, "consent_declaration": True},
            timeout=15)
        assert r.status_code == 200, r.text
        consent = db.consents.find_one({"email": email})
        assert consent is not None
        admin = session_for(ADMIN_EMAIL, ADMIN_PASSWORD)
        try:
            r = admin.post(f"{BASE_URL}/api/admin/consents/delete",
                           json={"items": [{"user_id": consent["user_id"],
                                            "created_at": consent["created_at"]}]}, timeout=15)
            assert r.status_code == 200, r.text
            assert r.json()["deleted"] == 1
            assert db.consents.find_one({"email": email}) is None
        finally:
            db.users.delete_many({"email": email})
            db.consents.delete_many({"email": email})
