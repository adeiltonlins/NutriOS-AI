from starlette.requests import Request

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


def test_chat_has_friendly_fallback_when_gemini_fails(monkeypatch):
    monkeypatch.setenv("IA_ATIVA", "true")
    monkeypatch.setattr(main.base_conhecimento, "buscar_contexto", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main.base_conhecimento, "formatar_contexto_para_prompt", lambda _rows: "")
    monkeypatch.setattr(main, "gerar_resposta", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider down")))
    result = main.chat.__wrapped__(request(), main.PerguntaRequest(pergunta="Tenho uma dúvida"))
    assert "instabilidade" in result.resposta
    assert "quero agendar" in result.resposta


def test_consultation_intent_does_not_depend_on_gemini(monkeypatch):
    monkeypatch.setenv("IA_ATIVA", "true")
    monkeypatch.setattr(main.base_conhecimento, "buscar_contexto", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main.base_conhecimento, "formatar_contexto_para_prompt", lambda _rows: "")
    monkeypatch.setattr(main.saas_store, "get_user", lambda _id: {"id": "nutri-1", "role": "client", "active": True, "expires_at": None, "ai_config": {"link_consulta": "https://pagamento.exemplo/consulta"}})
    result = main.chat.__wrapped__(request(), main.PerguntaRequest(pergunta="Quero marcar uma consulta", client_id="nutri-1"))
    assert result.requires_contact is True
    assert "nome e WhatsApp" in result.resposta
