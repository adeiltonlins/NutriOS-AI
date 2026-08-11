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


def _headers_upsert():
    """Headers pra INSERT/upsert (POST) — usa resolution=merge-duplicates."""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def _headers_update():
    """
    Headers pra UPDATE (PATCH) — sem resolution=merge-duplicates, que é uma
    instrução de upsert e não se aplica a PATCH.
    """
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _headers_read():
    """Headers pra GET (leitura)."""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _log_erro(prefixo: str, e: requests.RequestException) -> None:
    """
    Loga o erro com o corpo real da resposta do Supabase/PostgREST quando
    disponível — str(e) sozinho só mostra o status code, não o motivo.
    """
    if e.response is not None:
        print(f"[leads_store] {prefixo}: {e.response.status_code} - {e.response.text}")
    else:
        print(f"[leads_store] {prefixo}: {e}")


def salvar_lead(session_id: str, historico: list[dict], quis_agendar: bool, client_id: str | None = None, qualification: dict | None = None) -> None:
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
    if client_id:
        payload["client_id"] = client_id
    if qualification:
        payload.update({k: v for k, v in qualification.items() if k in {"lead_status", "lead_score", "lead_summary", "message_count", "lead_source"}})

    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/{TABELA}?on_conflict=session_id",
            headers=_headers_upsert(),
            json=payload,
            timeout=5,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        # Nunca deixa uma falha no armazenamento derrubar a resposta do chat
        _log_erro("Falha ao salvar lead", e)


def marcar_pago(session_id: str, payment_id: str, amount: float | None = None) -> None:
    """
    Marca o lead como pago, depois de o pagamento ter sido CONFIRMADO
    (status "approved") direto na API do Mercado Pago — nunca chamar isso
    só com base em parâmetro de URL, sem checar antes.
    """
    if not ARMAZENAMENTO_ATIVO:
        return

    payload = {
        "pago": True,
        "lead_status": "convertido",
        "lead_score": 100,
        "payment_id": payment_id,
        "pago_em": datetime.now(timezone.utc).isoformat(),
        "workflow_status": "payment_confirmed",
        "sale_amount": round(float(amount or 0), 2),
    }

    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{TABELA}",
            headers=_headers_update(),
            params={"session_id": f"eq.{session_id}"},
            json=payload,
            timeout=5,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        _log_erro("Falha ao marcar lead como pago", e)


def buscar_lead(session_id: str, client_id: str | None = None) -> dict | None:
    """Busca um lead específico pelo session_id (usado pra checar se já está pago)."""
    if not ARMAZENAMENTO_ATIVO:
        return None
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{TABELA}",
            headers=_headers_read(),
            params={"select": "*", "session_id": f"eq.{session_id}", **({"client_id": f"eq.{client_id}"} if client_id else {})},
            timeout=5,
        )
        resp.raise_for_status()
        resultados = resp.json()
        return resultados[0] if resultados else None
    except requests.RequestException as e:
        _log_erro("Falha ao buscar lead", e)
        return None


def atualizar_lead(session_id: str, payload: dict, client_id: str | None = None) -> dict | None:
    """Atualiza um lead, sempre permitindo restringir pelo dono (client_id)."""
    if not ARMAZENAMENTO_ATIVO:
        return None
    params = {"session_id": f"eq.{session_id}"}
    if client_id:
        params["client_id"] = f"eq.{client_id}"
    dados = dict(payload)
    dados["atualizado_em"] = datetime.now(timezone.utc).isoformat()
    headers = _headers_update()
    headers["Prefer"] = "return=representation"
    try:
        resp = requests.patch(f"{SUPABASE_URL}/rest/v1/{TABELA}", headers=headers, params=params, json=dados, timeout=5)
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else None
    except requests.RequestException as e:
        _log_erro("Falha ao atualizar lead", e)
        return None


def listar_leads(limite: int = 100, client_id: str | None = None, only_unassigned: bool = False) -> list[dict]:
    """Retorna os leads mais recentes, pro painel administrativo."""
    if not ARMAZENAMENTO_ATIVO:
        return []

    try:
        params = {"select": "*", "order": "atualizado_em.desc", "limit": str(limite)}
        if client_id:
            params["client_id"] = f"eq.{client_id}"
        elif only_unassigned:
            params["client_id"] = "is.null"
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{TABELA}",
            headers=_headers_read(),
            params=params,
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        _log_erro("Falha ao listar leads", e)
        return []
