"""Fast CI coverage for RBAC and tenant-scoped repositories without external services."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import auth, business_store, patient_repository

CLIENT_A = {"id": "tenant-a", "role": "client", "active": True}
CLIENT_B = {"id": "tenant-b", "role": "client", "active": True}
ADMIN = {"id": "admin", "role": "admin", "active": True}


def test_rbac_dependencies_reject_wrong_roles():
    with pytest.raises(HTTPException) as exc:
        auth.require_admin(CLIENT_A)
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        auth.require_nutritionist(ADMIN)
    assert exc.value.status_code == 403


def test_patient_repository_always_scopes_query_to_client(monkeypatch):
    calls = []

    def spy(method, table, params=None, **kwargs):
        calls.append((method, table, dict(params or {})))
        return []

    monkeypatch.setattr(patient_repository.saas_store, "_request", spy)
    patient_repository.search_patients_for_client(CLIENT_A["id"], "Maria")
    assert calls[0][1] == "patient_accounts"
    assert calls[0][2]["client_id"] == "eq.tenant-a"
    assert calls[0][2]["limit"] == "8"


def test_business_store_reads_and_writes_include_client_id(monkeypatch):
    calls = []

    def spy(method, table, params=None, payload=None, prefer=None, **kwargs):
        calls.append((method, table, dict(params or {}), payload))
        return []

    monkeypatch.setattr(business_store.saas_store, "_request", spy)
    business_store.list_rows("meal_plans", CLIENT_A["id"])
    business_store.get_row("meal_plans", "plan-b", CLIENT_A["id"])
    business_store.update_row("meal_plans", "plan-b", CLIENT_A["id"], {"title": "x"})
    business_store.delete_row("meal_plans", "plan-b", CLIENT_A["id"])

    for method, _table, params, _payload in calls:
        if method in {"GET", "PATCH", "DELETE"}:
            assert params.get("client_id") == "eq.tenant-a"
