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


def salvar_lead(session_id: str, historico: list[dict], resposta_bot: str, link_agendamento: str) -> None:
    """
    Salva (ou atualiza) o registro do lead dessa sessão.
    Detecta se o Bruce já convidou pra agendar checando se o link de
    agendamento apareceu na resposta mais recente dele.
    """
    if not ARMAZENAMENTO_ATIVO:
        return

    quis_agendar = bool(link_agendamento) and link_agendamento in resposta_bot

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
