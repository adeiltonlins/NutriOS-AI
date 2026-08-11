"""Persistência SaaS no Supabase via PostgREST, isolada do armazenamento legado."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ATIVO = bool(SUPABASE_URL and SUPABASE_KEY)


def _headers(prefer: str | None = None) -> dict[str, str]:
    value = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    if prefer:
        value["Prefer"] = prefer
    return value


def _request(method: str, table: str, *, params=None, payload=None, prefer=None) -> Any:
    if not ATIVO:
        raise RuntimeError("Supabase não configurado")
    response = requests.request(method, f"{SUPABASE_URL}/rest/v1/{table}", headers=_headers(prefer), params=params, json=payload, timeout=8)
    response.raise_for_status()
    return response.json() if response.content else None


def upload_public_asset(bucket: str, object_path: str, content: bytes, content_type: str) -> str:
    if not ATIVO:
        raise RuntimeError("Supabase não configurado")
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": content_type, "x-upsert": "true"}
    response = requests.put(f"{SUPABASE_URL}/storage/v1/object/{bucket}/{object_path}", headers=headers, data=content, timeout=15)
    response.raise_for_status()
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{object_path}"


def upload_private_asset(bucket: str, object_path: str, content: bytes, content_type: str) -> str:
    """Envia um objeto privado. Retorna somente o caminho interno, nunca uma URL pública."""
    if not ATIVO:
        raise RuntimeError("Supabase não configurado")
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": content_type, "x-upsert": "false"}
    response = requests.post(f"{SUPABASE_URL}/storage/v1/object/{bucket}/{object_path}", headers=headers, data=content, timeout=30)
    response.raise_for_status()
    return object_path


def download_private_asset(bucket: str, object_path: str) -> bytes:
    if not ATIVO:
        raise RuntimeError("Supabase não configurado")
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    response = requests.get(f"{SUPABASE_URL}/storage/v1/object/authenticated/{bucket}/{object_path}", headers=headers, timeout=30)
    response.raise_for_status()
    return response.content


def delete_private_asset(bucket: str, object_path: str) -> None:
    if not ATIVO:
        raise RuntimeError("Supabase não configurado")
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    response = requests.delete(f"{SUPABASE_URL}/storage/v1/object/{bucket}/{object_path}", headers=headers, timeout=30)
    if response.status_code not in {200, 204, 404}:
        response.raise_for_status()


def get_user(user_id: str) -> dict | None:
    rows = _request("GET", "saas_users", params={"select": "*", "id": f"eq.{user_id}", "limit": "1"})
    return rows[0] if rows else None


def get_user_by_identifier(identifier: str) -> dict | None:
    rows = _request("GET", "saas_users", params={"select": "*", "identifier": f"eq.{identifier.lower().strip()}", "limit": "1"})
    return rows[0] if rows else None


def get_user_by_slug(public_slug: str) -> dict | None:
    rows = _request("GET", "saas_users", params={"select": "*", "public_slug": f"eq.{public_slug.lower().strip()}", "limit": "1"})
    return rows[0] if rows else None


def list_users() -> list[dict]:
    return _request("GET", "saas_users", params={"select": "*", "order": "created_at.desc"}) or []


def create_user(payload: dict) -> dict:
    rows = _request("POST", "saas_users", payload=payload, prefer="return=representation")
    return rows[0]


def update_user(user_id: str, payload: dict) -> dict | None:
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    rows = _request("PATCH", "saas_users", params={"id": f"eq.{user_id}"}, payload=payload, prefer="return=representation")
    return rows[0] if rows else None


def delete_user(user_id: str) -> None:
    _request("DELETE", "saas_users", params={"id": f"eq.{user_id}"}, prefer="return=minimal")


def insert_access_code(payload: dict) -> dict:
    rows = _request("POST", "access_codes", payload=payload, prefer="return=representation")
    return rows[0]


def find_active_codes(code_lookup: str) -> list[dict]:
    return _request("GET", "access_codes", params={"select": "*", "code_lookup": f"eq.{code_lookup}", "revoked_at": "is.null", "order": "created_at.desc"}) or []


def update_code(code_id: str, payload: dict) -> None:
    _request("PATCH", "access_codes", params={"id": f"eq.{code_id}"}, payload=payload, prefer="return=minimal")


def revoke_codes(user_id: str) -> None:
    _request("PATCH", "access_codes", params={"user_id": f"eq.{user_id}", "revoked_at": "is.null"}, payload={"revoked_at": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")


def create_session(payload: dict) -> None:
    _request("POST", "user_sessions", payload=payload, prefer="return=minimal")


def find_session(token_lookup: str) -> dict | None:
    rows = _request("GET", "user_sessions", params={"select": "*", "token_lookup": f"eq.{token_lookup}", "revoked_at": "is.null", "limit": "1"})
    return rows[0] if rows else None


def touch_session(session_id: str) -> None:
    _request("PATCH", "user_sessions", params={"id": f"eq.{session_id}"}, payload={"last_seen_at": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")


def revoke_session(session_id: str) -> None:
    _request("PATCH", "user_sessions", params={"id": f"eq.{session_id}"}, payload={"revoked_at": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")


def revoke_user_sessions(user_id: str) -> None:
    _request("PATCH", "user_sessions", params={"user_id": f"eq.{user_id}", "revoked_at": "is.null"}, payload={"revoked_at": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")
