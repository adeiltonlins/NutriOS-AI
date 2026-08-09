"""
Camada de armazenamento de leads.

Guarda cada conversa (por sessão) num banco Postgres gerenciado pelo
Supabase, via API REST (PostgREST) — sem precisar de driver de banco
pesado, só requisições HTTP simples.

Se as variáveis SUPABASE_URL / SUPABASE_KEY não estiverem configuradas,
as funções aqui viram "no-op" (não quebram o chatbot, só não salvam nada)
— assim o projeto continua funcionando mesmo antes de você configurar o
banco.
"""
import os
import json
from datetime import datetime, timezone

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TABELA = "leads"

ARMAZENAMENTO_ATIVO = bool(SUPABASE_URL and SUPABASE_KEY)


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def salvar_lead(session_id: str, historico: list[dict], quis_agendar: bool) -> None:
    """
    Salva (ou atualiza) o registro do lead dessa sessão.
    quis_agendar é decidido por quem chama (main.py), com base em se o
    Bruce sinalizou o convite de pagamento nessa resposta — não fica mais
    escondido aqui dentro checando texto.
    """
    if not ARMAZENAMENTO_ATIVO:
        return

    payload = {
        "session_id": session_id,
        "historico": json.dumps(historico, ensure_ascii=False),
        "quis_agendar": quis_agendar,
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    }

    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/{TABELA}?on_conflict=session_id",
            headers=_headers(),
            json=payload,
            timeout=5,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        # Nunca deixa uma falha no armazenamento derrubar a resposta do chat
        print(f"[leads_store] Falha ao salvar lead: {e}")


def marcar_pago(session_id: str, payment_id: str) -> None:
    """
    Marca o lead como pago, depois de o pagamento ter sido CONFIRMADO
    (status "approved") direto na API do Mercado Pago — nunca chamar isso
    só com base em parâmetro de URL, sem checar antes.
    """
    if not ARMAZENAMENTO_ATIVO:
        return

    payload = {
        "pago": True,
        "payment_id": payment_id,
        "pago_em": datetime.now(timezone.utc).isoformat(),
    }

    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{TABELA}",
            headers=_headers(),
            params={"session_id": f"eq.{session_id}"},
            json=payload,
            timeout=5,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[leads_store] Falha ao marcar lead como pago: {e}")


def buscar_lead(session_id: str) -> dict | None:
    """Busca um lead específico pelo session_id (usado pra checar se já está pago)."""
    if not ARMAZENAMENTO_ATIVO:
        return None
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{TABELA}",
            headers=_headers(),
            params={"select": "*", "session_id": f"eq.{session_id}"},
            timeout=5,
        )
        resp.raise_for_status()
        resultados = resp.json()
        return resultados[0] if resultados else None
    except requests.RequestException as e:
        print(f"[leads_store] Falha ao buscar lead: {e}")
        return None


def listar_leads(limite: int = 100) -> list[dict]:
    """Retorna os leads mais recentes, pro painel administrativo."""
    if not ARMAZENAMENTO_ATIVO:
        return []

    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{TABELA}",
            headers=_headers(),
            params={"select": "*", "order": "atualizado_em.desc", "limit": str(limite)},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"[leads_store] Falha ao listar leads: {e}")
        return []
