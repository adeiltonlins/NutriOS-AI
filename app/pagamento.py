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
"""
import hashlib
import hmac
import os
import requests

MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "")
MP_WEBHOOK_SECRET = os.environ.get("MP_WEBHOOK_SECRET", "")
VALOR_CONSULTA = float(os.environ.get("VALOR_CONSULTA", "150.00"))
NOME_ITEM = os.environ.get("NOME_ITEM_PAGAMENTO", "Consulta nutricional")
# URL pública do seu serviço no Render, ex: https://nutri-chatbot-8h6k.onrender.com
URL_BASE = os.environ.get("URL_BASE", "").rstrip("/")

PAGAMENTO_ATIVO = bool(MP_ACCESS_TOKEN and URL_BASE)

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


def criar_link_pagamento(session_id: str) -> str | None:
    """
    Cria uma preferência de pagamento (Checkout Pro) pra essa sessão e
    devolve o link (init_point) pra pessoa pagar.

    Usa external_reference=session_id, o que permite depois relacionar
    o pagamento confirmado de volta com a conversa/lead certo.
    """
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
