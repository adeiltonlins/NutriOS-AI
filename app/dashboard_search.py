"""Busca rápida de pacientes para o dashboard profissional."""
from __future__ import annotations

from fastapi import Depends, Query

from app import auth, clinical_extensions, saas_store

router = clinical_extensions.router


@router.get("/app/api/pacientes")
def search_patients(
    q: str = Query(default="", max_length=80),
    user: dict = Depends(auth.require_nutritionist),
):
    term = q.strip()
    if len(term) < 2:
        return {"items": []}

    safe_term = term.replace("*", "").replace(",", " ").strip()[:80]
    if len(safe_term) < 2:
        return {"items": []}

    params = {
        "select": "id,name,identifier,phone",
        "client_id": f"eq.{user['id']}",
        "or": f"(name.ilike.*{safe_term}*,identifier.ilike.*{safe_term}*,phone.ilike.*{safe_term}*)",
        "order": "name.asc",
        "limit": "8",
    }
    rows = saas_store._request("GET", "patient_accounts", params=params) or []

    items = []
    for row in rows[:8]:
        identifier = row.get("identifier")
        items.append({
            "id": row.get("id"),
            "name": row.get("name") or "Paciente",
            "identifier": identifier,
            "phone": row.get("phone"),
            "email": identifier if identifier and "@" in str(identifier) else None,
        })
    return {"items": items}
