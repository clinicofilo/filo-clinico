from dotenv import load_dotenv, dotenv_values
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import asyncio
import hmac
import io
import json
import logging
import mimetypes
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import bcrypt
import httpx
import jwt
import requests
import stripe
from fastapi import (APIRouter, BackgroundTasks, Depends, FastAPI, File, HTTPException, Query,
                     Request, Response, UploadFile)
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from starlette.middleware.cors import CORSMiddleware
from db import db, init_pool, close_pool

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google.oauth2 import id_token as google_id_token
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

try:
    import boto3
except ImportError:
    boto3 = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI()
api_router = APIRouter(prefix="/api")

JWT_ALGORITHM = "HS256"

FRONTEND_URL = os.environ["FRONTEND_URL"]
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").lower()

_env_file = dotenv_values(ROOT_DIR / ".env")
stripe.api_key = _env_file.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_SECRET_KEY") or "sk_test_placeholder"
STRIPE_WEBHOOK_SECRET = _env_file.get("STRIPE_WEBHOOK_SECRET") or os.environ.get("STRIPE_WEBHOOK_SECRET", "")
TAX_MODE = "full"

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET = os.environ.get("PAYPAL_SECRET", "")
PAYPAL_BASE = "https://api-m.paypal.com" if os.environ.get("PAYPAL_ENV", "live") == "live" else "https://api-m.sandbox.paypal.com"
PAYPAL_AMOUNTS = {
    "revisione_referti": ("50.00", "Revisione referti e riassunto storia clinica - FiloClinico"),
    "consulto_video": ("50.00", "Consulto video online - FiloClinico"),
    "integrazione_dossier": ("25.00", "Integrazione dossier clinico - FiloClinico"),
}
IVA_RATE = 0.22


def paypal_totals(lookup_key: str):
    net = float(PAYPAL_AMOUNTS[lookup_key][0])
    tax = round(net * IVA_RATE, 2)
    return net, tax, round(net + tax, 2)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif", ".pdf"}
MAX_FILE_SIZE = 15 * 1024 * 1024
VALID_STATUSES = ["bozza", "pagato", "in_lavorazione", "completato"]
LOOKUP_KEYS = {"revisione_referti", "consulto_video", "integrazione_dossier"}

APP_NAME = "filoclinico"
STORAGE_PROVIDER = (os.environ.get("STORAGE_PROVIDER") or "local").lower()
UPLOADS_DIR = ROOT_DIR / "uploads"
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
storage_key = None


def init_storage(force: bool = False):
    if STORAGE_PROVIDER == "s3" and S3_BUCKET_NAME and boto3:
        return S3_BUCKET_NAME
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return "local"


def _put_object(path: str, data: bytes, content_type: str) -> dict:
    if STORAGE_PROVIDER == "s3" and S3_BUCKET_NAME and boto3:
        client_kwargs = {}
        if os.environ.get("S3_ENDPOINT_URL"):
            client_kwargs["endpoint_url"] = os.environ["S3_ENDPOINT_URL"]
        if os.environ.get("S3_REGION"):
            client_kwargs["region_name"] = os.environ["S3_REGION"]
        s3 = boto3.client("s3", **client_kwargs)
        s3.put_object(Bucket=S3_BUCKET_NAME, Key=path, Body=data, ContentType=content_type)
        return {"path": path}

    clean_path = path.lstrip("/")
    target = UPLOADS_DIR / clean_path
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as f:
        f.write(data)
    return {"path": clean_path}


def _get_object(path: str):
    if STORAGE_PROVIDER == "s3" and S3_BUCKET_NAME and boto3:
        client_kwargs = {}
        if os.environ.get("S3_ENDPOINT_URL"):
            client_kwargs["endpoint_url"] = os.environ["S3_ENDPOINT_URL"]
        if os.environ.get("S3_REGION"):
            client_kwargs["region_name"] = os.environ["S3_REGION"]
        s3 = boto3.client("s3", **client_kwargs)
        obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=path)
        return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")

    clean_path = path.lstrip("/")
    target = UPLOADS_DIR / clean_path
    if not target.exists():
        possible = UPLOADS_DIR / target.name
        if possible.exists():
            target = possible
        else:
            possible2 = UPLOADS_DIR / APP_NAME / clean_path
            if possible2.exists():
                target = possible2
            else:
                raise HTTPException(status_code=404, detail="File non presente nello storage")
    with open(target, "rb") as f:
        content = f.read()
    mime, _ = mimetypes.guess_type(str(target))
    return content, mime or "application/octet-stream"


def _delete_object(path: str):
    if STORAGE_PROVIDER == "s3" and S3_BUCKET_NAME and boto3:
        try:
            client_kwargs = {}
            if os.environ.get("S3_ENDPOINT_URL"):
                client_kwargs["endpoint_url"] = os.environ["S3_ENDPOINT_URL"]
            s3 = boto3.client("s3", **client_kwargs)
            s3.delete_object(Bucket=S3_BUCKET_NAME, Key=path)
        except Exception as e:
            logger.warning(f"S3 delete fallito per {path}: {e}")
        return

    try:
        clean_path = path.lstrip("/")
        target = UPLOADS_DIR / clean_path
        if target.exists():
            target.unlink()
    except Exception as e:
        logger.warning(f"Eliminazione locale fallita per {path}: {e}")


async def put_object(path: str, data: bytes, content_type: str) -> dict:
    return await asyncio.to_thread(_put_object, path, data, content_type)


async def get_object(path: str):
    return await asyncio.to_thread(_get_object, path)


async def delete_object(path: str):
    try:
        await asyncio.to_thread(_delete_object, path)
    except Exception as e:
        logger.warning(f"Eliminazione dallo storage fallita per {path}: {e}")


async def delete_patient_data(patient_id: str):
    """Elimina dossier e file caricati dal paziente (anche dallo storage).
    Consensi, pagamenti e slot vengono mantenuti per obblighi legali/fiscali."""
    dossiers = await db.dossiers.find({"patient_id": patient_id}).to_list(500)
    for d in dossiers:
        paths = [f.get("storage_path") for f in d.get("files", []) if f.get("storage_path")]
        sf = d.get("summary_file")
        if sf and sf.get("storage_path"):
            paths.append(sf["storage_path"])
        for p in paths:
            await delete_object(p)
        dossier_folder = UPLOADS_DIR / APP_NAME / "uploads" / d["dossier_id"]
        if dossier_folder.exists():
            shutil.rmtree(dossier_folder, ignore_errors=True)
    await db.dossiers.delete_many({"patient_id": patient_id})


def now():
    return datetime.now(timezone.utc)


def clean(doc):
    if not doc:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    doc.pop("password_hash", None)
    return doc


def _csv_safe(value) -> str:
    """Anti formula-injection: neutralizza celle che iniziano con = + - @ tab."""
    s = str(value or "").replace(";", ",")
    if s[:1] in ("=", "+", "-", "@", "\t"):
        s = "'" + s
    return s


# ---------------- Email (Resend / SMTP / Dev fallback) ----------------

import ipaddress
import re as _re
from html import escape as _escape
from html.parser import HTMLParser as _HTMLParser
from urllib.parse import urlparse as _urlparse

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "FiloClinico")
EMAIL_FROM_ADDRESS = os.environ.get("EMAIL_FROM_ADDRESS", "notifiche@filoclinico.org")
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")

_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = _re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", _re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(_HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = _urlparse(low).hostname or ""
        if not _host_ok(host) or _urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = _urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} != real link host {real!r} (G3)")


async def log_email(to: str, subject: str, template: str, status: str, error: str = None):
    """Traccia ogni email inviata/fallita: consultabile dall'area medico."""
    try:
        doc = {"to": to, "subject": subject, "template": template,
               "status": status, "created_at": now().isoformat()}
        if error:
            doc["error"] = error[:500]
        await db.email_log.insert_one(doc)
    except Exception as e:
        logger.warning(f"Log email fallito: {e}")


async def send_email(*, to: str, subject: str, html: str, reply_to: str = None, template: str = "generica"):
    _assert_safe_email(subject, html)
    contact_reply = reply_to or EMAIL_REPLY_TO
    from_header = f"{EMAIL_FROM_NAME} <{EMAIL_FROM_ADDRESS}>"

    # 1. Resend API diretta
    if RESEND_API_KEY:
        try:
            payload = {
                "from": from_header,
                "to": [to],
                "subject": subject,
                "html": html,
            }
            if contact_reply:
                payload["reply_to"] = contact_reply
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                    json=payload)
            resp.raise_for_status()
            await log_email(to, subject, template, "inviata")
            return resp.json().get("id")
        except httpx.HTTPStatusError as e:
            logger.error(f"Resend email send failed: {e.response.status_code} {e.response.text}")
            await log_email(to, subject, template, "fallita", f"HTTP {e.response.status_code}")
            raise HTTPException(status_code=502, detail="Invio email non riuscito")
        except Exception as e:
            logger.error(f"Resend email send error: {e}")
            await log_email(to, subject, template, "fallita", str(e)[:200])
            raise HTTPException(status_code=500, detail="Invio email non riuscito")

    # 2. Standard SMTP
    if SMTP_HOST and SMTP_USER:
        import smtplib
        from email.message import EmailMessage

        def _send_smtp():
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = from_header
            msg["To"] = to
            if contact_reply:
                msg["Reply-To"] = contact_reply
            msg.set_content(html, subtype="html")
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)

        try:
            await asyncio.to_thread(_send_smtp)
            await log_email(to, subject, template, "inviata")
            return "smtp_ok"
        except Exception as e:
            logger.error(f"SMTP send failed: {e}")
            await log_email(to, subject, template, "fallita", str(e)[:200])
            raise HTTPException(status_code=500, detail="Invio email non riuscito")

    # 3. Dev / Mock fallback (registra nei log senza bloccare flussi)
    logger.info(f"[EMAIL DEV SIMULATA] A: {to} | Template: {template} | Oggetto: {subject}")
    await log_email(to, subject, template, "simulata_dev")
    return f"dev_{uuid.uuid4().hex[:8]}"


async def send_account_deleted_email(email: str, name: str):
    """Conferma eliminazione account. Best-effort: non blocca mai l'eliminazione."""
    html = (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;'
        'font-family:Arial,sans-serif;color:#1A2942">'
        '<h2 style="margin:0 0 16px">Account eliminato</h2>'
        f'<p>Ciao {_escape(name or "")},</p>'
        '<p>ti confermiamo che il tuo account FiloClinico è stato eliminato, insieme a '
        'tutti i dossier clinici e i referti che avevi caricato.</p>'
        '<p>Ti ricordiamo che:</p>'
        '<ul style="padding-left:20px;color:#3A3A3A">'
        '<li>le copie dei referti già salvate sull\'archivio del medico che ha redatto il '
        'dossier restano disponibili al medico stesso, in qualità di titolare del trattamento;</li>'
        '<li>le ricevute di pagamento e la registrazione dei consensi privacy vengono '
        'conservate per obblighi fiscali e di legge.</li></ul>'
        '<p style="font-size:13px;color:#68645D">Se non hai richiesto tu questa eliminazione, '
        'contattaci al più presto rispondendo a questa email.</p>'
        f'<p style="font-size:12px;color:#888">Inviata da {_escape(EMAIL_FROM_NAME)}.</p>'
        '</td></tr></table>')
    try:
        await send_email(to=email, subject="FiloClinico — Conferma eliminazione account",
                         html=html, template="account_eliminato")
    except Exception as e:
        logger.error(f"Email eliminazione account non recapitata a {email}: {e}")


def _fmt_dt(dt_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_iso)
        return dt.strftime("%d/%m/%Y alle %H:%M")
    except (ValueError, TypeError):
        return dt_iso or ""


async def send_dossier_ready_email(email: str, name: str, title: str):
    """Avvisa il paziente che il PDF del dossier è stato caricato. Best-effort."""
    link = f"{FRONTEND_URL}/dashboard"
    html = (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;'
        'font-family:Arial,sans-serif;color:#1A2942">'
        '<h2 style="margin:0 0 16px">Il tuo dossier è pronto</h2>'
        f'<p>Ciao {_escape(name or "")},</p>'
        f'<p>il dossier clinico "{_escape(title or "")}" è pronto: il medico ha caricato '
        'il riassunto in PDF della storia clinica. Accedi alla tua area riservata per scaricarlo.</p>'
        f'<p style="margin:24px 0"><a href="{link}" style="background:#C86444;color:#ffffff;'
        'padding:12px 28px;border-radius:999px;text-decoration:none;font-weight:bold">'
        'Apri la tua area riservata</a></p>'
        f'<p style="font-size:12px;color:#888">Inviata da {_escape(EMAIL_FROM_NAME)}.</p>'
        '</td></tr></table>')
    try:
        await send_email(to=email, subject="FiloClinico — Il tuo dossier è pronto",
                         html=html, template="dossier_pronto")
    except Exception as e:
        logger.error(f"Email dossier pronto non recapitata a {email}: {e}")


def _consult_html(name: str, dt_iso: str, meet_link: str, intro: str) -> str:
    when = _fmt_dt(dt_iso)
    meet_btn = ""
    if meet_link:
        meet_btn = (
            f'<p style="margin:24px 0"><a href="{meet_link}" style="background:#C86444;color:#ffffff;'
            'padding:12px 28px;border-radius:999px;text-decoration:none;font-weight:bold">'
            'Entra in videochiamata</a></p>')
    return (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;'
        'font-family:Arial,sans-serif;color:#1A2942">'
        f'<h2 style="margin:0 0 16px">{intro}</h2>'
        f'<p>Ciao {_escape(name or "")},</p>'
        f'<p>il tuo consulto video di 30 minuti con il medico è fissato per <strong>{when}</strong>.</p>'
        + meet_btn +
        '<p style="font-size:13px;color:#68645D">Ti consigliamo di preparare eventuali domande '
        'e di collegarti qualche minuto prima.</p>'
        f'<p style="font-size:12px;color:#888">Inviata da {_escape(EMAIL_FROM_NAME)}.</p>'
        '</td></tr></table>')


async def send_consult_booked_email(email: str, name: str, dt_iso: str, meet_link: str):
    """Conferma prenotazione consulto video. Best-effort."""
    try:
        await send_email(to=email, subject="FiloClinico — Consulto video prenotato",
                         html=_consult_html(name, dt_iso, meet_link, "Consulto video prenotato"),
                         template="consulto_conferma")
    except Exception as e:
        logger.error(f"Email conferma consulto non recapitata a {email}: {e}")


async def send_consult_reminder_email(email: str, name: str, dt_iso: str, meet_link: str):
    """Promemoria 24h prima del consulto video. Best-effort."""
    try:
        await send_email(to=email, subject="FiloClinico — Promemoria: consulto video in programma",
                         html=_consult_html(name, dt_iso, meet_link, "Promemoria consulto video"),
                         template="consulto_promemoria")
    except Exception as e:
        logger.error(f"Email promemoria consulto non recapitata a {email}: {e}")


# ---------------- Auth ----------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, email: str, token_version: int = 0) -> str:
    payload = {"sub": user_id, "email": email, "type": "access", "tv": token_version,
               "exp": now() + timedelta(minutes=15)}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str, token_version: int = 0) -> str:
    payload = {"sub": user_id, "type": "refresh", "tv": token_version,
               "exp": now() + timedelta(days=7)}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def set_auth_cookies(response: Response, access: str, refresh: str):
    response.set_cookie("access_token", access, httponly=True, secure=True, samesite="none", max_age=900, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="none", max_age=604800, path="/")


async def user_from_jwt(token: str):
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
    except Exception:
        return None
    user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user or payload.get("tv", 0) != user.get("token_version", 0):
        return None
    return user


async def user_from_session(token: str):
    sess = await db.user_sessions.find_one({"session_token": token})
    if not sess:
        return None
    exp = sess.get("expires_at")
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now():
        return None
    return await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0, "password_hash": 0})


async def get_current_user(request: Request):
    user = None
    access = request.cookies.get("access_token")
    session_token = request.cookies.get("session_token")
    auth = request.headers.get("Authorization", "")
    bearer = auth[7:] if auth.startswith("Bearer ") else None
    if access:
        user = await user_from_jwt(access)
    if not user and session_token:
        user = await user_from_session(session_token)
    if not user and bearer:
        user = await user_from_jwt(bearer) or await user_from_session(bearer)
    if not user:
        raise HTTPException(status_code=401, detail="Non autenticato")
    return user


async def require_admin(user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accesso riservato al medico")
    return user


CONSENT_VERSION = "1.0"


async def record_consent(user_id: str, email: str, request: Request):
    await db.consents.insert_one({
        "user_id": user_id, "email": email, "version": CONSENT_VERSION,
        "items": {"privacy": True, "health_data": True, "declaration": True},
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", ""),
        "created_at": now().isoformat()})


def validate_password_strength(password: str):
    letters = sum(c.isalpha() for c in password)
    if (len(password) < 8 or letters < 6
            or not any(c.isdigit() for c in password)
            or not any(not c.isalnum() for c in password)):
        raise HTTPException(
            status_code=400,
            detail="La password deve avere almeno 8 caratteri, con almeno 6 lettere, un numero e un carattere speciale")


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    recovery_email: Optional[EmailStr] = None
    consent_privacy: bool
    consent_health_data: bool
    consent_declaration: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleSessionRequest(BaseModel):
    session_id: Optional[str] = None
    code: Optional[str] = None
    credential: Optional[str] = None
    redirect_uri: Optional[str] = None


@api_router.post("/auth/register")
async def register(body: RegisterRequest, request: Request, response: Response):
    email = body.email.lower()
    if not (body.consent_privacy and body.consent_health_data and body.consent_declaration):
        raise HTTPException(status_code=400, detail="Devi accettare tutti i consensi obbligatori per registrarti")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Registrazione non riuscita. Se hai già un account con questa email, accedi oppure reimposta la password.")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="La password deve avere almeno 8 caratteri")
    validate_password_strength(body.password)
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    role = "admin" if email == ADMIN_EMAIL else "patient"
    doc = {"user_id": user_id, "email": email, "name": body.name.strip(), "role": role,
           "password_hash": hash_password(body.password), "auth_provider": "email",
           "recovery_email": body.recovery_email.lower() if body.recovery_email else None,
           "consents_version": CONSENT_VERSION, "created_at": now().isoformat()}
    await db.users.insert_one(doc)
    await record_consent(user_id, email, request)
    set_auth_cookies(response, create_access_token(user_id, email), create_refresh_token(user_id))
    doc["has_password"] = True
    return clean(doc)


class ConsentRequest(BaseModel):
    consent_privacy: bool
    consent_health_data: bool
    consent_declaration: bool


@api_router.post("/auth/consents")
async def save_consents(body: ConsentRequest, request: Request, user=Depends(get_current_user)):
    if not (body.consent_privacy and body.consent_health_data and body.consent_declaration):
        raise HTTPException(status_code=400, detail="Devi accettare tutti i consensi obbligatori")
    await record_consent(user["user_id"], user["email"], request)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"consents_version": CONSENT_VERSION}})
    return {"ok": True}


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


@api_router.post("/auth/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, request: Request):
    email = body.email.lower()
    identifier = f"forgot:{request.client.host if request.client else 'unknown'}"
    attempts = await db.login_attempts.find_one({"identifier": identifier})
    if attempts and attempts.get("count", 0) >= 5:
        locked_at = datetime.fromisoformat(attempts["updated_at"])
        if locked_at.tzinfo is None:
            locked_at = locked_at.replace(tzinfo=timezone.utc)
        if now() - locked_at < timedelta(minutes=15):
            raise HTTPException(status_code=429, detail="Troppe richieste. Riprova tra 15 minuti.")
    await db.login_attempts.update_one(
        {"identifier": identifier},
        {"$inc": {"count": 1}, "$set": {"updated_at": now().isoformat()}}, upsert=True)
    user = await db.users.find_one({"email": email})
    if user and user.get("password_hash"):
        token = uuid.uuid4().hex + uuid.uuid4().hex
        await db.password_resets.delete_many({"email": email})
        await db.password_resets.insert_one({
            "token": token, "email": email, "user_id": user["user_id"],
            "expires_at": (now() + timedelta(minutes=30)).isoformat(),
            "used": False, "created_at": now().isoformat()})
        link = f"{FRONTEND_URL}/reset-password?token={token}"
        html = (
            '<table role="presentation" width="100%"><tr><td style="padding:24px;'
            'font-family:Arial,sans-serif;color:#1A2942">'
            f'<h2 style="margin:0 0 16px">Reimposta la tua password</h2>'
            f'<p>Ciao {_escape(user.get("name", ""))},</p>'
            '<p>hai richiesto di reimpostare la password del tuo account FiloClinico. '
            'Clicca il pulsante qui sotto (il link è valido 30 minuti e utilizzabile una sola volta):</p>'
            f'<p style="margin:24px 0"><a href="{link}" style="background:#C86444;color:#ffffff;'
            'padding:12px 28px;border-radius:999px;text-decoration:none;font-weight:bold">'
            'Reimposta password</a></p>'
            f'<p style="font-size:13px;color:#68645D">Se non hai richiesto tu il ripristino, '
            'ignora questa email: la tua password resta invariata.</p>'
            f'<p style="font-size:12px;color:#888">Inviata da {_escape(EMAIL_FROM_NAME)}. '
            'Non chiediamo mai la password via email.</p></td></tr></table>')
        try:
            await send_email(to=email, subject="FiloClinico — Reimposta la tua password",
                             html=html, template="reset_password")
        except Exception as e:
            logger.error(f"Reset email non recapitata a {email}: {e}")
    return {"ok": True}


@api_router.post("/auth/reset-password")
async def reset_password(body: ResetPasswordRequest):
    record = await db.password_resets.find_one({"token": body.token})
    if not record or record.get("used"):
        raise HTTPException(status_code=400, detail="Link non valido o già utilizzato")
    exp = datetime.fromisoformat(record["expires_at"])
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now():
        raise HTTPException(status_code=400, detail="Link scaduto. Richiedine uno nuovo.")
    validate_password_strength(body.password)
    await db.users.update_one({"user_id": record["user_id"]},
                              {"$set": {"password_hash": hash_password(body.password)},
                               "$inc": {"token_version": 1}})
    await db.user_sessions.delete_many({"user_id": record["user_id"]})
    await db.password_resets.update_one({"token": body.token}, {"$set": {"used": True}})
    return {"ok": True}


@api_router.post("/auth/login")
async def login(body: LoginRequest, request: Request, response: Response):
    email = body.email.lower()
    identifier = f"{request.client.host}:{email}"
    attempts = await db.login_attempts.find_one({"identifier": identifier})
    if attempts and attempts.get("count", 0) >= 5:
        locked_at = datetime.fromisoformat(attempts["updated_at"])
        if locked_at.tzinfo is None:
            locked_at = locked_at.replace(tzinfo=timezone.utc)
        if now() - locked_at < timedelta(minutes=15):
            raise HTTPException(status_code=429, detail="Troppi tentativi. Riprova tra 15 minuti.")
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1}, "$set": {"updated_at": now().isoformat()}}, upsert=True)
        raise HTTPException(status_code=401, detail="Email o password non corretti")
    await db.login_attempts.delete_one({"identifier": identifier})
    tv = user.get("token_version", 0)
    set_auth_cookies(response, create_access_token(user["user_id"], email, tv), create_refresh_token(user["user_id"], tv))
    user["has_password"] = bool(user.get("password_hash"))
    return clean(user)


@api_router.get("/auth/google/url")
async def google_auth_url(redirect_uri: Optional[str] = Query(None)):
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=400, detail="Google OAuth non configurato sul server")
    from urllib.parse import urlencode
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri or f"{FRONTEND_URL}/auth/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
    }
    return {"url": f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"}


@api_router.post("/auth/google/session")
async def google_session(body: GoogleSessionRequest, response: Response):
    email = None
    name = ""
    picture = ""

    # 1. Scambio codice OAuth Google standard
    if body.code:
        client_id = os.environ.get("GOOGLE_CLIENT_ID")
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise HTTPException(status_code=500, detail="Credenziali Google OAuth non configurate")
        token_resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": body.code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": body.redirect_uri or f"{FRONTEND_URL}/auth/callback",
                "grant_type": "authorization_code"
            }, timeout=15)
        if token_resp.status_code != 200:
            logger.error(f"Google token exchange failed: {token_resp.text}")
            raise HTTPException(status_code=401, detail="Autenticazione con Google non riuscita")
        token_data = token_resp.json()
        if "id_token" in token_data:
            try:
                idinfo = google_id_token.verify_oauth2_token(token_data["id_token"], GoogleRequest(), client_id)
                email = idinfo["email"].lower()
                name = idinfo.get("name", "")
                picture = idinfo.get("picture", "")
            except Exception as e:
                logger.warning(f"ID token verification fallback: {e}")
        if not email and "access_token" in token_data:
            userinfo = requests.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {token_data['access_token']}"}, timeout=10).json()
            email = userinfo.get("email", "").lower()
            name = userinfo.get("name", "")
            picture = userinfo.get("picture", "")

    # 2. Token Google ID diretto (Google One Tap / Credential)
    elif body.credential:
        client_id = os.environ.get("GOOGLE_CLIENT_ID")
        try:
            idinfo = google_id_token.verify_oauth2_token(body.credential, GoogleRequest(), client_id)
            email = idinfo["email"].lower()
            name = idinfo.get("name", "")
            picture = idinfo.get("picture", "")
        except Exception as e:
            logger.error(f"Google credential verify failed: {e}")
            raise HTTPException(status_code=401, detail="Credenziale Google non valida")

    # 3. Session ID diretto (test automatici o sessione già creata in DB)
    elif body.session_id:
        sess = await db.user_sessions.find_one({"session_token": body.session_id})
        if sess:
            user = await db.users.find_one({"user_id": sess["user_id"]})
            if user:
                response.set_cookie("session_token", body.session_id, httponly=True, secure=True,
                                    samesite="none", max_age=7 * 24 * 3600, path="/")
                out = clean(user)
                out["has_password"] = bool(user.get("password_hash"))
                return out
        raise HTTPException(status_code=401, detail="Sessione Google non valida")
    else:
        raise HTTPException(status_code=400, detail="Parametri di autenticazione mancanti")

    if not email:
        raise HTTPException(status_code=401, detail="Impossibile recuperare i dati dell'account Google")

    user = await db.users.find_one({"email": email})
    if not user:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        role = "admin" if email == ADMIN_EMAIL else "patient"
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": name,
            "picture": picture, "role": role,
            "auth_provider": "google", "created_at": now().isoformat()})
    else:
        user_id = user["user_id"]

    session_token = f"sess_{uuid.uuid4().hex}{uuid.uuid4().hex}"
    await db.user_sessions.insert_one({
        "user_id": user_id, "session_token": session_token,
        "expires_at": (now() + timedelta(days=7)).isoformat(),
        "created_at": now().isoformat()})
    response.set_cookie("session_token", session_token, httponly=True, secure=True,
                        samesite="none", max_age=7 * 24 * 3600, path="/")
    full = await db.users.find_one({"user_id": user_id})
    out = clean(full)
    out["has_password"] = bool(full.get("password_hash"))
    return out


@api_router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    full = await db.users.find_one({"user_id": user["user_id"]}, {"password_hash": 1})
    user["has_password"] = bool(full and full.get("password_hash"))
    return user


@api_router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Nessun refresh token")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token non valido")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")
    user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user or payload.get("tv", 0) != user.get("token_version", 0):
        raise HTTPException(status_code=401, detail="Token non valido")
    response.set_cookie("access_token", create_access_token(user["user_id"], user["email"], user.get("token_version", 0)),
                        httponly=True, secure=True, samesite="none", max_age=900, path="/")
    return {"ok": True}


@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.user_sessions.delete_many({"session_token": session_token})
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


class DeleteAccountRequest(BaseModel):
    password: str = ""
    confirm_email: str = ""


@api_router.post("/auth/delete-account")
async def delete_account(body: DeleteAccountRequest, response: Response, user=Depends(get_current_user)):
    if user.get("role") == "admin":
        raise HTTPException(status_code=400, detail="L'account medico non può essere eliminato")
    full = await db.users.find_one({"user_id": user["user_id"]})
    if full.get("password_hash"):
        if not body.password or not verify_password(body.password, full["password_hash"]):
            raise HTTPException(status_code=401, detail="Password non corretta")
    elif body.confirm_email.strip().lower() != user["email"]:
        raise HTTPException(status_code=400, detail="Per confermare inserisci la tua email di registrazione")
    await delete_patient_data(user["user_id"])
    await db.users.delete_one({"user_id": user["user_id"]})
    await db.user_sessions.delete_many({"user_id": user["user_id"]})
    await db.password_resets.delete_many({"email": user["email"]})
    await send_account_deleted_email(user["email"], full.get("name", ""))
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


# ---------------- Dossier ----------------

class DossierCreate(BaseModel):
    title: str
    patient_name: str
    relationship: str = "me"
    notes: str = ""


class DossierUpdate(BaseModel):
    status: Optional[str] = None
    summary_text: Optional[str] = None
    title: Optional[str] = None
    patient_name: Optional[str] = None


async def get_dossier_or_404(dossier_id: str, user):
    dossier = await db.dossiers.find_one({"dossier_id": dossier_id})
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier non trovato")
    if user.get("role") != "admin" and dossier["patient_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Accesso non autorizzato")
    return dossier


@api_router.post("/dossiers")
async def create_dossier(body: DossierCreate, user=Depends(get_current_user)):
    dossier_id = f"doss_{uuid.uuid4().hex[:12]}"
    doc = {
        "dossier_id": dossier_id,
        "patient_id": user["user_id"],
        "patient_email": user["email"],
        "patient_account_name": user.get("name", ""),
        "title": body.title.strip(),
        "patient_name": body.patient_name.strip(),
        "relationship": body.relationship,
        "notes": body.notes,
        "status": "bozza",
        "files": [],
        "summary_text": "",
        "summary_file": None,
        "revisione_paid": False,
        "consult_paid": False,
        "consult_slot_id": None,
        "integration_pending": False,
        "integrations": [],
        "created_at": now().isoformat(),
        "updated_at": now().isoformat(),
    }
    await db.dossiers.insert_one(doc)
    return clean(doc)


@api_router.post("/dossiers/{dossier_id}/questionnaire-done")
async def questionnaire_done(dossier_id: str, user=Depends(get_current_user)):
    await get_dossier_or_404(dossier_id, user)
    creds_doc = await db.drive_credentials.find_one({})
    if creds_doc:
        try:
            found = await asyncio.to_thread(_forms_has_response_sync, creds_doc, user["email"])
        except Exception as e:
            logger.error(f"Forms check error: {e}")
            found = None
        if found is False:
            raise HTTPException(
                status_code=400,
                detail="Non trovo una risposta al questionario con la tua email. Compila il questionario (Passo 1), invialo e riprova tra qualche secondo.")
    await db.dossiers.update_one(
        {"dossier_id": dossier_id},
        {"$set": {"questionnaire_done": True, "questionnaire_done_at": now().isoformat(),
                  "updated_at": now().isoformat()}})
    return {"ok": True}


@api_router.get("/dossiers")
async def list_dossiers(user=Depends(get_current_user)):
    query = {} if user.get("role") == "admin" else {"patient_id": user["user_id"]}
    dossiers = await db.dossiers.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return dossiers


@api_router.get("/dossiers/{dossier_id}")
async def get_dossier(dossier_id: str, user=Depends(get_current_user)):
    return clean(await get_dossier_or_404(dossier_id, user))


@api_router.patch("/dossiers/{dossier_id}")
async def update_dossier(dossier_id: str, body: DossierUpdate, user=Depends(require_admin)):
    dossier = await get_dossier_or_404(dossier_id, user)
    updates = {"updated_at": now().isoformat()}
    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail="Stato non valido")
        updates["status"] = body.status
    if body.summary_text is not None:
        updates["summary_text"] = body.summary_text
    if body.title is not None and body.title.strip():
        updates["title"] = body.title.strip()
    if body.patient_name is not None and body.patient_name.strip():
        updates["patient_name"] = body.patient_name.strip()
    await db.dossiers.update_one({"dossier_id": dossier_id}, {"$set": updates})
    return clean(await db.dossiers.find_one({"dossier_id": dossier["dossier_id"]}))


@api_router.delete("/dossiers/{dossier_id}")
async def delete_dossier(dossier_id: str, user=Depends(require_admin)):
    dossier = await db.dossiers.find_one({"dossier_id": dossier_id})
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier non trovato")
    await db.dossiers.delete_one({"dossier_id": dossier_id})
    return {"ok": True}


# ---------------- Google Drive ----------------

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/forms.responses.readonly",
]
GOOGLE_FORM_ID = "1O3Cp3GnFtW8cevhgm82jnwbSQRJ9gCclunzJoLReVjE"


def _drive_flow(scopes=DRIVE_SCOPES, autogenerate_code_verifier=True):
    return Flow.from_client_config(
        {"web": {
            "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
            "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [os.environ["GOOGLE_DRIVE_REDIRECT_URI"]],
        }},
        scopes=scopes,
        autogenerate_code_verifier=autogenerate_code_verifier,
        redirect_uri=os.environ["GOOGLE_DRIVE_REDIRECT_URI"])


def _forms_has_response_sync(creds_doc, email: str):
    creds = Credentials(
        token=creds_doc["access_token"],
        refresh_token=creds_doc.get("refresh_token"),
        token_uri=creds_doc["token_uri"],
        client_id=creds_doc["client_id"],
        client_secret=creds_doc["client_secret"],
        scopes=creds_doc.get("scopes"))
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
    service = build("forms", "v1", credentials=creds)
    email_l = email.lower()
    page_token = None
    while True:
        kwargs = {"formId": GOOGLE_FORM_ID, "pageSize": 200}
        if page_token:
            kwargs["pageToken"] = page_token
        resp = service.forms().responses().list(**kwargs).execute()
        for r in resp.get("responses", []):
            if email_l and (r.get("respondentEmail", "").lower() == email_l or email_l in json.dumps(r).lower()):
                return True
        page_token = resp.get("nextPageToken")
        if not page_token:
            return False


@api_router.get("/drive/connect")
async def drive_connect(user=Depends(require_admin)):
    if not os.environ.get("GOOGLE_CLIENT_ID") or not os.environ.get("GOOGLE_CLIENT_SECRET"):
        raise HTTPException(status_code=400, detail="Credenziali Google OAuth non configurate sul server")
    flow = _drive_flow(autogenerate_code_verifier=False)
    authorization_url, _ = flow.authorization_url(
        access_type="offline", include_granted_scopes="true",
        prompt="consent", state=user["user_id"])
    return {"authorization_url": authorization_url}


@api_router.get("/drive/callback")
async def drive_callback(code: str = Query(None), state: str = Query(None), error: str = Query(None)):
    if error or not code:
        logger.error(f"Drive OAuth error from Google: {error}")
        return RedirectResponse(f"{FRONTEND_URL}/admin?drive=error")
    try:
        flow = _drive_flow(scopes=None, autogenerate_code_verifier=False)
        flow.fetch_token(code=code)
    except Exception as e:
        logger.error(f"Drive token exchange failed: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/admin?drive=error")
    creds = flow.credentials
    await db.drive_credentials.update_one(
        {"user_id": state},
        {"$set": {
            "user_id": state,
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or []),
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
            "updated_at": now().isoformat(),
        }},
        upsert=True)
    return RedirectResponse(f"{FRONTEND_URL}/admin?drive=ok")


@api_router.get("/drive/status")
async def drive_status(user=Depends(require_admin)):
    connected = await db.drive_credentials.find_one({"user_id": user["user_id"]}) is not None
    configured = bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))
    return {"connected": connected, "configured": configured}


def _drive_create_folder(service, name, parent=None):
    safe = name.replace("'", " ").replace("\\", " ")
    q = f"name='{safe}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent:
        q += f" and '{parent}' in parents"
    res = service.files().list(q=q, fields="files(id,name)", supportsAllDrives=True).execute()
    if res.get("files"):
        return res["files"][0]["id"]
    meta = {"name": safe, "mimeType": "application/vnd.google-apps.folder"}
    if parent:
        meta["parents"] = [parent]
    return service.files().create(body=meta, fields="id", supportsAllDrives=True).execute()["id"]


def _drive_upload_sync(creds_doc, folder_name, data: bytes, filename, mime):
    creds = Credentials(
        token=creds_doc["access_token"],
        refresh_token=creds_doc.get("refresh_token"),
        token_uri=creds_doc["token_uri"],
        client_id=creds_doc["client_id"],
        client_secret=creds_doc["client_secret"],
        scopes=creds_doc.get("scopes"))
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
    service = build("drive", "v3", credentials=creds)
    root_id = _drive_create_folder(service, "Dossier Pazienti")
    folder_id = _drive_create_folder(service, folder_name, root_id)
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime)
    f = service.files().create(body={"name": filename, "parents": [folder_id]},
                               media_body=media, fields="id", supportsAllDrives=True).execute()
    new_token = creds.token if creds.token != creds_doc["access_token"] else None
    new_expiry = creds.expiry.isoformat() if creds.expiry else None
    return f["id"], new_token, new_expiry


async def drive_upload(dossier, content: bytes, filename: str, mime: str):
    try:
        creds_doc = await db.drive_credentials.find_one({})
        if not creds_doc:
            return None
        folder_name = f"{dossier.get('patient_name', 'Paziente')} - {dossier['dossier_id']}"
        file_id, new_token, new_expiry = await asyncio.to_thread(
            _drive_upload_sync, creds_doc, folder_name, content, filename, mime)
        if new_token:
            await db.drive_credentials.update_one(
                {"user_id": creds_doc["user_id"]},
                {"$set": {"access_token": new_token, "expiry": new_expiry,
                          "updated_at": now().isoformat()}})
        return file_id
    except Exception as e:
        logger.error(f"Drive upload error: {e}")
        return None


# ---------------- File referti ----------------

SAFE_INLINE_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
SAFE_INLINE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def safe_file_response(data: bytes, meta: dict):
    mime = meta.get("mime") or "application/octet-stream"
    ext = os.path.splitext(meta.get("filename") or "")[1].lower()
    headers = {"X-Content-Type-Options": "nosniff"}
    if mime in SAFE_INLINE_MIME and ext in SAFE_INLINE_EXT:
        return Response(content=data, media_type=mime, headers=headers)
    filename = (meta.get("filename") or "documento").replace('"', "")
    headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return Response(content=data, media_type="application/octet-stream", headers=headers)

@api_router.post("/dossiers/{dossier_id}/files")
async def upload_files(dossier_id: str, files: List[UploadFile] = File(...), user=Depends(get_current_user)):
    dossier = await get_dossier_or_404(dossier_id, user)
    if dossier["status"] == "completato" and not dossier.get("integration_pending"):
        raise HTTPException(status_code=400, detail="Il dossier è completato. Per aggiungere altri referti richiedi un'integrazione")
    if not dossier.get("questionnaire_done"):
        raise HTTPException(status_code=400, detail="Compila prima il questionario anamnestico (Passo 1)")
    saved = []
    for f in files:
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Formato non supportato: {ext or f.filename}")
        content = await f.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"{f.filename}: file troppo grande (max 15MB)")
        file_id = uuid.uuid4().hex[:12]
        mime = f.content_type or "application/octet-stream"
        storage_path = f"{APP_NAME}/uploads/{dossier_id}/{file_id}{ext}"
        result = await put_object(storage_path, content, mime)
        drive_id = await drive_upload(dossier, content, f.filename, mime)
        saved.append({
            "file_id": file_id, "filename": f.filename, "storage_path": result["path"],
            "mime": mime, "size": len(content), "drive_file_id": drive_id,
            "uploaded_at": now().isoformat()})
    await db.dossiers.update_one(
        {"dossier_id": dossier_id},
        {"$push": {"files": {"$each": saved}}, "$set": {"updated_at": now().isoformat()}})
    return {"files": saved}


@api_router.get("/dossiers/{dossier_id}/files/{file_id}")
async def get_file(dossier_id: str, file_id: str, user=Depends(get_current_user)):
    dossier = await get_dossier_or_404(dossier_id, user)
    meta = next((f for f in dossier.get("files", []) if f["file_id"] == file_id), None)
    if not meta:
        raise HTTPException(status_code=404, detail="File non trovato")
    try:
        data, ctype = await get_object(meta["storage_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="File non presente nello storage")
    return safe_file_response(data, meta)


@api_router.delete("/dossiers/{dossier_id}/files/{file_id}")
async def delete_file(dossier_id: str, file_id: str, user=Depends(get_current_user)):
    dossier = await get_dossier_or_404(dossier_id, user)
    if dossier["status"] == "completato" and not dossier.get("integration_pending"):
        raise HTTPException(status_code=400, detail="Il dossier è completato")
    meta = next((f for f in dossier.get("files", []) if f["file_id"] == file_id), None)
    if not meta:
        raise HTTPException(status_code=404, detail="File non trovato")
    await db.dossiers.update_one(
        {"dossier_id": dossier_id},
        {"$pull": {"files": {"file_id": file_id}}, "$set": {"updated_at": now().isoformat()}})
    return {"ok": True}


@api_router.post("/dossiers/{dossier_id}/summary-file")
async def upload_summary_file(dossier_id: str, file: UploadFile = File(...), user=Depends(require_admin)):
    dossier = await get_dossier_or_404(dossier_id, user)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".pdf", ".jpg", ".jpeg", ".png"}:
        raise HTTPException(status_code=400, detail="Carica un PDF o un'immagine")
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File troppo grande (max 15MB)")
    mime = file.content_type or "application/pdf"
    storage_path = f"{APP_NAME}/uploads/{dossier_id}/summary_{uuid.uuid4().hex[:8]}{ext}"
    result = await put_object(storage_path, content, mime)
    meta = {"storage_path": result["path"], "filename": file.filename,
            "mime": mime, "uploaded_at": now().isoformat()}
    await db.dossiers.update_one(
        {"dossier_id": dossier_id},
        {"$set": {"summary_file": meta, "integration_pending": False, "updated_at": now().isoformat()}})
    if dossier.get("patient_email"):
        await send_dossier_ready_email(
            dossier["patient_email"],
            dossier.get("patient_account_name") or dossier.get("patient_name", ""),
            dossier.get("title", ""))
    return {"summary_file": meta}


@api_router.get("/dossiers/{dossier_id}/summary-file")
async def get_summary_file(dossier_id: str, user=Depends(get_current_user)):
    dossier = await get_dossier_or_404(dossier_id, user)
    meta = dossier.get("summary_file")
    if not meta:
        raise HTTPException(status_code=404, detail="Nessun riassunto caricato")
    try:
        data, ctype = await get_object(meta["storage_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="File non presente nello storage")
    return safe_file_response(data, meta)


# ---------------- Pagamenti Stripe ----------------

class IntegrationNote(BaseModel):
    note: str


@api_router.post("/dossiers/{dossier_id}/integration-note")
async def set_integration_note(dossier_id: str, body: IntegrationNote, user=Depends(get_current_user)):
    """Breve raccordo anamnestico per l'integrazione da 25€: niente questionario, solo testo libero."""
    dossier = await get_dossier_or_404(dossier_id, user)
    if dossier["status"] != "completato" and not dossier.get("integration_pending"):
        raise HTTPException(status_code=400, detail="L'integrazione è disponibile solo per dossier completati")
    await db.dossiers.update_one(
        {"dossier_id": dossier_id},
        {"$set": {"integration_note": body.note.strip()[:2000], "updated_at": now().isoformat()}})
    return {"ok": True}


class CheckoutRequest(BaseModel):
    lookup_key: str
    origin_url: str
    dossier_id: str
    slot_id: Optional[str] = None
    integration_type: Optional[str] = None


async def fulfil_payment(record):
    dossier_id = record.get("dossier_id")
    if record.get("lookup_key") == "revisione_referti":
        await db.dossiers.update_one(
            {"dossier_id": dossier_id, "status": "bozza"},
            {"$set": {"status": "pagato", "revisione_paid": True, "updated_at": now().isoformat()}})
        await db.dossiers.update_one(
            {"dossier_id": dossier_id},
            {"$set": {"revisione_paid": True, "updated_at": now().isoformat()}})
    elif record.get("lookup_key") == "integrazione_dossier":
        doss = await db.dossiers.find_one({"dossier_id": dossier_id})
        await db.dossiers.update_one(
            {"dossier_id": dossier_id},
            {"$set": {"integration_pending": True, "updated_at": now().isoformat()},
             "$push": {"integrations": {"type": record.get("integration_type") or "",
                                        "note": (doss or {}).get("integration_note", ""),
                                        "paid_at": now().isoformat()}}})
    elif record.get("lookup_key") == "consulto_video":
        slot = None
        if record.get("slot_id"):
            res = await db.slots.update_one(
                {"slot_id": record["slot_id"], "status": "available"},
                {"$set": {"status": "booked", "booked_by": record.get("user_id"),
                          "dossier_id": dossier_id, "updated_at": now().isoformat()}})
            if res.modified_count == 0:
                # SEC: slot già prenotato da un altro pagamento concorrente.
                # NON segnare il consulto come pagato: il medico valuta rimborso/spostamento.
                logger.error(f"Slot {record['slot_id']} già prenotato: consulto non assegnato "
                             f"(dossier {dossier_id}, sessione {record.get('session_id')})")
                await db.payment_transactions.update_one(
                    {"session_id": record.get("session_id")},
                    {"$set": {"slot_conflict": True, "updated_at": now().isoformat()}})
                return
            slot = await db.slots.find_one({"slot_id": record["slot_id"]})
        consult_updates = {"consult_paid": True, "consult_slot_id": record.get("slot_id"),
                           "updated_at": now().isoformat()}
        if slot:
            consult_updates["consult_datetime"] = slot.get("datetime", "")
            consult_updates["consult_meet_link"] = slot.get("meet_link", "")
        await db.dossiers.update_one({"dossier_id": dossier_id}, {"$set": consult_updates})
        if slot:
            doss = await db.dossiers.find_one({"dossier_id": dossier_id})
            if doss and doss.get("patient_email"):
                await send_consult_booked_email(
                    doss["patient_email"],
                    doss.get("patient_account_name") or doss.get("patient_name", ""),
                    slot.get("datetime", ""), slot.get("meet_link", ""))


async def mark_paid(session_id: str, extra=None):
    updates = {"status": "completed", "payment_status": "paid", "updated_at": now().isoformat()}
    if extra:
        updates.update(extra)
    res = await db.payment_transactions.update_one(
        {"session_id": session_id, "payment_status": {"$ne": "paid"}}, {"$set": updates})
    if res.modified_count:
        record = await db.payment_transactions.find_one({"session_id": session_id})
        if record:
            await fulfil_payment(record)


@api_router.post("/payments/checkout")
async def create_checkout(body: CheckoutRequest, user=Depends(get_current_user)):
    if body.lookup_key not in LOOKUP_KEYS:
        raise HTTPException(status_code=400, detail="Servizio non valido")
    dossier = await get_dossier_or_404(body.dossier_id, user)
    if body.lookup_key == "consulto_video":
        if not body.slot_id:
            raise HTTPException(status_code=400, detail="Seleziona uno slot per il consulto")
        slot = await db.slots.find_one({"slot_id": body.slot_id})
        if not slot or slot["status"] != "available":
            raise HTTPException(status_code=400, detail="Slot non più disponibile")
    if body.lookup_key == "integrazione_dossier":
        if dossier["status"] != "completato":
            raise HTTPException(status_code=400, detail="L'integrazione è disponibile solo per dossier completati")
        if dossier.get("integration_pending"):
            raise HTTPException(status_code=400, detail="Hai già un'integrazione in corso")
        if body.integration_type not in ("nuovi", "dimenticati"):
            raise HTTPException(status_code=400, detail="Tipo di integrazione non valido")
    prices = await asyncio.to_thread(
        lambda: stripe.Price.list(lookup_keys=[body.lookup_key], active=True, limit=1).data)
    if not prices:
        raise HTTPException(status_code=500, detail=f"Prezzo non trovato: {body.lookup_key}")
    price = prices[0]
    kwargs = dict(
        line_items=[{"price": price.id, "quantity": 1}],
        mode="payment",
        success_url=f"{body.origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{body.origin_url}/payment/cancel",
        metadata={"user_id": user["user_id"], "lookup_key": body.lookup_key,
                  "dossier_id": body.dossier_id, "slot_id": body.slot_id or "",
                  "integration_type": body.integration_type or ""})

    def _create():
        if TAX_MODE == "full":
            try:
                return stripe.checkout.Session.create(**kwargs, managed_payments={"enabled": True})
            except stripe.error.InvalidRequestError as e:
                msg = (e.user_message or "").lower()
                if "managed payments" in msg or "ineligible" in msg:
                    return stripe.checkout.Session.create(
                        **kwargs, automatic_tax={"enabled": True},
                        billing_address_collection="required")
                raise
        return stripe.checkout.Session.create(**kwargs)

    session = await asyncio.to_thread(_create)
    await db.payment_transactions.insert_one({
        "session_id": session.id, "user_id": user["user_id"],
        "dossier_id": body.dossier_id, "slot_id": body.slot_id,
        "integration_type": body.integration_type,
        "lookup_key": body.lookup_key, "amount": (price.unit_amount or 0) / 100.0,
        "currency": price.currency, "status": "initiated", "payment_status": "pending",
        "created_at": now().isoformat(), "updated_at": now().isoformat()})
    return {"checkout_url": session.url, "session_id": session.id}


@api_router.get("/payments/status/{session_id}")
async def payment_status(session_id: str, user=Depends(get_current_user)):
    record = await db.payment_transactions.find_one({"session_id": session_id})
    if not record:
        raise HTTPException(status_code=404, detail="Transazione non trovata")
    if record.get("user_id") != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accesso non autorizzato")
    if record.get("payment_status") != "paid":
        try:
            s = await asyncio.to_thread(stripe.checkout.Session.retrieve, session_id)
            if s.payment_status == "paid" or s.status == "complete":
                await mark_paid(session_id, {
                    "stripe_payment_intent_id": s.payment_intent})
                record = await db.payment_transactions.find_one({"session_id": session_id})
        except stripe.error.StripeError:
            pass
    return {"session_id": record["session_id"], "status": record["status"],
            "payment_status": record["payment_status"]}


@api_router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    obj, t = event["data"]["object"], event["type"]
    if t == "checkout.session.completed":
        await mark_paid(obj["id"], {
            "stripe_payment_intent_id": obj.get("payment_intent")})
    elif t == "checkout.session.async_payment_succeeded":
        await mark_paid(obj["id"])
    elif t == "checkout.session.async_payment_failed":
        await db.payment_transactions.update_one(
            {"session_id": obj["id"]},
            {"$set": {"status": "failed", "payment_status": "failed", "updated_at": now().isoformat()}})
    elif t == "checkout.session.expired":
        await db.payment_transactions.update_one(
            {"session_id": obj["id"]},
            {"$set": {"status": "expired", "payment_status": "expired", "updated_at": now().isoformat()}})
    elif t == "charge.refunded":
        await db.payment_transactions.update_one(
            {"stripe_payment_intent_id": obj.get("payment_intent")},
            {"$set": {"status": "refunded", "payment_status": "refunded", "updated_at": now().isoformat()}})
    return {"status": "ok"}


# ---------------- Pagamenti PayPal ----------------

def _paypal_token() -> str:
    r = requests.post(f"{PAYPAL_BASE}/v1/oauth2/token",
                      auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
                      data={"grant_type": "client_credentials"}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


class PayPalOrderRequest(BaseModel):
    lookup_key: str
    dossier_id: str
    slot_id: Optional[str] = None
    integration_type: Optional[str] = None


@api_router.post("/paypal/orders")
async def paypal_create_order(body: PayPalOrderRequest, user=Depends(get_current_user)):
    if not PAYPAL_CLIENT_ID or not PAYPAL_SECRET:
        raise HTTPException(status_code=500, detail="PayPal non configurato")
    if body.lookup_key not in PAYPAL_AMOUNTS:
        raise HTTPException(status_code=400, detail="Servizio non valido")
    dossier = await get_dossier_or_404(body.dossier_id, user)
    if body.lookup_key == "consulto_video":
        if not body.slot_id:
            raise HTTPException(status_code=400, detail="Seleziona uno slot per il consulto")
        slot = await db.slots.find_one({"slot_id": body.slot_id})
        if not slot or slot["status"] != "available":
            raise HTTPException(status_code=400, detail="Slot non più disponibile")
    if body.lookup_key == "integrazione_dossier":
        if dossier["status"] != "completato":
            raise HTTPException(status_code=400, detail="L'integrazione è disponibile solo per dossier completati")
        if dossier.get("integration_pending"):
            raise HTTPException(status_code=400, detail="Hai già un'integrazione in corso")
        if body.integration_type not in ("nuovi", "dimenticati"):
            raise HTTPException(status_code=400, detail="Tipo di integrazione non valido")
    value, description = PAYPAL_AMOUNTS[body.lookup_key]
    net, tax, total = paypal_totals(body.lookup_key)

    def _create():
        token = _paypal_token()
        r = requests.post(
            f"{PAYPAL_BASE}/v2/checkout/orders",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "reference_id": body.dossier_id,
                    "description": description,
                    "amount": {
                        "currency_code": "EUR",
                        "value": f"{total:.2f}",
                        "breakdown": {
                            "item_total": {"currency_code": "EUR", "value": f"{net:.2f}"},
                            "tax_total": {"currency_code": "EUR", "value": f"{tax:.2f}"},
                        },
                    },
                }],
            }, timeout=30)
        r.raise_for_status()
        return r.json()

    order = await asyncio.to_thread(_create)
    await db.payment_transactions.insert_one({
        "session_id": order["id"], "provider": "paypal", "user_id": user["user_id"],
        "dossier_id": body.dossier_id, "slot_id": body.slot_id,
        "integration_type": body.integration_type,
        "lookup_key": body.lookup_key, "amount": total, "currency": "eur",
        "status": "initiated", "payment_status": "pending",
        "created_at": now().isoformat(), "updated_at": now().isoformat()})
    return {"order_id": order["id"]}


@api_router.post("/paypal/orders/{order_id}/capture")
async def paypal_capture_order(order_id: str, user=Depends(get_current_user)):
    record = await db.payment_transactions.find_one({"session_id": order_id, "provider": "paypal"})
    if not record:
        raise HTTPException(status_code=404, detail="Ordine non trovato")
    if record.get("user_id") != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accesso non autorizzato")

    def _capture():
        token = _paypal_token()
        r = requests.post(
            f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30)
        r.raise_for_status()
        return r.json()

    try:
        result = await asyncio.to_thread(_capture)
    except requests.HTTPError as e:
        logger.error(f"PayPal capture failed: {e}")
        raise HTTPException(status_code=400, detail="Pagamento PayPal non riuscito")
    if result.get("status") != "COMPLETED":
        raise HTTPException(status_code=400, detail="Pagamento non completato")
    captures = result["purchase_units"][0].get("payments", {}).get("captures", [])
    if captures:
        _, _, expected_total = paypal_totals(record["lookup_key"])
        amt = captures[0]["amount"]
        if amt["value"] != f"{expected_total:.2f}" or amt.get("currency_code") != "EUR":
            raise HTTPException(status_code=400, detail="Importo non corrispondente")
    await mark_paid(order_id, {"paypal_capture_id": captures[0]["id"] if captures else None})
    return {"status": "paid"}


# ---------------- Consensi (registro per il medico) ----------------

@api_router.get("/admin/patients")
async def list_patients(user=Depends(require_admin)):
    patients = await db.users.find(
        {"role": {"$ne": "admin"}},
        {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    for p in patients:
        p["dossier_count"] = await db.dossiers.count_documents({"patient_id": p["user_id"]})
    return patients


@api_router.delete("/admin/patients/{user_id}")
async def delete_patient(user_id: str, user=Depends(require_admin)):
    target = await db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Paziente non trovato")
    if target.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Non puoi eliminare un account medico")
    await delete_patient_data(user_id)
    await db.users.delete_one({"user_id": user_id})
    await db.user_sessions.delete_many({"user_id": user_id})
    await send_account_deleted_email(target["email"], target.get("name", ""))
    return {"ok": True}


@api_router.get("/admin/emails")
async def list_emails(user=Depends(require_admin)):
    return await db.email_log.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@api_router.get("/admin/emails/export")
async def export_emails(user=Depends(require_admin)):
    rows = await db.email_log.find({}).sort("created_at", -1).to_list(5000)
    lines = ["data_ora_utc;destinatario;tipo;esito;oggetto;errore"]
    for e in rows:
        lines.append(";".join([
            _csv_safe(e.get("created_at")), _csv_safe(e.get("to")), _csv_safe(e.get("template")),
            _csv_safe(e.get("status")), _csv_safe(e.get("subject")),
            _csv_safe(e.get("error"))]))
    return Response(
        content="\n".join(lines).encode("utf-8"), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="registro_email_filochinico.csv"'})


async def send_consult_reminders():
    """Invia il promemoria per i consulti prenotati nelle prossime 24 ore."""
    soon = now() + timedelta(hours=24)
    slots = await db.slots.find({"status": "booked", "reminder_sent": {"$ne": True}}).to_list(500)
    for slot in slots:
        try:
            dt = datetime.fromisoformat(slot.get("datetime", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if not (now() < dt <= soon):
            continue
        dossier = await db.dossiers.find_one({"dossier_id": slot.get("dossier_id")})
        if not dossier or not dossier.get("patient_email"):
            continue
        await send_consult_reminder_email(
            dossier["patient_email"],
            dossier.get("patient_account_name") or dossier.get("patient_name", ""),
            slot.get("datetime", ""), slot.get("meet_link", ""))
        await db.slots.update_one({"slot_id": slot["slot_id"]},
                                  {"$set": {"reminder_sent": True, "updated_at": now().isoformat()}})


@api_router.post("/cron/consult-reminders")
async def cron_consult_reminders(request: Request, background_tasks: BackgroundTasks):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    if not secret or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="Non autorizzato")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload non valido")
    run_id = request.headers.get("X-Webhook-Id") or (body or {}).get("run_id") or uuid.uuid4().hex
    if await db.cron_runs.find_one({"run_id": run_id}):
        return {"ok": True, "duplicate": True}
    await db.cron_runs.insert_one({"run_id": run_id, "schedule": (body or {}).get("schedule_id", ""),
                                   "created_at": now().isoformat()})
    background_tasks.add_task(send_consult_reminders)
    return {"ok": True}


@api_router.get("/admin/consents")
async def list_consents(user=Depends(require_admin)):
    consents = await db.consents.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return consents


@api_router.get("/admin/consents/export")
async def export_consents(user=Depends(require_admin)):
    consents = await db.consents.find({}).sort("created_at", -1).to_list(2000)
    lines = ["email;user_id;versione_informativa;data_ora_utc;ip;user_agent"]
    for c in consents:
        lines.append(";".join([
            _csv_safe(c.get("email")), _csv_safe(c.get("user_id")), _csv_safe(c.get("version")),
            _csv_safe(c.get("created_at")), _csv_safe(c.get("ip")),
            _csv_safe(c.get("user_agent"))]))
    return Response(
        content="\n".join(lines).encode("utf-8"), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="consensi_filochinico.csv"'})


class ConsentRef(BaseModel):
    user_id: str
    created_at: str


class ConsentDeleteRequest(BaseModel):
    items: List[ConsentRef]


@api_router.post("/admin/consents/delete")
async def delete_consents(body: ConsentDeleteRequest, user=Depends(require_admin)):
    if not body.items:
        raise HTTPException(status_code=400, detail="Nessun consenso selezionato")
    res = await db.consents.delete_many(
        {"$or": [{"user_id": i.user_id, "created_at": i.created_at} for i in body.items]})
    return {"ok": True, "deleted": res.deleted_count}


# ---------------- Slot consulto video ----------------

class SlotCreate(BaseModel):
    datetime: str
    meet_link: str = ""


class SlotUpdate(BaseModel):
    meet_link: str


@api_router.get("/slots")
async def list_slots(user=Depends(get_current_user)):
    query = {} if user.get("role") == "admin" else {"status": "available"}
    slots = await db.slots.find(query, {"_id": 0}).sort("datetime", 1).to_list(200)
    return slots


@api_router.post("/slots")
async def create_slot(body: SlotCreate, user=Depends(require_admin)):
    slot_id = f"slot_{uuid.uuid4().hex[:12]}"
    doc = {"slot_id": slot_id, "datetime": body.datetime, "meet_link": body.meet_link,
           "status": "available", "booked_by": None, "dossier_id": None,
           "created_at": now().isoformat(), "updated_at": now().isoformat()}
    await db.slots.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.delete("/slots/{slot_id}")
async def delete_slot(slot_id: str, user=Depends(require_admin)):
    slot = await db.slots.find_one({"slot_id": slot_id})
    if not slot:
        raise HTTPException(status_code=404, detail="Slot non trovato")
    if slot["status"] == "booked":
        raise HTTPException(status_code=400, detail="Non puoi eliminare uno slot prenotato")
    await db.slots.delete_one({"slot_id": slot_id})
    return {"ok": True}


@api_router.put("/slots/{slot_id}")
async def update_slot(slot_id: str, body: SlotUpdate, user=Depends(require_admin)):
    """Aggiorna il link Meet dello slot. Se lo slot è prenotato, il paziente
    riceve l'email di conferma con link, giorno e ora del consulto."""
    slot = await db.slots.find_one({"slot_id": slot_id})
    if not slot:
        raise HTTPException(status_code=404, detail="Slot non trovato")
    meet_link = body.meet_link.strip()
    await db.slots.update_one({"slot_id": slot_id},
                              {"$set": {"meet_link": meet_link, "updated_at": now().isoformat()}})
    if slot["status"] == "booked" and meet_link:
        dossier = await db.dossiers.find_one({"dossier_id": slot.get("dossier_id")})
        if dossier and dossier.get("patient_email"):
            await send_consult_booked_email(
                dossier["patient_email"],
                dossier.get("patient_account_name") or dossier.get("patient_name", ""),
                slot.get("datetime", ""), meet_link)
    return clean(await db.slots.find_one({"slot_id": slot_id}))


@api_router.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(api_router)

cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
for default_origin in ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001", FRONTEND_URL]:
    if default_origin and default_origin not in cors_origins:
        cors_origins.append(default_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def seed_users():
    admin_email = ADMIN_EMAIL
    admin_password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "user_id": f"user_{uuid.uuid4().hex[:12]}", "email": admin_email,
            "name": "Dott. Pietro Spitaleri", "role": "admin",
            "password_hash": hash_password(admin_password),
            "auth_provider": "email", "created_at": now().isoformat()})
    elif existing.get("role") != "admin":
        await db.users.update_one({"email": admin_email}, {"$set": {"role": "admin"}})
    test_email = "mario.rossi@test.it"
    if await db.users.find_one({"email": test_email}) is None:
        await db.users.insert_one({
            "user_id": f"user_{uuid.uuid4().hex[:12]}", "email": test_email,
            "name": "Mario Rossi", "role": "patient",
            "password_hash": hash_password("Test1234!"),
            "auth_provider": "email", "created_at": now().isoformat()})


@app.on_event("startup")
async def startup():
    await init_pool()
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.user_sessions.create_index("session_token")
    await db.login_attempts.create_index("identifier")
    await db.dossiers.create_index("dossier_id", unique=True)
    await db.slots.create_index("slot_id", unique=True)
    await db.password_resets.create_index("token", unique=True)
    await db.payment_transactions.create_index("session_id", unique=True)
    try:
        init_storage()
        logger.info("Object storage inizializzato")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    await seed_users()


@app.on_event("shutdown")
async def shutdown_db_client():
    await close_pool()
