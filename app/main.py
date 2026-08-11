"""
API do chatbot nutricional — MVP com RAG (retrieval por TF-IDF) + Gemini API.

Rodar localmente:
    export GEMINI_API_KEY=sua_chave_aqui
    uvicorn app.main:app --reload

Depois acesse http://localhost:8000/docs para testar pela interface Swagger.
"""
import csv
import html
import io
import json
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel, Field

from app.knowledge_base import base_conhecimento
from app.llm import gerar_resposta, LINK_AGENDAMENTO, MARCADOR_LINK_PAGAMENTO, NUTRICIONISTA_NOME
from app import leads_store
from app import pagamento
from app import auth, saas_store
import os


def token_valido(token: str) -> bool:
    """Compara o token do admin usando comparação de tempo constante
    (evita timing attack) e nunca autoriza se ADMIN_TOKEN não estiver
    configurado."""
    token_esperado = os.environ.get("ADMIN_TOKEN", "")
    if not token_esperado:
        return False
    return secrets.compare_digest(token, token_esperado)

# Contato liberado pro paciente só depois do pagamento confirmado —
# ex: link do WhatsApp pessoal/profissional do nutricionista.
CONTATO_NUTRICIONISTA = os.environ.get("CONTATO_NUTRICIONISTA", LINK_AGENDAMENTO)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Nutri Chatbot API",
    description="Chatbot nutricional com RAG sobre dados TACO e diretrizes de saúde",
    version="0.1.0",
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Restringe CORS ao(s) domínio(s) reais do site (configure ALLOWED_ORIGINS
# no .env, separado por vírgula, ex: "https://seusite.com,https://www.seusite.com").
# Sem configurar, cai pra URL_BASE (Render) — nunca "*" em produção.
_origens_env = os.environ.get("ALLOWED_ORIGINS", "")
if _origens_env:
    ALLOWED_ORIGINS = [o.strip() for o in _origens_env.split(",") if o.strip()]
else:
    _url_base = os.environ.get("URL_BASE", "").rstrip("/")
    ALLOWED_ORIGINS = [_url_base] if _url_base else []

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", "1048576"))


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and int(length) > MAX_BODY_BYTES:
        return Response("Corpo da requisição excede o limite", status_code=413)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path != "/pagamento/webhook":
        origin = request.headers.get("origin")
        if origin and ALLOWED_ORIGINS and origin.rstrip("/") not in {x.rstrip("/") for x in ALLOWED_ORIGINS}:
            return Response("Origem não autorizada", status_code=403)
        if request.url.path != "/auth/logout" and request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
            return Response("Content-Type inválido", status_code=415)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.get("/")
def servir_interface():
    """Serve a interface de chat (HTML) na URL raiz do site."""
    return FileResponse(STATIC_DIR / "index.html")


class MensagemHistorico(BaseModel):
    autor: str  # "user" ou "bot"
    texto: str


class PerguntaRequest(BaseModel):
    pergunta: str = Field(..., min_length=1, max_length=1000, description="Pergunta do usuário")
    historico: list[MensagemHistorico] = Field(default_factory=list, max_length=40, description="Mensagens anteriores da conversa, em ordem (limitado pra evitar payloads gigantes)")
    session_id: str = Field(default="", max_length=100, description="Identificador único da conversa, gerado pelo navegador")
    client_id: str | None = Field(default=None, max_length=64)
    client_slug: str | None = Field(default=None, max_length=160)
    lead_source: str | None = Field(default=None, max_length=80)


class LoginRequest(BaseModel):
    code: str | None = Field(default=None, max_length=256)
    identifier: str | None = Field(default=None, max_length=160)
    password: str | None = Field(default=None, max_length=128)


class PasswordSetupRequest(BaseModel):
    password: str = Field(..., min_length=10, max_length=128)


class ClienteRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    identifier: str = Field(..., min_length=3, max_length=160)
    plan: str | None = Field(default=None, max_length=60)
    duration_days: int = Field(default=30, ge=1, le=3650)


class CodigoRequest(BaseModel):
    hours: int | None = Field(default=None, ge=1, le=24 * 365)
    expires_at: datetime | None = None


class RespostaResponse(BaseModel):
    resposta: str
    fontes_utilizadas: list[str]
    requires_contact: bool = False
    workflow_status: str | None = None


class LeadContactRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=100)
    client_id: str | None = Field(default=None, max_length=64)
    client_slug: str | None = Field(default=None, max_length=160)
    name: str = Field(..., min_length=2, max_length=120)
    phone: str = Field(..., min_length=8, max_length=30)
    consent: bool
    lead_source: str | None = Field(default=None, max_length=80)


class LeadClaimPaidRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=100)
    client_id: str | None = Field(default=None, max_length=64)
    client_slug: str | None = Field(default=None, max_length=160)


class LeadWorkflowRequest(BaseModel):
    action: str = Field(..., max_length=40)
    amount: float | None = Field(default=None, ge=0, le=1000000)


def qualificar_lead(historico: list[dict], quis_agendar: bool, pago: bool = False) -> dict:
    """Classificação comercial local: rápida e sem consumir outra chamada do Gemini."""
    falas = [str(m.get("texto", "")).strip() for m in historico if m.get("autor") == "user"]
    texto = " ".join(falas).lower()
    quentes = ("preço", "valor", "quanto custa", "agendar", "consulta", "pagamento", "pagar", "quero marcar", "horário")
    interesse = ("emagrecer", "ganhar massa", "não consigo", "já tentei", "dificuldade", "preciso", "objetivo", "compulsão", "acompanhamento")
    score = min(100, len(falas) * 4 + sum(14 for k in quentes if k in texto) + sum(6 for k in interesse if k in texto) + (25 if quis_agendar else 0))
    if pago:
        status, score = "convertido", 100
    elif quis_agendar or any(k in texto for k in quentes):
        status = "quente"
    elif any(k in texto for k in interesse) or len(falas) >= 3:
        status = "interessado"
    else:
        status = "duvida"
    resumo = " | ".join(falas[-3:])[:600] or "Conversa iniciada"
    return {"lead_status": status, "lead_score": score, "lead_summary": resumo, "message_count": len(falas)}


def criar_slug_publico(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:60] or "nutricionista"
    return f"{base}-{secrets.token_hex(2)}"


def resolver_cliente_publico(client_slug: str | None, client_id: str | None) -> dict:
    client = saas_store.get_user_by_slug(client_slug) if client_slug else saas_store.get_user(client_id) if client_id else None
    if not client or client.get("role") != "client" or not client.get("active"):
        raise HTTPException(404, "Assistente indisponível")
    if client.get("expires_at") and datetime.fromisoformat(client["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        raise HTTPException(404, "Assistente indisponível")
    return client


def normalizar_whatsapp(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if not 10 <= len(digits) <= 15:
        raise HTTPException(400, "Informe um WhatsApp válido com DDD e código do país.")
    return digits


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "alimentos_carregados": len(base_conhecimento.alimentos),
        "armazenamento_leads_ativo": leads_store.ARMAZENAMENTO_ATIVO,
    }


@app.get("/login")
def login_page():
    return FileResponse(STATIC_DIR / "login.html")


@app.post("/auth/login")
@limiter.limit(os.getenv("LOGIN_RATE_LIMIT", "5/minute"))
def login(request: Request, payload: LoginRequest, response: Response):
    try:
        if payload.code:
            user = auth.authenticate_master(payload.code) or auth.authenticate_code(payload.code)
        elif payload.identifier and payload.password:
            user = auth.authenticate_password(payload.identifier.lower().strip(), payload.password)
        else:
            user = None
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    if not user:
        raise HTTPException(401, "Credenciais inválidas")
    auth.create_session(user, response)
    redirect = "/admin" if user["role"] == "admin" else ("/app/primeiro-acesso" if not user.get("password_hash") else "/app")
    return {"redirect": redirect}


@app.post("/auth/logout")
def logout(request: Request, response: Response):
    auth.logout(request, response)
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(auth.current_user)):
    return {"id": user["id"], "name": user["name"], "role": user["role"], "active": user["active"]}


@app.get("/app")
def client_app(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "app.html")


@app.get("/app/primeiro-acesso")
def password_setup_page(user: dict = Depends(auth.current_user)):
    if user.get("role") != "client":
        raise HTTPException(403, "Somente clientes")
    return FileResponse(STATIC_DIR / "setup-password.html")


@app.post("/app/primeiro-acesso")
def password_setup(payload: PasswordSetupRequest, user: dict = Depends(auth.current_user)):
    if user.get("role") != "client":
        raise HTTPException(403, "Somente clientes")
    try:
        password_hash = auth.hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    saas_store.update_user(user["id"], {"password_hash": password_hash, "password_created_at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, "redirect": "/app"}


@app.get("/app/chat")
def client_chat(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/n/{public_slug}")
def public_client_chat(public_slug: str):
    client = saas_store.get_user_by_slug(public_slug)
    if not client or client.get("role") != "client" or not client.get("active"):
        raise HTTPException(404, "Assistente indisponível")
    if client.get("expires_at") and datetime.fromisoformat(client["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        raise HTTPException(404, "Assistente indisponível")
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/public/clientes/{public_slug}")
def public_client_branding(public_slug: str):
    client = saas_store.get_user_by_slug(public_slug)
    if not client or client.get("role") != "client" or not client.get("active"):
        raise HTTPException(404, "Assistente indisponível")
    if client.get("expires_at") and datetime.fromisoformat(client["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        raise HTTPException(404, "Assistente indisponível")
    config = client.get("ai_config") or {}
    safe_keys = {"nome", "especialidade", "identidade_ia", "mensagem_inicial", "horario", "logo_url", "crn", "cor_principal", "instagram", "acoes_rapidas"}
    safe = {k: config.get(k) for k in safe_keys if config.get(k)}
    safe["nome"] = safe.get("nome") or client.get("name")
    color = safe.get("cor_principal", "#2563eb")
    safe["cor_principal"] = color if re.fullmatch(r"#[0-9a-fA-F]{6}", str(color)) else "#2563eb"
    if safe.get("logo_url") and not str(safe["logo_url"]).startswith("https://"):
        safe.pop("logo_url", None)
    for key in ("instagram",):
        if safe.get(key) and not str(safe[key]).startswith("https://"):
            safe.pop(key, None)
    return safe


@app.get("/app/leads")
def own_leads(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "client-leads.html")


@app.get("/app/api/leads")
def own_leads_data(user: dict = Depends(auth.current_user)):
    return leads_store.listar_leads(limite=500, client_id=None if user["role"] == "admin" else user["id"])


@app.get("/app/metricas")
def own_metrics(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "client-metrics.html")


def _parse_data_lead(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _metricas_periodo(leads: list[dict], start: datetime, end: datetime) -> dict:
    created = [x for x in leads if (d := _parse_data_lead(x.get("criado_em") or x.get("atualizado_em"))) and start <= d < end]
    sales = [x for x in leads if x.get("pago") and (d := _parse_data_lead(x.get("pago_em"))) and start <= d < end]
    revenue = sum(float(x.get("sale_amount") or 0) for x in sales)
    scheduled = [x for x in leads if (d := _parse_data_lead(x.get("scheduled_at"))) and start <= d < end]
    sources: dict[str, int] = {}
    daily: dict[str, dict] = {}
    for item in created:
        source = str(item.get("lead_source") or "direto").strip().lower()[:80]
        sources[source] = sources.get(source, 0) + 1
    for item in sales:
        day = str(item.get("pago_em"))[:10]
        daily.setdefault(day, {"sales": 0, "revenue": 0.0})
        daily[day]["sales"] += 1
        daily[day]["revenue"] += float(item.get("sale_amount") or 0)
    return {"conversations": len(created), "leads": sum(bool(x.get("quis_agendar")) for x in created), "sales": len(sales), "revenue": round(revenue, 2), "ticket_average": round(revenue / len(sales), 2) if sales else 0, "scheduled": len(scheduled), "conversion_rate": round((len(sales) / len(created) * 100), 1) if created else 0, "sources": sources, "daily": daily}


@app.get("/app/api/metricas")
def own_metrics_data(month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"), user: dict = Depends(auth.current_user)):
    now = datetime.now(timezone.utc)
    if month:
        year, number = map(int, month.split("-"))
        if number < 1 or number > 12:
            raise HTTPException(400, "Mês inválido")
        start = datetime(year, number, 1, tzinfo=timezone.utc)
    else:
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    end = datetime(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1, tzinfo=timezone.utc)
    previous_start = datetime(start.year - (start.month == 1), 12 if start.month == 1 else start.month - 1, 1, tzinfo=timezone.utc)
    leads = leads_store.listar_leads(limite=5000, client_id=None if user["role"] == "admin" else user["id"])
    current = _metricas_periodo(leads, start, end)
    previous = _metricas_periodo(leads, previous_start, start)
    growth = round(((current["revenue"] - previous["revenue"]) / previous["revenue"] * 100), 1) if previous["revenue"] else (100.0 if current["revenue"] else 0.0)
    return {"month": start.strftime("%Y-%m"), "current": current, "previous": previous, "revenue_growth": growth}


@app.get("/app/api/metricas/exportar")
def export_own_metrics(user: dict = Depends(auth.current_user)):
    leads = leads_store.listar_leads(limite=5000, client_id=None if user["role"] == "admin" else user["id"])
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Data", "Nome", "WhatsApp", "Origem", "Status", "Pago", "Valor", "Agendado"])
    for lead in leads:
        writer.writerow([lead.get("criado_em") or lead.get("atualizado_em"), lead.get("lead_name"), lead.get("lead_phone"), lead.get("lead_source") or "direto", lead.get("workflow_status"), "Sim" if lead.get("pago") else "Não", lead.get("sale_amount") or 0, "Sim" if lead.get("scheduled_at") else "Não"])
    return Response("\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=balancete-nutribot.csv"})


@app.patch("/app/api/leads/{session_id}")
def update_lead_workflow(session_id: str, payload: LeadWorkflowRequest, user: dict = Depends(auth.current_user)):
    client_id = None if user["role"] == "admin" else user["id"]
    lead = leads_store.buscar_lead(session_id, client_id)
    if not lead:
        raise HTTPException(404, "Lead não encontrado")
    now = datetime.now(timezone.utc).isoformat()
    actions = {
        "confirm_payment": {"pago": True, "pago_em": now, "manual_payment_confirmed_at": now, "workflow_status": "payment_confirmed", "lead_status": "convertido", "lead_score": 100, "sale_amount": round(float(payload.amount or 0), 2)},
        "contacted": {"contacted_at": now, "workflow_status": "contacted"},
        "anamnesis_sent": {"anamnesis_sent_at": now, "workflow_status": "anamnesis_sent"},
        "scheduled": {"scheduled_at": now, "workflow_status": "scheduled"},
    }
    if payload.action not in actions:
        raise HTTPException(400, "Ação inválida")
    updated = leads_store.atualizar_lead(session_id, actions[payload.action], client_id)
    if not updated:
        raise HTTPException(503, "Não foi possível atualizar o lead")
    return updated


@app.get("/app/configuracoes")
def own_config(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "client-config.html")


@app.get("/app/api/configuracoes")
def own_config_data(request: Request, user: dict = Depends(auth.current_user)):
    return {"name": user["name"], "identifier": user["identifier"], "plan": user.get("plan"), "expires_at": user.get("expires_at"), "public_slug": user.get("public_slug"), "public_url": f"{str(request.base_url).rstrip('/')}/n/{user.get('public_slug')}" if user.get("public_slug") else None, "ai_config": user.get("ai_config") or {}}


@app.patch("/app/api/configuracoes")
def update_own_config(payload: dict, user: dict = Depends(auth.current_user)):
    current = user.get("ai_config") or {}
    allowed = {k: v for k, v in payload.items() if k in {"nome", "especialidade", "whatsapp", "link_consulta", "identidade_ia", "mensagem_inicial", "cta", "horario", "logo_url", "prompt", "free_message_limit", "crn", "cor_principal", "instagram", "acoes_rapidas", "anamnesis_url", "whatsapp_message_template", "payment_wait_message"}}
    if "free_message_limit" in allowed:
        allowed["free_message_limit"] = max(1, min(50, int(allowed["free_message_limit"] or 8)))
    current.update(allowed)
    updated = saas_store.update_user(user["id"], {"ai_config": current})
    return {"ok": True, "ai_config": updated.get("ai_config") if updated else current}


@app.post("/leads/contact")
@limiter.limit("5/minute")
def register_lead_contact(request: Request, payload: LeadContactRequest):
    if not payload.consent:
        raise HTTPException(400, "É necessário autorizar o contato pelo WhatsApp.")
    client = resolver_cliente_publico(payload.client_slug, payload.client_id)
    config = client.get("ai_config") or {}
    payment_url = str(config.get("link_consulta") or "").strip()
    if not payment_url.startswith("https://"):
        raise HTTPException(409, "O profissional ainda não configurou o link de pagamento.")
    lead = leads_store.buscar_lead(payload.session_id, client["id"])
    if not lead:
        leads_store.salvar_lead(payload.session_id, [], True, client["id"], {"lead_status": "quente", "lead_score": 70, "lead_summary": "Solicitou atendimento", "message_count": 0})
    updated = leads_store.atualizar_lead(payload.session_id, {"lead_name": payload.name.strip(), "lead_phone": normalizar_whatsapp(payload.phone), "contact_consent_at": datetime.now(timezone.utc).isoformat(), "workflow_status": "awaiting_payment", "lead_status": "quente", "lead_source": (payload.lead_source or "direto").strip().lower()[:80]}, client["id"])
    if not updated:
        raise HTTPException(503, "Não foi possível registrar seus dados.")
    message = config.get("payment_wait_message") or "Após realizar o pagamento, clique em ‘Já realizei o pagamento’. A clínica fará a conferência e entrará em contato pelo WhatsApp informado em até 24 horas."
    return {"ok": True, "payment_url": payment_url, "message": message, "workflow_status": "awaiting_payment"}


@app.post("/leads/claim-paid")
@limiter.limit("5/minute")
def claim_paid(request: Request, payload: LeadClaimPaidRequest):
    client = resolver_cliente_publico(payload.client_slug, payload.client_id)
    lead = leads_store.buscar_lead(payload.session_id, client["id"])
    if not lead or not lead.get("contact_consent_at"):
        raise HTTPException(400, "Cadastre seus dados antes de informar o pagamento.")
    updated = leads_store.atualizar_lead(payload.session_id, {"workflow_status": "awaiting_verification", "claimed_paid_at": datetime.now(timezone.utc).isoformat()}, client["id"])
    if not updated:
        raise HTTPException(503, "Não foi possível registrar a solicitação.")
    return {"ok": True, "message": "Recebemos seu aviso. A clínica verificará o pagamento e entrará em contato pelo WhatsApp informado em até 24 horas.", "workflow_status": "awaiting_verification"}


@app.get("/admin")
def admin_page(user: dict = Depends(auth.require_admin)):
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/admin/api/dashboard")
def admin_dashboard(user: dict = Depends(auth.require_admin)):
    clients = [u for u in saas_store.list_users() if u["role"] == "client"]
    leads = leads_store.listar_leads(limite=1000)
    now = datetime.now(timezone.utc)

    def expired(client: dict) -> bool:
        value = client.get("expires_at")
        return bool(value and datetime.fromisoformat(value.replace("Z", "+00:00")) <= now)

    return {
        "clients_total": len(clients),
        "clients_active": sum(bool(c["active"]) and not expired(c) for c in clients),
        "clients_expired": sum(expired(c) for c in clients),
        "leads_total": len(leads),
        "ai_active": os.getenv("IA_ATIVA", "true").lower() == "true",
        "clients": clients,
    }


@app.post("/admin/clientes")
def create_client(payload: ClienteRequest, admin: dict = Depends(auth.require_admin)):
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.duration_days)
    return saas_store.create_user({"name": payload.name, "identifier": payload.identifier.lower().strip(), "role": "client", "active": True, "plan": payload.plan, "expires_at": expires_at.isoformat(), "public_slug": criar_slug_publico(payload.name)})


@app.post("/admin/clientes/{user_id}/renovar")
def renew_client(user_id: str, payload: CodigoRequest, admin: dict = Depends(auth.require_admin)):
    client = saas_store.get_user(user_id)
    if not client or client.get("role") != "client":
        raise HTTPException(404, "Cliente não encontrado")
    base = datetime.now(timezone.utc)
    if client.get("expires_at"):
        current_expiry = datetime.fromisoformat(client["expires_at"].replace("Z", "+00:00"))
        if current_expiry > base:
            base = current_expiry
    days = max(1, (payload.hours or 720) // 24)
    return saas_store.update_user(user_id, {"active": True, "expires_at": (base + timedelta(days=days)).isoformat()})


@app.patch("/admin/clientes/{user_id}")
def edit_client(user_id: str, payload: dict, admin: dict = Depends(auth.require_admin)):
    allowed = {k: v for k, v in payload.items() if k in {"name", "identifier", "plan", "active", "expires_at", "ai_config"}}
    if "active" in allowed and not allowed["active"]:
        saas_store.revoke_user_sessions(user_id)
    return saas_store.update_user(user_id, allowed)


@app.post("/admin/clientes/{user_id}/codigos")
@limiter.limit(os.getenv("CODE_GENERATION_RATE_LIMIT", "10/minute"))
def generate_code(request: Request, user_id: str, payload: CodigoRequest, admin: dict = Depends(auth.require_admin)):
    client = saas_store.get_user(user_id)
    if not client or client["role"] != "client":
        raise HTTPException(404, "Cliente não encontrado")
    expires = payload.expires_at or (datetime.now(timezone.utc) + timedelta(hours=payload.hours or 24 * 30))
    if expires <= datetime.now(timezone.utc):
        raise HTTPException(400, "A expiração deve estar no futuro")
    code = auth.issue_code(user_id, expires, admin["id"])
    return {"code": code, "expires_at": expires, "show_once": True}


@app.post("/admin/clientes/{user_id}/revogar")
def revoke_client_access(user_id: str, admin: dict = Depends(auth.require_admin)):
    saas_store.revoke_codes(user_id)
    saas_store.revoke_user_sessions(user_id)
    saas_store.update_user(user_id, {"password_hash": None, "password_created_at": None})
    return {"ok": True}


@app.post("/admin/clientes/{user_id}/resetar-senha")
def reset_client_password(user_id: str, admin: dict = Depends(auth.require_admin)):
    client = saas_store.get_user(user_id)
    if not client or client.get("role") != "client":
        raise HTTPException(404, "Cliente não encontrado")
    saas_store.update_user(user_id, {"password_hash": None, "password_created_at": None})
    saas_store.revoke_user_sessions(user_id)
    saas_store.revoke_codes(user_id)
    return {"ok": True, "message": "Senha removida. Gere um novo código de primeiro acesso."}


@app.post("/chat", response_model=RespostaResponse)
@limiter.limit("15/minute")
def chat(request: Request, req: PerguntaRequest):
    if os.getenv("IA_ATIVA", "true").lower() != "true":
        raise HTTPException(503, "Assistente temporariamente indisponível")
    if not req.pergunta.strip():
        raise HTTPException(status_code=400, detail="Pergunta vazia.")

    resultados = base_conhecimento.buscar_contexto(req.pergunta, top_k=5)
    contexto = base_conhecimento.formatar_contexto_para_prompt(resultados)

    historico_dict = [{"autor": m.autor, "texto": m.texto} for m in req.historico]

    # ---- Calcula o estado do convite/pagamento ANTES de chamar o modelo ----
    # O modelo nunca vê o link real (só o marcador), então ele sozinho não
    # tem como saber se já convidou ou se o pagamento já caiu — isso é
    # calculado aqui, com base no histórico e no Supabase, e passado pra
    # ele como contexto extra.
    lead_atual = leads_store.buscar_lead(req.session_id) if req.session_id else None
    ja_pago = bool(lead_atual and lead_atual.get("pago"))

    def _mensagem_ja_tem_link(texto: str) -> bool:
        return "mercadopago.com" in texto or (LINK_AGENDAMENTO and LINK_AGENDAMENTO in texto)

    ja_convidou_antes = any(
        m.autor == "bot" and _mensagem_ja_tem_link(m.texto) for m in req.historico
    )

    if ja_pago:
        estado_convite = "pago"
    elif ja_convidou_antes:
        estado_convite = "convidou_pendente"
    else:
        estado_convite = "nunca_convidou"

    client_config = {}
    resolved_client_id = req.client_id
    client = None
    if req.client_slug:
        client = saas_store.get_user_by_slug(req.client_slug)
        resolved_client_id = client.get("id") if client else None
    elif req.client_id:
        client = saas_store.get_user(req.client_id)
    if req.client_slug or req.client_id:
        if not client or not client.get("active") or client.get("role") != "client":
            raise HTTPException(404, "Assistente indisponível")
        if client.get("expires_at") and datetime.fromisoformat(client["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            raise HTTPException(404, "Assistente indisponível")
        client_config = client.get("ai_config") or {}
        if req.session_id:
            lead_atual = leads_store.buscar_lead(req.session_id, resolved_client_id)
            ja_pago = bool(lead_atual and lead_atual.get("pago"))
            if ja_pago:
                estado_convite = "pago"
            elif lead_atual and lead_atual.get("workflow_status") in {"awaiting_payment", "awaiting_verification"}:
                estado_convite = "convidou_pendente"
    limite_gratuito = int(client_config.get("free_message_limit") or os.getenv("FREE_MESSAGE_LIMIT", "8"))
    historico_salvo = []
    if lead_atual:
        raw = lead_atual.get("historico") or []
        try:
            historico_salvo = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            historico_salvo = []
    mensagens_anteriores = sum(1 for m in historico_salvo if m.get("autor") == "user")
    atingiu_limite = mensagens_anteriores >= limite_gratuito
    cta_cliente = client_config.get("link_consulta")
    fallback_cliente = cta_cliente or "O canal de agendamento deste profissional ainda não foi configurado. Solicite o contato diretamente à clínica."
    if atingiu_limite and not ja_pago:
        resposta = "Já consegui entender melhor o que você busca. Para continuar com uma orientação realmente personalizada, o próximo passo é conversar com a nutricionista e avaliar seu caso com segurança. " + (fallback_cliente if resolved_client_id else LINK_AGENDAMENTO)
    else:
        try:
            resposta = gerar_resposta(req.pergunta, contexto, historico_dict, estado_convite, client_config)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Erro ao consultar o modelo de IA: {e}")

    # O Bruce usa um marcador em vez de escrever o link — aqui a gente
    # detecta a intenção de convidar pra consulta e troca pelo link real.
    #
    # TRAVA DE SEGURANÇA (independe do modelo obedecer a instrução ou não):
    # se o pagamento já foi confirmado, NUNCA gera uma preferência nova no
    # Mercado Pago — troca o marcador pelo contato de verdade direto. Isso
    # evita duplicar links/preferências e evita confundir quem já pagou.
    quis_agendar = atingiu_limite or MARCADOR_LINK_PAGAMENTO in resposta
    requires_contact = False
    if quis_agendar and resolved_client_id and not (lead_atual and lead_atual.get("lead_phone")):
        resposta = "Para enviar o link de pagamento com segurança, preciso primeiro do seu nome e WhatsApp. Preencha os dados abaixo; eles serão usados somente pela clínica para falar com você sobre este atendimento."
        requires_contact = True
    elif quis_agendar:
        if ja_pago:
            resposta = resposta.replace(MARCADOR_LINK_PAGAMENTO, CONTATO_NUTRICIONISTA)
        else:
            link_real = cta_cliente if resolved_client_id else None
            if not resolved_client_id and not link_real and pagamento.PAGAMENTO_ATIVO and req.session_id:
                link_real = pagamento.criar_link_pagamento(req.session_id)
            resposta = resposta.replace(MARCADOR_LINK_PAGAMENTO, link_real or (fallback_cliente if resolved_client_id else LINK_AGENDAMENTO))

    fontes = []
    for r in resultados:
        if r["tipo"] == "alimento":
            fontes.append(r["dado"]["nome"])
        else:
            fontes.append(r["dado"]["titulo"])

    # Salva o histórico atualizado da conversa (não derruba a resposta se falhar)
    if req.session_id:
        historico_completo = historico_dict + [
            {"autor": "user", "texto": req.pergunta},
            {"autor": "bot", "texto": resposta},
        ]
        qualification = qualificar_lead(historico_completo, quis_agendar, ja_pago)
        qualification["lead_source"] = (req.lead_source or "direto").strip().lower()[:80]
        leads_store.salvar_lead(req.session_id, historico_completo, quis_agendar, resolved_client_id, qualification)

    return RespostaResponse(resposta=resposta, fontes_utilizadas=fontes, requires_contact=requires_contact, workflow_status=(lead_atual or {}).get("workflow_status"))


@app.get("/pagamento/sucesso", response_class=HTMLResponse)
def pagamento_sucesso(
    payment_id: str = Query(default="", alias="payment_id"),
    external_reference: str = Query(default=""),
    status: str = Query(default=""),
):
    """
    Página de retorno do Mercado Pago após o pagamento. NUNCA confia só
    nesses parâmetros de URL (dá pra forjar) — sempre confere o status
    real direto na API antes de liberar qualquer contato.
    """
    pagamento_confirmado = False
    dados_pagamento = None

    if payment_id:
        dados_pagamento = pagamento.consultar_pagamento(payment_id)
    elif external_reference:
        resultados = pagamento.buscar_pagamentos_por_referencia(external_reference)
        dados_pagamento = resultados[0] if resultados else None

    session_id_confirmado = ""
    if dados_pagamento and dados_pagamento.get("status") == "approved":
        pagamento_confirmado = True
        session_id_confirmado = dados_pagamento.get("external_reference") or external_reference
        if session_id_confirmado:
            leads_store.marcar_pago(session_id_confirmado, str(dados_pagamento.get("id", payment_id)), dados_pagamento.get("transaction_amount"))

    # session_id pra usar no polling do lado pendente — o Mercado Pago
    # sempre reenvia o external_reference na URL de retorno (mesmo quando
    # o pagamento ainda não está aprovado), então dá pra usar ele aqui.
    session_id_para_poll = session_id_confirmado or external_reference

    if pagamento_confirmado:
        corpo = f"""
        <div id="conteudo">
            <h1>✅ Pagamento confirmado!</h1>
            <p>Obrigado! Aqui está o contato de {NUTRICIONISTA_NOME} pra combinar o melhor horário:</p>
            <p><a href="{CONTATO_NUTRICIONISTA}" style="font-size:18px;">Falar agora →</a></p>
        </div>
        """
        script_polling = ""
    else:
        corpo = """
        <div id="conteudo">
            <h1>Pagamento em processamento</h1>
            <p>Assim que for confirmado, o contato aparece aqui automaticamente
            — não precisa recarregar a página.</p>
            <p style="color:#888; font-size:14px;">Verificando a cada poucos segundos…</p>
        </div>
        """
        # Consulta /contato periodicamente e troca o conteúdo da página
        # sozinho quando o pagamento for liberado, sem precisar de reload.
        script_polling = f"""
        <script>
        (function() {{
            const sessionId = {session_id_para_poll!r};
            if (!sessionId) return;

            async function checarContato() {{
                try {{
                    const resp = await fetch('/contato?session_id=' + encodeURIComponent(sessionId));
                    const dados = await resp.json();
                    if (dados.liberado && dados.contato) {{
                        document.getElementById('conteudo').innerHTML = `
                            <h1>✅ Pagamento confirmado!</h1>
                            <p>Obrigado! Aqui está o contato de {NUTRICIONISTA_NOME} pra combinar o melhor horário:</p>
                            <p><a href="${{dados.contato}}" style="font-size:18px;">Falar agora →</a></p>
                        `;
                        clearInterval(intervalo);
                    }}
                }} catch (e) {{
                    // silenciosamente tenta de novo no próximo ciclo
                }}
            }}

            const intervalo = setInterval(checarContato, 4000);
            checarContato();
        }})();
        </script>
        """

    return HTMLResponse(f"""
    <html>
    <head><meta charset="UTF-8"><title>Pagamento — Bruce</title></head>
    <body style="font-family: sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; text-align: center;">
        {corpo}
        {script_polling}
    </body>
    </html>
    """)


@app.get("/pagamento/pendente", response_class=HTMLResponse)
def pagamento_pendente():
    return HTMLResponse("<h2>Pagamento pendente</h2><p>Assim que for aprovado, o contato é liberado.</p>")


@app.get("/pagamento/erro", response_class=HTMLResponse)
def pagamento_erro():
    return HTMLResponse("<h2>Pagamento não concluído</h2><p>Você pode tentar novamente na conversa com o Bruce.</p>")


@app.post("/pagamento/webhook")
async def pagamento_webhook(request: Request):
    """
    Webhook assíncrono do Mercado Pago — é a fonte da verdade sobre
    pagamentos (pode chegar mesmo que a pessoa feche a aba antes do
    redirecionamento). O Mercado Pago manda o id do pagamento como query
    param (?type=payment&data.id=XXXX) ou no corpo, dependendo da
    configuração — tratamos os dois casos.
    """
    # O Mercado Pago manda notificações de tipos diferentes pro mesmo
    # evento (ex: topic=merchant_order e topic=payment). O id que vem
    # junto de merchant_order NÃO é um payment_id — consultar a API de
    # pagamentos com ele sempre dá 404. A notificação topic=payment traz
    # o id certo e cobre o mesmo evento, então só processamos essa.
    topic = request.query_params.get("topic") or request.query_params.get("type")
    if topic == "merchant_order":
        return {"status": "ignorado", "motivo": "topic merchant_order"}

    payment_id = request.query_params.get("data.id") or request.query_params.get("id")

    if not payment_id:
        try:
            body = await request.json()
            payment_id = str(body.get("data", {}).get("id", ""))
        except Exception:
            payment_id = None

    if not payment_id:
        return {"status": "ignorado", "motivo": "sem payment_id"}

    dados = pagamento.consultar_pagamento(payment_id)
    if dados and dados.get("status") == "approved":
        session_id = dados.get("external_reference")
        if session_id:
            leads_store.marcar_pago(session_id, payment_id, dados.get("transaction_amount"))

    return {"status": "ok"}


@app.get("/agendar")
@limiter.limit("10/minute")
def agendar(request: Request, session_id: str = Query(default="")):
    """
    Usado pelo botão fixo "Agendar consulta" do front-end. Reaproveita a
    MESMA lógica de geração de link do fluxo de chat (nunca cria um
    caminho paralelo sem tracking): se o pagamento estiver ativo e a
    sessão for válida, gera uma preferência real do Mercado Pago
    (com external_reference = session_id, pra manter o webhook
    funcionando); caso contrário, cai no link fixo de agendamento.
    """
    link = None
    if pagamento.PAGAMENTO_ATIVO and session_id:
        link = pagamento.criar_link_pagamento(session_id)
    return {"url": link or LINK_AGENDAMENTO}


@app.get("/contato")
def verificar_contato(session_id: str = Query(default="")):
    """
    Endpoint que o frontend pode consultar pra saber se já pode mostrar o
    contato do nutricionista pra essa sessão (só libera se pago=true).
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id é obrigatório.")

    lead = leads_store.buscar_lead(session_id)
    liberado = bool(lead and lead.get("pago"))

    return {
        "liberado": liberado,
        "contato": CONTATO_NUTRICIONISTA if liberado else None,
    }


def painel_autorizado(request: Request, token: str) -> bool:
    if token_valido(token):
        return True
    try:
        return auth.user_from_token(request, request.cookies.get(auth.COOKIE_NAME)).get("role") == "admin"
    except HTTPException:
        return False


@app.get("/painel", response_class=HTMLResponse)
def painel_leads(request: Request, token: str = Query(default="")):
    """
    Painel simples pro nutricionista ver os leads que conversaram com o Bruce.
    Protegido por um token simples (não é autenticação robusta — dá pra
    melhorar depois, mas serve bem pro MVP).
    """
    if not painel_autorizado(request, token):
        return HTMLResponse(
            "<h2>Acesso negado</h2><p>Adicione ?token=SEU_TOKEN na URL.</p>",
            status_code=401,
        )

    leads = leads_store.listar_leads(limite=200)

    total = len(leads)
    total_agendou = sum(1 for l in leads if l.get("quis_agendar"))
    total_pago = sum(1 for l in leads if l.get("pago"))
    # Conversão calculada sobre quem pediu agendamento (base mais justa que
    # o total de conversas, já que nem toda conversa chega a pedir).
    taxa_conversao = (total_pago / total_agendou * 100) if total_agendou else 0

    linhas_html = ""
    for lead in leads:
        agendou = "✅ Sim" if lead.get("quis_agendar") else "—"
        pago = "💰 Sim" if lead.get("pago") else "—"
        atualizado = html.escape(lead.get("atualizado_em", "")[:16].replace("T", " "))
        session_id_raw = lead.get("session_id", "")
        session_curta = html.escape(session_id_raw[:8])
        link_conversa = f"/painel/conversa?token={html.escape(token, quote=True)}&session_id={html.escape(session_id_raw, quote=True)}"
        linhas_html += f"""
        <tr>
            <td>{session_curta}</td>
            <td>{atualizado}</td>
            <td>{agendou}</td>
            <td>{pago}</td>
            <td><a href="{link_conversa}">Ver conversa</a></td>
        </tr>"""

    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Painel de Leads — Bruce</title>
        <style>
            body {{ font-family: sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #ddd; }}
            th {{ background: #f4f4f4; }}
            h1 {{ margin-bottom: 4px; }}
            .total {{ color: #666; }}
            .stats {{ display: flex; gap: 16px; margin-top: 20px; flex-wrap: wrap; }}
            .card {{ background: #f4f4f4; border-radius: 10px; padding: 16px 20px; min-width: 140px; }}
            .card .valor {{ font-size: 26px; font-weight: bold; }}
            .card .rotulo {{ color: #666; font-size: 13px; }}
            .links {{ margin-top: 16px; font-size: 14px; }}
            .links a {{ margin-right: 16px; }}
        </style>
    </head>
    <body>
        <h1>Painel de Leads</h1>
        <p class="total">{total} conversas registradas</p>

        <div class="stats">
            <div class="card"><div class="valor">{total}</div><div class="rotulo">Conversas totais</div></div>
            <div class="card"><div class="valor">{total_agendou}</div><div class="rotulo">Pediram agendamento</div></div>
            <div class="card"><div class="valor">{total_pago}</div><div class="rotulo">Pagaram</div></div>
            <div class="card"><div class="valor">{taxa_conversao:.0f}%</div><div class="rotulo">Conversão (pediu → pagou)</div></div>
        </div>

        <div class="links">
            <a href="/painel/exportar?token={token}">⬇️ Exportar CSV</a>
            <a href="/painel/lembretes?token={token}">⏰ Quem precisa de lembrete</a>
        </div>

        <table>
            <tr><th>Sessão</th><th>Última atividade</th><th>Pediu agendamento?</th><th>Pagou?</th><th></th></tr>
            {linhas_html if linhas_html else '<tr><td colspan="5">Nenhum lead ainda.</td></tr>'}
        </table>
    </body>
    </html>
    """


@app.get("/painel/exportar")
def exportar_leads_csv(request: Request, token: str = Query(default="")):
    """Exporta os leads em CSV pro nutricionista abrir no Excel/Sheets."""
    if not painel_autorizado(request, token):
        raise HTTPException(status_code=401, detail="Acesso negado.")

    def _campo_seguro(valor: str) -> str:
        # Evita "CSV injection": se um campo controlado pelo usuário (ex:
        # session_id) começar com =, +, - ou @, o Excel/Sheets pode
        # interpretar como fórmula ao abrir o arquivo.
        if valor and valor[0] in ("=", "+", "-", "@"):
            return "'" + valor
        return valor

    leads = leads_store.listar_leads(limite=1000)

    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(["session_id", "criado_em", "atualizado_em", "quis_agendar", "pago", "payment_id", "pago_em"])
    for lead in leads:
        escritor.writerow([
            _campo_seguro(lead.get("session_id", "")),
            lead.get("criado_em", ""),
            lead.get("atualizado_em", ""),
            lead.get("quis_agendar", False),
            lead.get("pago", False),
            lead.get("payment_id", ""),
            lead.get("pago_em", ""),
        ])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@app.get("/painel/lembretes", response_class=HTMLResponse)
def leads_para_lembrete(request: Request, token: str = Query(default=""), dias: int = Query(default=2)):
    """
    Lista quem pediu agendamento, ainda não pagou, e está parado há X dias
    (padrão 2) — pra você mandar uma mensagem manual por enquanto. Quando
    quiser automatizar o envio (e-mail/WhatsApp), essa é a lista que serve
    de base.
    """
    if not painel_autorizado(request, token):
        return HTMLResponse("<h2>Acesso negado</h2>", status_code=401)

    leads = leads_store.listar_leads(limite=1000)
    limite_data = datetime.now(timezone.utc) - timedelta(days=dias)

    candidatos = []
    for lead in leads:
        if not lead.get("quis_agendar") or lead.get("pago"):
            continue
        atualizado_str = lead.get("atualizado_em", "")
        if not atualizado_str:
            continue
        try:
            atualizado_dt = datetime.fromisoformat(atualizado_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if atualizado_dt <= limite_data:
            candidatos.append(lead)

    linhas_html = ""
    for lead in candidatos:
        atualizado = html.escape(lead.get("atualizado_em", "")[:16].replace("T", " "))
        session_id_raw = lead.get("session_id", "")
        session_curta = html.escape(session_id_raw[:8])
        link_conversa = f"/painel/conversa?token={html.escape(token, quote=True)}&session_id={html.escape(session_id_raw, quote=True)}"
        linhas_html += f"""
        <tr>
            <td>{session_curta}</td>
            <td>{atualizado}</td>
            <td><a href="{link_conversa}">Ver conversa</a></td>
        </tr>"""

    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Lembretes pendentes — Bruce</title>
        <style>
            body {{ font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #ddd; }}
            th {{ background: #f4f4f4; }}
        </style>
    </head>
    <body>
        <p><a href="/painel?token={token}">&larr; Voltar pro painel</a></p>
        <h1>Precisam de lembrete</h1>
        <p>Pediram agendamento, não pagaram, e estão parados há {dias}+ dias.</p>
        <table>
            <tr><th>Sessão</th><th>Última atividade</th><th></th></tr>
            {linhas_html if linhas_html else '<tr><td colspan="3">Ninguém pendente por enquanto 🎉</td></tr>'}
        </table>
    </body>
    </html>
    """


@app.get("/painel/conversa", response_class=HTMLResponse)
def painel_conversa(request: Request, token: str = Query(default=""), session_id: str = Query(default="")):
    """Mostra a conversa completa de um lead específico."""
    if not painel_autorizado(request, token):
        return HTMLResponse("<h2>Acesso negado</h2>", status_code=401)

    leads = leads_store.listar_leads(limite=200)
    lead = next((l for l in leads if l.get("session_id") == session_id), None)

    if not lead:
        return HTMLResponse("<h2>Conversa não encontrada</h2>", status_code=404)

    import json
    historico = json.loads(lead.get("historico", "[]"))

    mensagens_html = ""
    for msg in historico:
        # texto e autor vêm do histórico salvo, que é 100% controlado pelo
        # navegador do visitante — NUNCA jogar direto no HTML sem escapar,
        # ou vira XSS armazenado (rouba o token do admin via document.location).
        autor_raw = msg.get("autor")
        autor = "Pessoa" if autor_raw == "user" else "Bruce"
        cor = "#EEE" if autor_raw == "user" else "#F2F1E6"
        texto_seguro = html.escape(str(msg.get("texto", ""))).replace("\n", "<br>")
        mensagens_html += f"""
        <div style="background:{cor}; padding:12px; border-radius:8px; margin-bottom:10px;">
            <strong>{autor}:</strong><br>{texto_seguro}
        </div>"""

    link_voltar = f"/painel?token={html.escape(token, quote=True)}"
    return f"""
    <html>
    <head><meta charset="UTF-8"><title>Conversa — Bruce</title></head>
    <body style="font-family: sans-serif; max-width: 700px; margin: 40px auto; padding: 0 20px;">
        <p><a href="{link_voltar}">&larr; Voltar pro painel</a></p>
        <h1>Conversa completa</h1>
        {mensagens_html}
    </body>
    </html>
    """
