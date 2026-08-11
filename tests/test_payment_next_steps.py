from app import main


def test_payment_next_steps_only_releases_after_verified_payment():
    pending = main.payment_next_steps({"session_id": "session-123", "pago": False}, None, "https://example.com/")
    assert pending["liberado"] is False
    assert "whatsapp_url" not in pending


def test_payment_next_steps_builds_tenant_actions():
    lead = {"session_id": "session-123", "pago": True}
    owner = {
        "public_slug": "dra-maria-ab12",
        "ai_config": {"whatsapp": "(81) 99999-9999"},
    }
    result = main.payment_next_steps(lead, owner, "https://example.com/")
    assert result["liberado"] is True
    assert result["whatsapp_url"].startswith("https://wa.me/5581999999999?")
    assert result["anamnesis_url"] == "https://example.com/n/dra-maria-ab12/anamnese?session_id=session-123"
    assert result["response_deadline_hours"] == 24


def test_payment_next_steps_builds_master_anamnesis_url():
    result = main.payment_next_steps({"session_id": "master-session", "pago": True}, {"ai_config": {}}, "https://example.com")
    assert result["anamnesis_url"] == "https://example.com/assistente/anamnese?session_id=master-session"
