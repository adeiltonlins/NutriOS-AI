"""Regression tests for authenticated, tenant-scoped dashboard search."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import auth, dashboard_search, patient_repository


CLIENT = {"id": "tenant-a", "role": "client", "active": True}
ADMIN = {"id": "admin-1", "role": "admin", "active": True}


def test_admin_cannot_use_nutritionist_dependency():
    with pytest.raises(HTTPException) as exc:
        auth.require_nutritionist(ADMIN)
    assert exc.value.status_code == 403


def test_search_is_scoped_to_authenticated_client(monkeypatch):
    calls = []

    def fake_request(method, table, params=None, **kwargs):
        calls.append((method, table, dict(params or {})))
        return [{"id": "p1", "client_id": "tenant-a", "name": "Maria", "identifier": "maria@example.com", "phone": "81999999999"}]

    monkeypatch.setattr(patient_repository.saas_store, "_request", fake_request)
    result = dashboard_search.search_patients("Maria", CLIENT)

    assert result["items"][0]["email"] == "maria@example.com"
    assert calls[0][0] == "GET"
    assert calls[0][1] == "patient_accounts"
    assert calls[0][2]["client_id"] == "eq.tenant-a"
    assert calls[0][2]["limit"] == "8"


def test_search_never_returns_more_than_eight(monkeypatch):
    rows = [{"id": f"p{i}", "name": f"Paciente {i}", "identifier": None, "phone": None} for i in range(20)]
    monkeypatch.setattr(patient_repository.saas_store, "_request", lambda *a, **k: rows)
    result = dashboard_search.search_patients("Paciente", CLIENT)
    assert len(result["items"]) == 8


def test_short_or_operator_only_query_does_not_hit_database(monkeypatch):
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("database should not be queried")

    monkeypatch.setattr(patient_repository.saas_store, "_request", fail_if_called)
    assert dashboard_search.search_patients("*", CLIENT) == {"items": []}
    assert called is False
