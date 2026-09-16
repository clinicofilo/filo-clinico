"""Tests for integration anamnestic note (25€ integration) + fulfil storing the note."""
import os
import sys
import uuid
import requests
from datetime import datetime, timezone
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


class TestIntegrationNote:
    def _make_dossier(self, completed=True):
        patient = session_for(PATIENT_EMAIL, PATIENT_PASSWORD)
        r = patient.post(f"{BASE_URL}/api/dossiers",
                         json={"title": "TEST nota integrazione", "patient_name": "Mario Rossi"}, timeout=15)
        assert r.status_code == 200, r.text
        dossier_id = r.json()["dossier_id"]
        if completed:
            db.dossiers.update_one({"dossier_id": dossier_id},
                                   {"$set": {"status": "completato"}})
        return patient, dossier_id

    def _cleanup(self, dossier_id):
        admin = session_for(ADMIN_EMAIL, ADMIN_PASSWORD)
        admin.delete(f"{BASE_URL}/api/dossiers/{dossier_id}", timeout=15)

    def test_note_requires_completed_dossier(self):
        patient, dossier_id = self._make_dossier(completed=False)
        try:
            r = patient.post(f"{BASE_URL}/api/dossiers/{dossier_id}/integration-note",
                             json={"note": "Nota di prova"}, timeout=10)
            assert r.status_code == 400
        finally:
            self._cleanup(dossier_id)

    def test_note_saved_and_visible(self):
        patient, dossier_id = self._make_dossier(completed=True)
        try:
            r = patient.post(f"{BASE_URL}/api/dossiers/{dossier_id}/integration-note",
                             json={"note": "Nuova terapia iniziata a marzo, esami del 10/09 allegati."},
                             timeout=10)
            assert r.status_code == 200, r.text
            admin = session_for(ADMIN_EMAIL, ADMIN_PASSWORD)
            r = admin.get(f"{BASE_URL}/api/dossiers/{dossier_id}", timeout=10)
            assert r.status_code == 200
            assert r.json()["integration_note"] == "Nuova terapia iniziata a marzo, esami del 10/09 allegati."
        finally:
            self._cleanup(dossier_id)

    def test_note_not_editable_by_others(self):
        patient, dossier_id = self._make_dossier(completed=True)
        other_email = f"test.note.{uuid.uuid4().hex[:8]}@test.it"
        requests.post(f"{BASE_URL}/api/auth/register",
                      json={"name": "TEST Other", "email": other_email, "password": "TestSicuro2026!",
                            "consent_privacy": True, "consent_health_data": True,
                            "consent_declaration": True}, timeout=15)
        try:
            other = session_for(other_email, "TestSicuro2026!")
            r = other.post(f"{BASE_URL}/api/dossiers/{dossier_id}/integration-note",
                           json={"note": "intrusione"}, timeout=10)
            assert r.status_code == 403
        finally:
            self._cleanup(dossier_id)
            db.users.delete_many({"email": other_email})
            db.consents.delete_many({"email": other_email})

    def test_fulfil_stores_note_in_integrations(self):
        """Al pagamento dell'integrazione, la nota finisce nella entry di integrations."""
        import server
        patient, dossier_id = self._make_dossier(completed=True)
        try:
            patient.post(f"{BASE_URL}/api/dossiers/{dossier_id}/integration-note",
                         json={"note": "Raccordo anamnestico di test"}, timeout=10)
            run_async(server.fulfil_payment({
                "lookup_key": "integrazione_dossier", "dossier_id": dossier_id,
                "user_id": "test", "session_id": f"sess_note_{uuid.uuid4().hex[:8]}",
                "integration_type": "nuovi"}))
            dossier = db.dossiers.find_one({"dossier_id": dossier_id})
            assert dossier["integration_pending"] is True
            assert dossier["integrations"][-1]["note"] == "Raccordo anamnestico di test"
            assert dossier["integrations"][-1]["type"] == "nuovi"
        finally:
            self._cleanup(dossier_id)
