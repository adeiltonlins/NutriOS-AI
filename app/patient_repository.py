"""Consultas de pacientes com isolamento obrigatório por nutricionista."""
from __future__ import annotations

from app import saas_store


def _clean_search_term(value: str, limit: int = 80) -> str:
    """Normaliza entrada para filtros PostgREST sem permitir operadores extras."""
    return value.replace("*", "").replace(",", " ").replace("(", " ").replace(")", " ").strip()[:limit]


def search_patients_for_client(client_id: str, query: str, limit: int = 8) -> list[dict]:
    term = _clean_search_term(query)
    if len(term) < 2:
        return []

    safe_limit = max(1, min(int(limit), 8))
    params = {
        "select": "id,name,identifier,phone",
        "client_id": f"eq.{client_id}",
        "or": f"(name.ilike.*{term}*,identifier.ilike.*{term}*,phone.ilike.*{term}*)",
        "order": "name.asc",
        "limit": str(safe_limit),
    }
    rows = saas_store._request("GET", "patient_accounts", params=params) or []
    return rows[:safe_limit]


def serialize_patient_search_item(row: dict) -> dict:
    identifier = row.get("identifier")
    return {
        "id": row.get("id"),
        "name": row.get("name") or "Paciente",
        "identifier": identifier,
        "phone": row.get("phone"),
        "email": identifier if identifier and "@" in str(identifier) else None,
    }
