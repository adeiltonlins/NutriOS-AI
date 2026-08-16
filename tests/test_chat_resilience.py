from starlette.requests import Request
from fastapi import HTTPException
from datetime import datetime, timezone
import pytest

from app import main


def request():
    return Request({"type": "http", "method": "POST", "path": "/chat", "headers": [], "client": ("127.0.0.1", 1234)})


def test_chat_returns_model_answer_without_writing_lead(monkeypatch):
    monkeypatch.setenv("IA_ATIVA", "true")
    monkeypatch.setattr(main.base_conhecimento, "buscar_contexto", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main.base_conhecimento, "formatar_contexto_para_prompt", lambda _rows: "")
    monkeypatch.setattr(main, "gerar_resposta", lambda *_args, **_kwargs: "Resposta nutricional segura.")
    result = main.chat.__wrapped__(request(), main.PerguntaRequest(pergunta="Como melhorar meu café da manhã?"))
    assert result.resposta == "Resposta nutricional segura."
    assert result.requires_contact is False


def test_chat_has_useful_fallback_when_gemini_fails(monkeypatch):
    monkeypatch.setenv("IA_ATIVA", "true")
    monkeypatch.setattr(main.base_conhecimento, "buscar_contexto", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main.base_conhecimento, "formatar_contexto_para_prompt", lambda _rows: "")
    monkeypatch.setattr(main, "gerar_resposta", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider down")))
    result = main.chat.__wrapped__(request(), main.PerguntaRequest(pergunta="Tenho intolerância à lactose. O que posso comer no café da manhã?"))
    assert "sem lactose" in result.resposta
    assert "instabilidade" not in result.resposta


def test_consultation_intent_does_not_depend_on_gemini(monkeypatch):
    monkeypatch.setenv("IA_ATIVA", "true")
    monkeypatch.setattr(main.base_conhecimento, "buscar_contexto", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main.base_conhecimento, "formatar_contexto_para_prompt", lambda _rows: "")
    monkeypatch.setattr(main.saas_store, "get_user", lambda _id: {"id": "nutri-1", "role": "client", "active": True, "expires_at": None, "ai_config": {"link_consulta": "https://pagamento.exemplo/consulta"}})
    result = main.chat.__wrapped__(request(), main.PerguntaRequest(pergunta="Quero marcar uma consulta", client_id="nutri-1"))
    assert result.requires_contact is True
    assert "nome e WhatsApp" in result.resposta


def test_master_daily_visitor_limit_blocks_before_calling_ai(monkeypatch):
    monkeypatch.setenv("IA_ATIVA", "true")
    monkeypatch.setattr(main.base_conhecimento, "buscar_contexto", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main.base_conhecimento, "formatar_contexto_para_prompt", lambda _rows: "")
    monkeypatch.setattr(main, "master_chat_user", lambda: {"id": "admin-1", "role": "admin", "active": True, "ai_config": {"daily_visitor_limit": 1, "public_chat_enabled": True}})
    monkeypatch.setattr(main.leads_store, "listar_leads", lambda **_kwargs: [{"session_id": "existing", "criado_em": datetime.now(timezone.utc).isoformat()}])
    monkeypatch.setattr(main.leads_store, "buscar_lead", lambda *_args, **_kwargs: None)
    called = False
    def should_not_call(*_args, **_kwargs):
        nonlocal called
        called = True
        return "não deveria chamar"
    monkeypatch.setattr(main, "gerar_resposta", should_not_call)
    with pytest.raises(HTTPException) as error:
        main.chat.__wrapped__(request(), main.PerguntaRequest(pergunta="Olá", session_id="new-session", client_id="master"))
    assert error.value.status_code == 429
    assert called is False


def test_master_uses_mercado_pago_api_when_fixed_link_is_empty(monkeypatch):
    monkeypatch.setattr(main, "resolver_cliente_publico", lambda *_args: {"id": "admin-1", "identifier": "admin@example.com", "role": "admin", "active": True, "ai_config": {"whatsapp": "5581988762300"}})
    monkeypatch.setattr(main.pagamento, "PAGAMENTO_ATIVO", True)
    monkeypatch.setattr(main.pagamento, "criar_link_pagamento", lambda session_id: f"https://mercadopago.com/teste/{session_id}")
    monkeypatch.setattr(main.leads_store, "buscar_lead", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main.leads_store, "salvar_lead", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main.leads_store, "atualizar_lead", lambda *_args, **_kwargs: {"ok": True})
    payload = main.LeadContactRequest(session_id="session-123", client_id="master", name="Pessoa Teste", phone="81999999999", consent=True)
    result = main.register_lead_contact.__wrapped__(request(), payload)
    assert result["payment_url"] == "https://mercadopago.com/teste/session-123"
