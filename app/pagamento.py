"""
Integração com o Mercado Pago — Checkout Pro (link de pagamento com valor fixo).

Fluxo:
1. Quando o Bruce decide convidar a pessoa pra consulta, o backend gera um
   link de pagamento único pra aquela sessão (criar_link_pagamento).
2. A pessoa paga no Mercado Pago.
3. O Mercado Pago notifica o backend de duas formas (as duas são tratadas,
   pra garantir confiabilidade):
   - Redirecionamento imediato pro back_url de sucesso (bom pra UX rápida)
   - Webhook assíncrono em /pagamento/webhook (fonte da verdade, pode
     chegar mesmo se a pessoa fechar a aba antes do redirecionamento)
4. Em ambos os casos, o backend CONFERE o pagamento direto na API do
   Mercado Pago (nunca confia cegamente no que vem na URL) antes de
   liberar o contato do nutricionista.

Se MP_ACCESS_TOKEN não estiver configurado, as funções viram "no-op" —
mesmo padrão usado no leads_store.py, pra não quebrar o resto do projeto.

Modo de teste: se TEST_PAYMENT_MODE=true, cria links simulados e webhook
aceita confirmação manual para validar fluxo sem tocar no MP real.
"""
import hashlib
import hmac
import os
import requests
from datetime import datetime, timezone

# Modo de teste — nunca use em produção
TEST_PAYMENT_MODE = os.environ.get("TEST_PAYMENT_MODE", "false").lower() == "true"
_test_payments = {}  # session_id -> {status, payment_id, paid_at}

MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "")
MP_WEBHOOK_SECRET = os.environ.get("MP_WEBHOOK_SECRET", "")
VALOR_CONSULTA = float(os.environ.get("VALOR_CONSULTA", "150.00"))
NOME_ITEM = os.environ.get("NOME_ITEM_PAGAMENTO", "Consulta nutricional")
# URL pública do seu serviço no Render, ex: https://nutri-chatbot-8h6k.onrender.com
URL_BASE = os.environ.get("URL_BASE", "").rstrip("/")

PAGAMENTO_ATIVO = bool((MP_ACCESS_TOKEN and URL_BASE) or TEST_PAYMENT_MODE)

_API_BASE = "https://api.mercadopago.com"


def _headers():
    return {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def validar_assinatura_webhook(x_signature: str | None, x_request_id: str | None, data_id: str | None) -> bool:
    if not MP_WEBHOOK_SECRET:
        raise RuntimeError("MP_WEBHOOK_SECRET não configurado")
    if not x_signature:
        return False
    parts = {}
    for item in x_signature.split(","):
        key, separator, value = item.strip().partition("=")
        if separator and key in {"ts", "v1"}:
            parts[key] = value
    if not parts.get("ts") or not parts.get("v1"):
        return False
    manifest = ""
    if data_id:
        manifest += f"id:{data_id.lower()};"
    if x_request_id:
        manifest += f"request-id:{x_request_id};"
    manifest += f"ts:{parts['ts']};"
    expected = hmac.new(MP_WEBHOOK_SECRET.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(parts["v1"], expected)


def _test_payment_url(session_id: str) -> str:
    """Gera URL de pagamento simulada para testes."""
    return f"{URL_BASE or 'https://test.local'}/pagamento/teste?session_id={session_id}"


def _register_test_payment(session_id: str, status: str = "pending"):
    """Registra pagamento de teste para consulta via webhook/sucesso."""
    _test_payments[session_id] = {
        "status": status,
        "payment_id": f"TEST-{session_id[:8]}",
        "paid_at": datetime.now(timezone.utc).isoformat(),
        "external_reference": session_id,
        "transaction_amount": VALOR_CONSULTA,
    }


def _get_test_payment(session_id: str) -> dict | None:
    return _test_payments.get(session_id)


def confirmar_pagamento_teste(session_id: str) -> bool:
    """Endpoint auxiliar: marca pagamento de teste como aprovado."""
    if not TEST_PAYMENT_MODE:
        return False
    _register_test_payment(session_id, "approved")
    return True


def criar_link_pagamento(session_id: str) -> str | None:
    """
    Cria uma preferência de pagamento (Checkout Pro) pra essa sessão e
    devolve o link (init_point) pra pessoa pagar.

    Usa external_reference=session_id, o que permite depois relacionar
    o pagamento confirmado de volta com a conversa/lead certo.
    """
    if TEST_PAYMENT_MODE:
        _register_test_payment(session_id, "pending")
        return _test_payment_url(session_id)
    if not PAGAMENTO_ATIVO:
        return None

    payload = {
        "items": [
            {
                "title": NOME_ITEM,
                "quantity": 1,
                "unit_price": VALOR_CONSULTA,
                "currency_id": "BRL",
            }
        ],
        "external_reference": session_id,
        "back_urls": {
            "success": f"{URL_BASE}/pagamento/sucesso",
            "pending": f"{URL_BASE}/pagamento/pendente",
            "failure": f"{URL_BASE}/pagamento/erro",
        },
        "auto_return": "approved",
        "notification_url": f"{URL_BASE}/pagamento/webhook",
    }

    try:
        resp = requests.post(
            f"{_API_BASE}/checkout/preferences",
            headers=_headers(),
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("init_point")
    except requests.RequestException as e:
        print(f"[pagamento] Falha ao criar link de pagamento: {e}")
        return None


def consultar_pagamento(payment_id: str) -> dict | None:
    """Busca o status real de um pagamento direto na API do Mercado Pago."""
    if not PAGAMENTO_ATIVO:
        return None
    if TEST_PAYMENT_MODE and payment_id.startswith("TEST-"):
        # Busca pelo session_id derivado do payment_id
        session_id = payment_id.replace("TEST-", "")
        # Precisa encontrar a chave completa (pode ter mais chars)
        for k, v in _test_payments.items():
            if k.startswith(session_id):
                return v
        return None
    try:
        resp = requests.get(
            f"{_API_BASE}/v1/payments/{payment_id}",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"[pagamento] Falha ao consultar pagamento {payment_id}: {e}")
        return None


def buscar_pagamentos_por_referencia(external_reference: str) -> list[dict]:
    """
    Busca pagamentos pela external_reference (nosso session_id) — usado
    na página de sucesso quando só temos o session_id na URL, sem o
    payment_id direto.
    """
    if not PAGAMENTO_ATIVO:
        return []
    if TEST_PAYMENT_MODE:
        payment = _get_test_payment(external_reference)
        return [payment] if payment else []
    try:
        resp = requests.get(
            f"{_API_BASE}/v1/payments/search",
            headers=_headers(),
            params={"external_reference": external_reference},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except requests.RequestException as e:
        print(f"[pagamento] Falha ao buscar pagamentos por referência: {e}")
        return []
