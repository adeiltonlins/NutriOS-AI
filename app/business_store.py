"""Persistência dos módulos comerciais do SaaS via Supabase/PostgREST."""
from __future__ import annotations

from typing import Any

from app import saas_store


def list_rows(table: str, client_id: str, *, order: str = "created_at.desc", extra: dict | None = None) -> list[dict]:
    params = {"select": "*", "client_id": f"eq.{client_id}", "order": order}
    params.update(extra or {})
    return saas_store._request("GET", table, params=params) or []


def get_row(table: str, row_id: str, client_id: str) -> dict | None:
    rows = saas_store._request("GET", table, params={"select": "*", "id": f"eq.{row_id}", "client_id": f"eq.{client_id}", "limit": "1"}) or []
    return rows[0] if rows else None


def create_row(table: str, client_id: str, payload: dict) -> dict:
    data = dict(payload)
    data["client_id"] = client_id
    rows = saas_store._request("POST", table, payload=data, prefer="return=representation")
    return rows[0]


def update_row(table: str, row_id: str, client_id: str, payload: dict) -> dict | None:
    rows = saas_store._request("PATCH", table, params={"id": f"eq.{row_id}", "client_id": f"eq.{client_id}"}, payload=payload, prefer="return=representation")
    return rows[0] if rows else None


def delete_row(table: str, row_id: str, client_id: str) -> None:
    saas_store._request("DELETE", table, params={"id": f"eq.{row_id}", "client_id": f"eq.{client_id}"}, prefer="return=minimal")


def upsert_anamnesis(client_id: str, session_id: str, payload: dict) -> dict:
    data = {"client_id": client_id, "session_id": session_id, **payload}
    rows = saas_store._request("POST", "anamneses", params={"on_conflict": "client_id,session_id"}, payload=data, prefer="resolution=merge-duplicates,return=representation")
    return rows[0]


def audit(actor_id: str | None, client_id: str | None, action: str, resource_type: str = "", resource_id: str = "", metadata: dict | None = None) -> None:
    try:
        saas_store._request("POST", "audit_logs", payload={"actor_id": actor_id, "client_id": client_id, "action": action, "resource_type": resource_type, "resource_id": resource_id, "metadata": metadata or {}}, prefer="return=minimal")
    except Exception as exc:
        print(f"[audit] Falha ao registrar evento: {exc}")
