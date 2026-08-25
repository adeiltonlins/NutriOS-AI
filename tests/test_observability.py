"""Tests for lightweight operational metrics."""
from __future__ import annotations

from app import observability


def test_external_call_metrics_include_average_and_error_rate():
    observability.record_external_call("supabase", "GET patient_accounts", 10, True)
    observability.record_external_call("supabase", "GET patient_accounts", 30, False, "timeout")
    data = observability.snapshot()
    metrics = data["external_calls"]["supabase:GET patient_accounts"]
    assert metrics["count"] >= 2
    assert metrics["avg_ms"] >= 0
    assert 0 <= metrics["error_rate"] <= 1
    assert any(item["service"] == "supabase" for item in data["recent_errors"])
