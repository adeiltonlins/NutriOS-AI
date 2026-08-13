"""Acesso temporário de pacientes ao canal privado de acompanhamento."""
from __future__ import annotations
import hashlib, hmac, os, secrets
from datetime import datetime, timedelta, timezone
from fastapi import Cookie, HTTPException, Request, Response
from app import saas_store
from app.auth import hash_password, verify_password

COOKIE_NAME = "nutribot_patient_session"
SECRET = os.getenv("SESSION_SECRET") or os.getenv("APP_TOKEN_SECRET", "")
SESSION_SECONDS = int(os.getenv("PATIENT_SESSION_DURATION", "2592000"))

def _digest(value: str, purpose: str) -> str:
    if len(SECRET) < 32: raise RuntimeError("SESSION_SECRET deve ter pelo menos 32 caracteres")
    return hmac.new(SECRET.encode(), f"patient:{purpose}:{value}".encode(), hashlib.sha256).hexdigest()

def _lookup(value: str, purpose: str) -> str:
    return hashlib.sha256(f"patient:{purpose}:{value}".encode()).hexdigest()

def generate_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    body = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"PACI-{body[:4]}-{body[4:]}"

def issue_code(patient_id: str, hours: int = 24) -> str:
    raw = generate_code(); now = datetime.now(timezone.utc)
    saas_store._request("PATCH", "patient_access_codes", params={"patient_id":f"eq.{patient_id}","revoked_at":"is.null"}, payload={"revoked_at":now.isoformat()}, prefer="return=minimal")
    saas_store._request("POST", "patient_access_codes", payload={"patient_id":patient_id,"code_hash":_digest(raw,"code"),"code_lookup":_lookup(raw,"code"),"expires_at":(now+timedelta(hours=hours)).isoformat()}, prefer="return=minimal")
    return raw

def authenticate(code: str) -> dict | None:
    normalized=code.strip().upper(); now=datetime.now(timezone.utc)
    rows=saas_store._request("GET","patient_access_codes",params={"select":"*","code_lookup":f"eq.{_lookup(normalized,'code')}","revoked_at":"is.null","used_at":"is.null","limit":"1"}) or []
    if not rows: return None
    row=rows[0]
    if datetime.fromisoformat(row["expires_at"].replace("Z","+00:00")) <= now or not hmac.compare_digest(row["code_hash"],_digest(normalized,"code")): return None
    patient=(saas_store._request("GET","patient_accounts",params={"select":"*","id":f"eq.{row['patient_id']}","limit":"1"}) or [None])[0]
    if not patient or not patient.get("active") or patient.get("archived_at") or datetime.fromisoformat(patient["access_expires_at"].replace("Z","+00:00")) <= now: return None
    saas_store._request("PATCH","patient_access_codes",params={"id":f"eq.{row['id']}"},payload={"used_at":now.isoformat()},prefer="return=minimal")
    return patient

def authenticate_password(identifier: str, password: str) -> dict | None:
    """Autentica somente pacientes ativos e dentro da validade contratada."""
    normalized = identifier.strip().lower()
    if not normalized or not password:
        return None
    rows = saas_store._request(
        "GET", "patient_accounts",
        params={"select": "*", "login_identifier": f"eq.{normalized}", "active": "eq.true", "archived_at": "is.null", "limit": "1"},
    ) or []
    if not rows:
        return None
    patient = rows[0]
    if datetime.fromisoformat(patient["access_expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        return None
    return patient if verify_password(patient.get("password_hash"), password) else None

def set_credentials(patient: dict, identifier: str, password: str) -> dict:
    """Conclui o primeiro acesso sem expor senha ou código em texto puro."""
    normalized = identifier.strip().lower()
    if len(normalized) < 4 or len(normalized) > 160:
        raise ValueError("Use um e-mail ou identificador com pelo menos 4 caracteres")
    existing = saas_store._request(
        "GET", "patient_accounts",
        params={"select": "id", "login_identifier": f"eq.{normalized}", "id": f"neq.{patient['id']}", "limit": "1"},
    ) or []
    if existing:
        raise ValueError("Este identificador já está em uso")
    rows = saas_store._request(
        "PATCH", "patient_accounts", params={"id": f"eq.{patient['id']}"},
        payload={"login_identifier": normalized, "password_hash": hash_password(password), "password_created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()},
        prefer="return=representation",
    ) or []
    return rows[0] if rows else patient

def create_session(patient: dict, response: Response):
    raw=secrets.token_urlsafe(48); now=datetime.now(timezone.utc); plan_end=datetime.fromisoformat(patient["access_expires_at"].replace("Z","+00:00")); expires=min(now+timedelta(seconds=SESSION_SECONDS),plan_end)
    saas_store._request("POST","patient_sessions",payload={"patient_id":patient["id"],"token_hash":_digest(raw,"session"),"token_lookup":_lookup(raw,"session"),"expires_at":expires.isoformat()},prefer="return=minimal")
    response.set_cookie(COOKIE_NAME,raw,max_age=max(0,int((expires-now).total_seconds())),httponly=True,secure=os.getenv("COOKIE_SECURE","true").lower()=="true",samesite=os.getenv("COOKIE_SAMESITE","lax"),path="/")

def current_patient(request: Request, token: str|None=Cookie(default=None,alias=COOKIE_NAME)) -> dict:
    if not token: raise HTTPException(401,"Acesso do paciente necessário")
    rows=saas_store._request("GET","patient_sessions",params={"select":"*","token_lookup":f"eq.{_lookup(token,'session')}","revoked_at":"is.null","limit":"1"}) or []
    if not rows or not hmac.compare_digest(rows[0]["token_hash"],_digest(token,"session")): raise HTTPException(401,"Sessão inválida")
    session=rows[0]; now=datetime.now(timezone.utc)
    patient=(saas_store._request("GET","patient_accounts",params={"select":"*","id":f"eq.{session['patient_id']}","limit":"1"}) or [None])[0]
    if not patient or not patient.get("active") or patient.get("archived_at") or datetime.fromisoformat(session["expires_at"].replace("Z","+00:00"))<=now or datetime.fromisoformat(patient["access_expires_at"].replace("Z","+00:00"))<=now: raise HTTPException(403,"Acompanhamento encerrado. Solicite a renovação ao seu nutricionista.")
    saas_store._request("PATCH","patient_sessions",params={"id":f"eq.{session['id']}"},payload={"last_seen_at":now.isoformat()},prefer="return=minimal")
    return patient

def revoke(patient_id: str):
    now=datetime.now(timezone.utc).isoformat()
    saas_store._request("PATCH","patient_sessions",params={"patient_id":f"eq.{patient_id}","revoked_at":"is.null"},payload={"revoked_at":now},prefer="return=minimal")
    saas_store._request("PATCH","patient_access_codes",params={"patient_id":f"eq.{patient_id}","revoked_at":"is.null"},payload={"revoked_at":now},prefer="return=minimal")

def logout(response: Response): response.delete_cookie(COOKIE_NAME,path="/")
