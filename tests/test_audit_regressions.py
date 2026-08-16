from starlette.requests import Request

from app import main
from app.llm import montar_patient_system_prompt


def request(path="/leads/contact"):
    return Request({"type": "http", "method": "POST", "path": path, "headers": [], "client": ("127.0.0.1", 1234)})


def test_tenant_checkout_uses_active_service_payment_link(monkeypatch):
    client = {"id": "nutri-1", "role": "client", "ai_config": {}}
    monkeypatch.setattr(main, "resolver_cliente_publico", lambda *_args: client)
    monkeypatch.setattr(main.business_store, "list_rows", lambda *_args, **_kwargs: [{"active": True, "payment_url": "https://pay.example/consulta"}])
    monkeypatch.setattr(main.leads_store, "buscar_lead", lambda *_args: {"session_id": "session-123"})
    monkeypatch.setattr(main.leads_store, "atualizar_lead", lambda *_args: {"ok": True})
    monkeypatch.setattr(main.pagamento, "criar_link_pagamento", lambda *_args: (_ for _ in ()).throw(AssertionError("Mercado Pago global não deve atender tenant")))
    payload = main.LeadContactRequest(session_id="session-123", client_slug="nutri", name="Pessoa Teste", phone="81999999999", consent=True)
    result = main.register_lead_contact.__wrapped__(request(), payload)
    assert result["payment_url"] == "https://pay.example/consulta"


def test_patient_prompt_has_no_commercial_context():
    prompt = montar_patient_system_prompt({"nome": "Dra. Ana"}).casefold()
    assert "já é paciente" in prompt
    assert "nunca fale sobre venda" in prompt
    assert "convite para consulta" in prompt
    assert "link_pagamento" not in prompt


def test_patient_chat_does_not_read_or_write_leads(monkeypatch):
    patient = {"id": "patient-1", "client_id": "nutri-1", "messages_used": 0, "message_limit": 10, "diet_context": "Plano em acompanhamento"}
    monkeypatch.setattr(main.saas_store, "get_user", lambda *_args: {"id": "nutri-1", "ai_config": {"nome": "Dra. Ana"}})
    monkeypatch.setattr(main.saas_store, "_request", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main, "gerar_resposta_paciente", lambda *_args, **_kwargs: "Uma opção geral é combinar fruta e proteína; confirme porções com sua nutricionista.")
    monkeypatch.setattr(main.leads_store, "buscar_lead", lambda *_args: (_ for _ in ()).throw(AssertionError("portal privado não consulta leads")))
    monkeypatch.setattr(main.leads_store, "salvar_lead", lambda *_args: (_ for _ in ()).throw(AssertionError("portal privado não salva leads")))
    payload = main.PerguntaRequest(pergunta="Qual lanche posso fazer?", session_id="patient-session")
    result = main.patient_private_chat.__wrapped__(request("/paciente/api/chat"), payload, patient)
    assert result.requires_contact is False
    assert "pagamento" not in result.resposta.casefold()


def test_dashboard_links_separate_clinical_finance_from_sales():
    html = (main.STATIC_DIR / "app.html").read_text(encoding="utf-8")
    assert 'href="/app/financeiro"><span class="os-nav-icon">$</span><span>Financeiro clínico' in html
    assert 'href="/app/metricas"><span class="os-nav-icon">▥</span><span>Captação e vendas' in html
    assert 'class="os-metric-card" href="/app/financeiro"' in html
