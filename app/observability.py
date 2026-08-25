"""Observabilidade leve do NutriOS sem dependência externa obrigatória."""
from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timezone
from threading import Lock

from fastapi import Depends

from app import auth, clinical_extensions

router = clinical_extensions.router
_lock = Lock()
_totals: Counter[str] = Counter()
_latency_ms: Counter[str] = Counter()
_recent_errors: deque[dict] = deque(maxlen=25)


def record_external_call(service: str, operation: str, duration_ms: float, ok: bool, detail: str | None = None) -> None:
    key = f"{service}:{operation}"
    with _lock:
        _totals[f"{key}:count"] += 1
        _latency_ms[f"{key}:sum_ms"] += int(max(0.0, duration_ms))
        if not ok:
            _totals[f"{key}:errors"] += 1
            _recent_errors.appendleft({
                "at": datetime.now(timezone.utc).isoformat(),
                "service": service,
                "operation": operation,
                "detail": (detail or "erro externo")[:240],
            })


def snapshot() -> dict:
    with _lock:
        groups: dict[str, dict] = {}
        for key, value in _totals.items():
            base, metric = key.rsplit(":", 1)
            groups.setdefault(base, {})[metric] = int(value)
        for key, value in _latency_ms.items():
            base = key.removesuffix(":sum_ms")
            groups.setdefault(base, {})["sum_ms"] = int(value)
        for metrics in groups.values():
            count = metrics.get("count", 0)
            metrics["avg_ms"] = round(metrics.get("sum_ms", 0) / count, 1) if count else 0
            metrics["error_rate"] = round(metrics.get("errors", 0) / count, 4) if count else 0
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "external_calls": groups,
            "recent_errors": list(_recent_errors),
        }


@router.get("/admin/api/observability")
def observability_snapshot(user: dict = Depends(auth.require_admin)):
    """Resumo operacional em memória para o ADMIN mestre."""
    return snapshot()
