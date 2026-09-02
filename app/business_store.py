"""Persistência dos módulos comerciais do SaaS via Supabase/PostgREST."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app import saas_store


def organization_id_for_user(user_id: str) -> str:
    """Resolve a organização ativa do profissional autenticado."""
    rows = saas_store._request(
        "GET",
        "organization_members",
        params={"select": "organization_id", "user_id": f"eq.{user_id}", "is_active": "eq.true", "limit": "1"},
    ) or []
    if rows:
        return str(rows[0]["organization_id"])
    owned = saas_store._request(
        "GET",
        "organizations",
        params={"select": "id", "owner_user_id": f"eq.{user_id}", "is_active": "eq.true", "limit": "1"},
    ) or []
    if owned:
        return str(owned[0]["id"])
    raise HTTPException(403, "Organização ativa não encontrada para este usuário")


def _organization_or_none(user_id: str) -> str | None:
    try:
        return organization_id_for_user(user_id)
    except Exception:
        return None


def list_rows(table: str, client_id: str, *, order: str = "created_at.desc", extra: dict | None = None) -> list[dict]:
    """Lê tabelas novas por organization_id e mantém fallback para client_id legado."""
    organization_id = _organization_or_none(client_id)
    if organization_id:
        try:
            params = {"select": "*", "organization_id": f"eq.{organization_id}", "order": order}
            params.update(extra or {})
            return saas_store._request("GET", table, params=params) or []
        except Exception:
            pass
    params = {"select": "*", "client_id": f"eq.{client_id}", "order": order}
    params.update(extra or {})
    return saas_store._request("GET", table, params=params) or []


def get_row(table: str, row_id: str, client_id: str) -> dict | None:
    organization_id = _organization_or_none(client_id)
    if organization_id:
        try:
            rows = saas_store._request("GET", table, params={"select": "*", "id": f"eq.{row_id}", "organization_id": f"eq.{organization_id}", "limit": "1"}) or []
            return rows[0] if rows else None
        except Exception:
            pass
    rows = saas_store._request("GET", table, params={"select": "*", "id": f"eq.{row_id}", "client_id": f"eq.{client_id}", "limit": "1"}) or []
    return rows[0] if rows else None


def create_row(table: str, client_id: str, payload: dict) -> dict:
    organization_id = _organization_or_none(client_id)
    if organization_id:
        try:
            data = dict(payload)
            data["organization_id"] = organization_id
            rows = saas_store._request("POST", table, payload=data, prefer="return=representation") or []
            if rows:
                return rows[0]
        except Exception:
            pass
    data = dict(payload)
    data["client_id"] = client_id
    rows = saas_store._request("POST", table, payload=data, prefer="return=representation") or []
    if not rows:
        raise HTTPException(500, "Não foi possível criar o registro")
    return rows[0]


def update_row(table: str, row_id: str, client_id: str, payload: dict) -> dict | None:
    organization_id = _organization_or_none(client_id)
    if organization_id:
        try:
            rows = saas_store._request(
                "PATCH", table,
                params={"id": f"eq.{row_id}", "organization_id": f"eq.{organization_id}"},
                payload=payload, prefer="return=representation",
            ) or []
            return rows[0] if rows else None
        except Exception:
            pass
    rows = saas_store._request("PATCH", table, params={"id": f"eq.{row_id}", "client_id": f"eq.{client_id}"}, payload=payload, prefer="return=representation") or []
    return rows[0] if rows else None


def delete_row(table: str, row_id: str, client_id: str) -> None:
    organization_id = _organization_or_none(client_id)
    if organization_id:
        try:
            saas_store._request("DELETE", table, params={"id": f"eq.{row_id}", "organization_id": f"eq.{organization_id}"}, prefer="return=minimal")
            return
        except Exception:
            pass
    saas_store._request("DELETE", table, params={"id": f"eq.{row_id}", "client_id": f"eq.{client_id}"}, prefer="return=minimal")


def list_org_rows(table: str, organization_id: str, *, order: str = "created_at.desc", extra: dict | None = None) -> list[dict]:
    params = {"select": "*", "organization_id": f"eq.{organization_id}", "order": order}
    params.update(extra or {})
    return saas_store._request("GET", table, params=params) or []


def get_org_row(table: str, row_id: str, organization_id: str) -> dict | None:
    rows = saas_store._request("GET", table, params={"select": "*", "id": f"eq.{row_id}", "organization_id": f"eq.{organization_id}", "limit": "1"}) or []
    return rows[0] if rows else None


def create_org_row(table: str, organization_id: str, payload: dict) -> dict:
    data = dict(payload)
    data["organization_id"] = organization_id
    rows = saas_store._request("POST", table, payload=data, prefer="return=representation") or []
    if not rows:
        raise HTTPException(500, "Não foi possível criar o registro")
    return rows[0]


def update_org_row(table: str, row_id: str, organization_id: str, payload: dict) -> dict | None:
    rows = saas_store._request("PATCH", table, params={"id": f"eq.{row_id}", "organization_id": f"eq.{organization_id}"}, payload=payload, prefer="return=representation") or []
    return rows[0] if rows else None


def delete_org_row(table: str, row_id: str, organization_id: str) -> None:
    saas_store._request("DELETE", table, params={"id": f"eq.{row_id}", "organization_id": f"eq.{organization_id}"}, prefer="return=minimal")


def upsert_anamnesis(client_id: str, session_id: str, payload: dict) -> dict:
    data = {"client_id": client_id, "session_id": session_id, **payload}
    rows = saas_store._request("POST", "anamneses", params={"on_conflict": "client_id,session_id"}, payload=data, prefer="resolution=merge-duplicates,return=representation")
    return rows[0]


def audit(actor_id: str | None, client_id: str | None, action: str, resource_type: str = "", resource_id: str = "", metadata: dict | None = None) -> None:
    try:
        saas_store._request("POST", "audit_logs", payload={"actor_id": actor_id, "client_id": client_id, "action": action, "resource_type": resource_type, "resource_id": resource_id, "metadata": metadata or {}}, prefer="return=minimal")
    except Exception as exc:
        print(f"[audit] Falha ao registrar evento: {exc}")
