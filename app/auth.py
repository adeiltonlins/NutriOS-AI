"""Códigos temporários, sessões opacas em cookie e dependências RBAC."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException, Request, Response
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app import saas_store

COOKIE_NAME = "nutribot_session"
SESSION_SECONDS = int(os.getenv("SESSION_DURATION", "28800"))
CODE_MAX_ATTEMPTS = int(os.getenv("ACCESS_CODE_MAX_ATTEMPTS", "5"))
SECRET = os.getenv("SESSION_SECRET") or os.getenv("APP_TOKEN_SECRET", "")
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def _require_secret() -> bytes:
    if len(SECRET) < 32:
        raise RuntimeError("SESSION_SECRET deve ter pelo menos 32 caracteres")
    return SECRET.encode()


def _digest(value: str, purpose: str) -> str:
    return hmac.new(_require_secret(), f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def _lookup(value: str, purpose: str) -> str:
    return hashlib.sha256(f"{purpose}:{value}".encode()).hexdigest()


def generate_access_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    body = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"NTRI-{body[:4]}-{body[4:]}"


def issue_code(user_id: str, expires_at: datetime, created_by: str) -> str:
    raw = generate_access_code()
    saas_store.revoke_codes(user_id)
    saas_store.insert_access_code({
        "user_id": user_id, "code_hash": _digest(raw, "code"), "code_lookup": _lookup(raw, "code"),
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(), "max_attempts": CODE_MAX_ATTEMPTS,
        "created_by": created_by,
    })
    return raw


def authenticate_code(raw_code: str) -> dict | None:
    normalized = raw_code.strip().upper()
    now = datetime.now(timezone.utc)
    for code in saas_store.find_active_codes(_lookup(normalized, "code")):
        expires = datetime.fromisoformat(code["expires_at"].replace("Z", "+00:00"))
        attempts = int(code.get("attempts") or 0)
        if code.get("used_at") or expires <= now or attempts >= int(code.get("max_attempts") or CODE_MAX_ATTEMPTS):
            continue
        if not hmac.compare_digest(code["code_hash"], _digest(normalized, "code")):
            saas_store.update_code(code["id"], {"attempts": attempts + 1})
            continue
        user = saas_store.get_user(code["user_id"])
        if not user or not user.get("active"):
            return None
        saas_store.update_code(code["id"], {"used_at": now.isoformat()})
        user["_grant_expires_at"] = expires.isoformat()
        return user
    return None


def authenticate_master(raw_code: str) -> dict | None:
    """Acesso permanente do ADMIN mestre, mantido somente no backend."""
    expected = os.getenv("ADMIN_TOKEN", "")
    if not expected or not secrets.compare_digest(raw_code.strip(), expected):
        return None
    user = saas_store.get_user_by_identifier(os.getenv("ADMIN_IDENTIFIER", "admin").lower())
    return user if user and user.get("role") == "admin" and user.get("active") else None


def authenticate_password(identifier: str, password: str) -> dict | None:
    user = saas_store.get_user_by_identifier(identifier)
    if not user or user.get("role") != "client" or not user.get("active") or not user.get("password_hash"):
        return None
    try:
        if not PASSWORD_HASHER.verify(user["password_hash"], password):
            return None
    except (VerifyMismatchError, InvalidHashError):
        return None
    return user


def hash_password(password: str) -> str:
    if len(password) < 10 or len(password) > 128:
        raise ValueError("A senha deve ter entre 10 e 128 caracteres")
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return bool(PASSWORD_HASHER.verify(password_hash, password))
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_session(user: dict, response: Response) -> None:
    raw = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    session_expires = now + timedelta(seconds=SESSION_SECONDS)
    if user.get("_grant_expires_at"):
        grant_expires = datetime.fromisoformat(user["_grant_expires_at"].replace("Z", "+00:00"))
        session_expires = min(session_expires, grant_expires)
    saas_store.create_session({
        "user_id": user["id"], "session_token_hash": _digest(raw, "session"),
        "token_lookup": _lookup(raw, "session"), "role": user["role"],
        "expires_at": session_expires.isoformat(),
    })
    response.set_cookie(COOKIE_NAME, raw, max_age=SESSION_SECONDS, httponly=True,
                        secure=os.getenv("COOKIE_SECURE", "true").lower() == "true",
                        samesite=os.getenv("COOKIE_SAMESITE", "lax"), path="/")


def user_from_token(request: Request, token: str | None) -> dict:
    if not token:
        raise HTTPException(401, "Sessão necessária")
    session = saas_store.find_session(_lookup(token, "session"))
    if not session or not hmac.compare_digest(session["session_token_hash"], _digest(token, "session")):
        raise HTTPException(401, "Sessão inválida")
    now = datetime.now(timezone.utc)
    if datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00")) <= now:
        saas_store.revoke_session(session["id"])
        raise HTTPException(401, "Sessão expirada")
    user = saas_store.get_user(session["user_id"])
    if not user or not user.get("active"):
        saas_store.revoke_session(session["id"])
        raise HTTPException(403, "Acesso bloqueado")
    if user.get("expires_at") and datetime.fromisoformat(user["expires_at"].replace("Z", "+00:00")) <= now:
        saas_store.revoke_session(session["id"])
        raise HTTPException(403, "Acesso expirado")
    saas_store.touch_session(session["id"])
    request.state.auth_session_id = session["id"]
    return user


def current_user(request: Request, token: str | None = Cookie(default=None, alias=COOKIE_NAME)) -> dict:
    return user_from_token(request, token)


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Acesso administrativo necessário")
    return user


def logout(request: Request, response: Response, token: str | None = Cookie(default=None, alias=COOKIE_NAME)) -> None:
    if token:
        session = saas_store.find_session(_lookup(token, "session"))
        if session:
            saas_store.revoke_session(session["id"])
    response.delete_cookie(COOKIE_NAME, path="/")
