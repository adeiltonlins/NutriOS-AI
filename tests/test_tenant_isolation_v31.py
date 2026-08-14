"""Security regression tests: tenant isolation / IDOR.

These tests model two nutritionist accounts (tenant-a and tenant-b). They verify
that tenant-a cannot read or mutate resources owned by tenant-b merely by
changing UUID/path parameters.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Test-only stubs for optional runtime integrations unavailable in the QA container.
# Production still uses the real packages declared in requirements.txt.
import sys, types
if "slowapi" not in sys.modules:
    slowapi = types.ModuleType("slowapi")
    class _Limiter:
        def __init__(self, *a, **k): pass
        def limit(self, *a, **k):
            def deco(fn):
                return fn
            return deco
    slowapi.Limiter = _Limiter
    slowapi._rate_limit_exceeded_handler = lambda *a, **k: None
    util = types.ModuleType("slowapi.util"); util.get_remote_address = lambda request: "127.0.0.1"
    errors = types.ModuleType("slowapi.errors")
    class RateLimitExceeded(Exception): pass
    errors.RateLimitExceeded = RateLimitExceeded
    sys.modules["slowapi"] = slowapi; sys.modules["slowapi.util"] = util; sys.modules["slowapi.errors"] = errors
if "google.genai" not in sys.modules:
    google = sys.modules.get("google") or types.ModuleType("google")
    genai = types.ModuleType("google.genai")
    class _Client:
        def __init__(self, *a, **k): pass
    genai.Client = _Client
    google.genai = genai
    sys.modules["google"] = google; sys.modules["google.genai"] = genai

import pytest
from fastapi import HTTPException, Response

from app import auth, business_store, main

TENANT_A = {"id": "tenant-a", "role": "client", "active": True, "patient_limit": 100, "ai_config": {"training_enabled": True}}
TENANT_B = {"id": "tenant-b", "role": "client", "active": True}
PATIENT_B = "patient-b"
PLAN_B = "plan-b"
WORKOUT_B = "workout-b"
REMINDER_B = "reminder-b"
TX_B = "tx-b"


class TenantDB:
    """Tiny PostgREST-like spy that contains only tenant-b records."""
    def __init__(self):
        self.calls = []
        self.rows = {
            "patient_accounts": [{
                "id": PATIENT_B,
                "client_id": "tenant-b",
                "name": "Paciente B",
                "active": True,
                "access_expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            }],
            "meal_plans": [{"id": PLAN_B, "client_id": "tenant-b", "patient_id": PATIENT_B, "title": "Plano B", "status": "draft"}],
            "workout_plans": [{"id": WORKOUT_B, "client_id": "tenant-b", "patient_id": PATIENT_B, "title": "Treino B", "status": "draft"}],
            "clinic_reminders": [{"id": REMINDER_B, "client_id": "tenant-b", "patient_id": PATIENT_B}],
            "clinic_transactions": [{"id": TX_B, "client_id": "tenant-b", "patient_id": PATIENT_B, "status": "pending"}],
        }

    @staticmethod
    def _match(value, expr):
        if not isinstance(expr, str):
            return True
        if expr.startswith("eq."):
            return str(value) == expr[3:]
        return True

    def request(self, method, table, params=None, payload=None, prefer=None, **kwargs):
        params = params or {}
        self.calls.append({"method": method, "table": table, "params": dict(params), "payload": payload, "prefer": prefer})
        rows = [dict(r) for r in self.rows.get(table, [])]
        filtered = []
        for row in rows:
            ok = True
            for key, expr in params.items():
                if key in {"select", "order", "limit", "on_conflict"}:
                    continue
                if key in row and not self._match(row.get(key), expr):
                    ok = False
                    break
            if ok:
                filtered.append(row)
        if method == "GET":
            return filtered
        if method in {"PATCH", "DELETE"}:
            # The security invariant: a request from tenant-a must never match
            # tenant-b data when client_id is included in the filter.
            if filtered:
                for row in filtered:
                    if row.get("client_id") == "tenant-b" and params.get("client_id") == "eq.tenant-a":
                        raise AssertionError("cross-tenant mutation matched a foreign row")
            return filtered
        if method == "POST":
            # Used only by tests that should have been rejected before create.
            data = dict(payload or {})
            data.setdefault("id", "new-row")
            return [data]
        return []


@pytest.fixture()
def tenant_db(monkeypatch):
    db = TenantDB()
    monkeypatch.setattr(main.saas_store, "_request", db.request)
    monkeypatch.setattr(business_store.saas_store, "_request", db.request)
    monkeypatch.setattr(main.business_store, "audit", lambda *_a, **_k: None)
    return db


def assert_404(call):
    with pytest.raises(HTTPException) as exc:
        call()
    assert exc.value.status_code == 404


def test_owned_patient_rejects_foreign_patient(tenant_db):
    assert_404(lambda: main._owned_patient(PATIENT_B, TENANT_A["id"]))
    call = tenant_db.calls[-1]
    assert call["table"] == "patient_accounts"
    assert call["params"]["id"] == f"eq.{PATIENT_B}"
    assert call["params"]["client_id"] == "eq.tenant-a"


@pytest.mark.parametrize("operation", ["edit", "renew", "archive", "restore", "hide"])
def test_patient_mutations_reject_foreign_patient_before_write(tenant_db, operation):
    before = len(tenant_db.calls)
    if operation == "edit":
        fn = lambda: main.edit_patient(PATIENT_B, {"name": "INVASAO"}, TENANT_A)
    elif operation == "renew":
        fn = lambda: main.renew_patient(PATIENT_B, main.PatientRenewRequest(duration_days=30), TENANT_A)
    elif operation == "archive":
        fn = lambda: main.archive_patient(PATIENT_B, TENANT_A)
    elif operation == "restore":
        fn = lambda: main.restore_patient(PATIENT_B, TENANT_A)
    else:
        fn = lambda: main.hide_patient(PATIENT_B, TENANT_A)
    assert_404(fn)
    new_calls = tenant_db.calls[before:]
    assert all(c["method"] == "GET" for c in new_calls), "foreign access must fail before any write"


def test_create_workout_for_foreign_patient_is_blocked(tenant_db):
    payload = main.WorkoutPlanRequest(title="Treino invasor", exercises=[{"name": "Teste", "sets": 1, "reps": "1"}])
    assert_404(lambda: main.create_workout_plan(PATIENT_B, payload, TENANT_A))
    assert not any(c["method"] == "POST" and c["table"] == "workout_plans" for c in tenant_db.calls)


def test_publish_foreign_workout_is_blocked_by_client_scope(tenant_db):
    assert_404(lambda: main.publish_workout_plan(WORKOUT_B, TENANT_A))
    get_call = next(c for c in tenant_db.calls if c["table"] == "workout_plans")
    assert get_call["params"]["client_id"] == "eq.tenant-a"
    assert not any(c["method"] == "PATCH" and c["table"] == "workout_plans" for c in tenant_db.calls)


def test_foreign_patient_meal_plan_cannot_be_created(tenant_db):
    # Ownership must be checked before food parsing or DB insertion.
    payload = main.MealPlanRequest(title="Plano invasor", content=[])
    assert_404(lambda: main.create_meal_plan(PATIENT_B, payload, TENANT_A))
    assert not any(c["method"] == "POST" and c["table"] == "meal_plans" for c in tenant_db.calls)


def test_foreign_plan_cannot_be_approved(tenant_db):
    assert_404(lambda: main.approve_meal_plan(PATIENT_B, PLAN_B, TENANT_A))
    assert not any(c["method"] == "PATCH" and c["table"] == "meal_plans" for c in tenant_db.calls)


def test_finance_update_cannot_touch_foreign_transaction(tenant_db):
    payload = main.clinical_extensions.FinanceUpdate(status="paid") if hasattr(main, "clinical_extensions") else None
    # Test the storage primitive directly: it must always include client_id.
    result = business_store.update_row("clinic_transactions", TX_B, TENANT_A["id"], {"status": "paid"})
    assert result is None
    call = tenant_db.calls[-1]
    assert call["method"] == "PATCH"
    assert call["params"]["id"] == f"eq.{TX_B}"
    assert call["params"]["client_id"] == "eq.tenant-a"


def test_reminder_lookup_is_tenant_scoped(tenant_db):
    row = business_store.get_row("clinic_reminders", REMINDER_B, TENANT_A["id"])
    assert row is None
    call = tenant_db.calls[-1]
    assert call["params"]["client_id"] == "eq.tenant-a"


def test_list_patients_never_lists_foreign_tenant(tenant_db):
    result = main.list_patients(TENANT_A)
    assert result == []
    call = tenant_db.calls[-1]
    assert call["table"] == "patient_accounts"
    assert call["params"]["client_id"] == "eq.tenant-a"


def test_business_store_all_crud_operations_are_client_scoped(monkeypatch):
    calls = []
    def spy(method, table, params=None, payload=None, prefer=None, **kwargs):
        calls.append((method, table, params or {}, payload))
        return [] if method != "POST" else [{"id": "x", **(payload or {})}]
    monkeypatch.setattr(business_store.saas_store, "_request", spy)
    business_store.list_rows("meal_plans", "tenant-a")
    business_store.get_row("meal_plans", "row-b", "tenant-a")
    business_store.update_row("meal_plans", "row-b", "tenant-a", {"title": "x"})
    business_store.delete_row("meal_plans", "row-b", "tenant-a")
    for method, _table, params, _payload in calls:
        if method in {"GET", "PATCH", "DELETE"}:
            assert params.get("client_id") == "eq.tenant-a"


def test_client_role_cannot_be_promoted_to_admin_by_calling_dependency():
    with pytest.raises(HTTPException) as exc:
        auth.require_admin(TENANT_A)
    assert exc.value.status_code == 403


def test_defense_in_depth_patient_patch_filters_include_client_id():
    source = (main.Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8") if hasattr(main, "Path") else open("app/main.py", encoding="utf-8").read()
    # The three historical mutations had an ownership pre-check but lacked the
    # tenant filter in the actual PATCH. Keep both layers forever.
    for endpoint_name in ("renew_patient", "archive_patient", "restore_patient"):
        start = source.index(f"def {endpoint_name}")
        chunk = source[start:start+1300]
        assert '"client_id": f"eq.{user[\'id\']}"' in chunk
