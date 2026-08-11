from datetime import datetime, timezone

from app.main import _metricas_periodo


def test_metricas_mensais_calculam_faturamento_e_origem():
    leads = [
        {"criado_em": "2026-08-02T10:00:00Z", "pago": True, "pago_em": "2026-08-03T10:00:00Z", "sale_amount": 200, "quis_agendar": True, "lead_source": "instagram", "scheduled_at": "2026-08-04T10:00:00Z"},
        {"criado_em": "2026-08-05T10:00:00Z", "pago": True, "pago_em": "2026-08-06T10:00:00Z", "sale_amount": 100, "quis_agendar": True, "lead_source": "whatsapp"},
        {"criado_em": "2026-08-07T10:00:00Z", "pago": False, "quis_agendar": False, "lead_source": "instagram"},
    ]
    result = _metricas_periodo(leads, datetime(2026, 8, 1, tzinfo=timezone.utc), datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert result["revenue"] == 300
    assert result["sales"] == 2
    assert result["ticket_average"] == 150
    assert result["conversion_rate"] == 66.7
    assert result["scheduled"] == 1
    assert result["sources"] == {"instagram": 2, "whatsapp": 1}


def test_metricas_nao_misturam_outros_meses():
    leads = [{"criado_em": "2026-07-31T23:00:00Z", "pago": True, "pago_em": "2026-07-31T23:00:00Z", "sale_amount": 999}]
    result = _metricas_periodo(leads, datetime(2026, 8, 1, tzinfo=timezone.utc), datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert result["conversations"] == 0
    assert result["revenue"] == 0
