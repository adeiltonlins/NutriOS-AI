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
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel, Field

from app.knowledge_base import base_conhecimento
from app.llm import gerar_resposta, LINK_AGENDAMENTO, MARCADOR_LINK_PAGAMENTO, NUTRICIONISTA_NOME
from app import leads_store
from app import pagamento
from app import auth, business_store, emailer, patient_auth, saas_store
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
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
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
        if request.method in {"POST", "PUT", "PATCH"} and request.url.path not in {"/auth/logout", "/app/api/logo"} and request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
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


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=10, max_length=128)
    new_password: str = Field(..., min_length=10, max_length=128)


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
    stage: str | None = Field(default=None, max_length=40)


class ServiceRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=600)
    price: float = Field(default=0, ge=0, le=1000000)
    payment_url: str | None = Field(default=None, max_length=500)
    active: bool = True


class AvailabilityRequest(BaseModel):
    weekday: int = Field(..., ge=0, le=6)
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    slot_minutes: int = Field(default=60, ge=15, le=240)


class AnamnesisRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=100)
    answers: dict


class AppointmentRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=100)
    starts_at: datetime
    service_id: str | None = Field(default=None, max_length=64)
    patient_name: str = Field(..., min_length=2, max_length=120)
    patient_phone: str = Field(..., min_length=8, max_length=30)


class DataRequestPayload(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=100)
    request_type: str = Field(..., pattern=r"^(export|delete)$")


class PatientRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    identifier: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=30)
    plan_name: str | None = Field(default=None, max_length=100)
    duration_days: int = Field(default=30, ge=1, le=730)
    diet_context: str | None = Field(default=None, max_length=12000)
    message_limit: int = Field(default=200, ge=1, le=5000)


class PatientLoginRequest(BaseModel):
    code: str = Field(..., min_length=8, max_length=64)


class PatientRenewRequest(BaseModel):
    duration_days: int = Field(default=30, ge=1, le=730)


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
    return FileResponse(STATIC_DIR / "login.html", headers={"Cache-Control": "no-store"})


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
def client_app(background_tasks: BackgroundTasks, user: dict = Depends(auth.current_user)):
    if user.get("role") == "client" and not user.get("password_hash"):
        return RedirectResponse("/app/primeiro-acesso", status_code=303)
    if user.get("role") == "client" and "@" in str((user.get("ai_config") or {}).get("notification_email") or user.get("identifier") or ""):
        last = _parse_data_lead(user.get("last_weekly_report_at")) if user.get("last_weekly_report_at") else None
        if not last or last < datetime.now(timezone.utc) - timedelta(days=7):
            leads = leads_store.listar_leads(limite=5000, client_id=user["id"])
            start, end = datetime.now(timezone.utc) - timedelta(days=7), datetime.now(timezone.utc)
            metrics = _metricas_periodo(leads, start, end)
            address = str((user.get("ai_config") or {}).get("notification_email") or user.get("identifier"))
            body = f"Resumo dos últimos 7 dias\nConversas: {metrics['conversations']}\nVendas: {metrics['sales']}\nFaturamento: R$ {metrics['revenue']:.2f}\nConversão: {metrics['conversion_rate']}%\nAgendamentos: {metrics['scheduled']}"
            background_tasks.add_task(emailer.send_notification, address, "Seu relatório semanal — NutriBot AI", body)
            saas_store.update_user(user["id"], {"last_weekly_report_at": datetime.now(timezone.utc).isoformat()})
    return FileResponse(STATIC_DIR / "app.html", headers={"Cache-Control": "no-store"})


@app.get("/app/primeiro-acesso")
def password_setup_page(user: dict = Depends(auth.current_user)):
    if user.get("role") != "client":
        raise HTTPException(403, "Somente clientes")
    return FileResponse(STATIC_DIR / "setup-password.html", headers={"Cache-Control": "no-store"})


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


@app.post("/app/api/senha")
def change_client_password(payload: PasswordChangeRequest, user: dict = Depends(auth.current_user)):
    if user.get("role") != "client":
        raise HTTPException(403, "Somente nutricionistas")
    if not auth.verify_password(user.get("password_hash"), payload.current_password):
        raise HTTPException(401, "Senha atual inválida")
    try:
        password_hash = auth.hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    saas_store.update_user(user["id"], {"password_hash": password_hash, "password_created_at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True}


@app.post("/app/api/logo")
async def upload_client_logo(file: UploadFile = File(...), user: dict = Depends(auth.current_user)):
    if user.get("role") != "client":
        raise HTTPException(403, "Somente nutricionistas")
    allowed = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
    if file.content_type not in allowed:
        raise HTTPException(400, "Envie uma imagem JPG, PNG ou WebP")
    content = await file.read(1_000_001)
    if len(content) > 1_000_000:
        raise HTTPException(413, "A imagem deve ter no máximo 1 MB")
    if not content:
        raise HTTPException(400, "Imagem vazia")
    public_url = saas_store.upload_public_asset(
        "nutribot-assets", f"logos/{user['id']}/{secrets.token_hex(12)}.{allowed[file.content_type]}", content, file.content_type
    )
    config = dict(user.get("ai_config") or {})
    config["logo_url"] = public_url
    saas_store.update_user(user["id"], {"ai_config": config})
    return {"ok": True, "logo_url": public_url}


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


@app.get("/app/crm")
def own_crm(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "client-crm.html")


@app.get("/app/gestao")
def own_management(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "client-management.html")


@app.get("/app/onboarding")
def onboarding_page(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "client-onboarding.html")


@app.get("/app/api/onboarding")
def onboarding_status(user: dict = Depends(auth.current_user)):
    config = user.get("ai_config") or {}
    services = business_store.list_rows("client_services", user["id"])
    availability = business_store.list_rows("availability", user["id"])
    checks = [
        {"id": "identity", "label": "Identidade profissional", "done": bool(config.get("nome") and config.get("especialidade")), "href": "/app/configuracoes"},
        {"id": "branding", "label": "Logo e mensagem inicial", "done": bool(config.get("logo_url") and config.get("mensagem_inicial")), "href": "/app/configuracoes"},
        {"id": "notification", "label": "E-mail de notificações", "done": bool(config.get("notification_email") or "@" in str(user.get("identifier"))), "href": "/app/configuracoes"},
        {"id": "service", "label": "Primeiro serviço ou plano", "done": bool(services), "href": "/app/gestao"},
        {"id": "availability", "label": "Disponibilidade da agenda", "done": bool(availability), "href": "/app/gestao"},
    ]
    done = sum(x["done"] for x in checks)
    return {"checks": checks, "completed": done, "total": len(checks), "percentage": round(done / len(checks) * 100)}


@app.get("/app/api/insights")
def lead_insights(user: dict = Depends(auth.current_user)):
    leads = leads_store.listar_leads(limite=500, client_id=user["id"])
    ranked = sorted((x for x in leads if not x.get("pago")), key=lambda x: (int(x.get("lead_score") or 0), bool(x.get("claimed_paid_at")), str(x.get("atualizado_em") or "")), reverse=True)
    return [{"session_id": x.get("session_id"), "name": x.get("lead_name") or "Visitante", "phone": x.get("lead_phone"), "score": x.get("lead_score") or 0, "reason": "Pagamento informado" if x.get("claimed_paid_at") else "Alta intenção de compra" if int(x.get("lead_score") or 0) >= 60 else "Conversa recente"} for x in ranked[:10]]


@app.get("/app/api/data-requests")
def list_data_requests(user: dict = Depends(auth.current_user)):
    return business_store.list_rows("data_requests", user["id"], order="requested_at.desc")


@app.get("/admin/api/audit")
def admin_audit(admin: dict = Depends(auth.require_admin)):
    return saas_store._request("GET", "audit_logs", params={"select": "*", "order": "created_at.desc", "limit": "500"}) or []


@app.get("/app/api/services")
def list_services(user: dict = Depends(auth.current_user)):
    return business_store.list_rows("client_services", user["id"], order="created_at.desc")


@app.post("/app/api/services")
def create_service(payload: ServiceRequest, user: dict = Depends(auth.current_user)):
    data = payload.model_dump()
    if data.get("payment_url") and not data["payment_url"].startswith("https://"):
        raise HTTPException(400, "O link de pagamento deve começar com https://")
    return business_store.create_row("client_services", user["id"], data)


@app.patch("/app/api/services/{row_id}")
def update_service(row_id: str, payload: ServiceRequest, user: dict = Depends(auth.current_user)):
    if not business_store.get_row("client_services", row_id, user["id"]):
        raise HTTPException(404, "Serviço não encontrado")
    return business_store.update_row("client_services", row_id, user["id"], payload.model_dump())


@app.delete("/app/api/services/{row_id}")
def delete_service(row_id: str, user: dict = Depends(auth.current_user)):
    if not business_store.get_row("client_services", row_id, user["id"]):
        raise HTTPException(404, "Serviço não encontrado")
    business_store.delete_row("client_services", row_id, user["id"])
    return {"ok": True}


@app.get("/app/api/availability")
def list_availability(user: dict = Depends(auth.current_user)):
    return business_store.list_rows("availability", user["id"], order="weekday.asc,start_time.asc")


@app.post("/app/api/availability")
def create_availability(payload: AvailabilityRequest, user: dict = Depends(auth.current_user)):
    if payload.start_time >= payload.end_time:
        raise HTTPException(400, "O horário final deve ser posterior ao inicial")
    return business_store.create_row("availability", user["id"], payload.model_dump())


@app.delete("/app/api/availability/{row_id}")
def delete_availability(row_id: str, user: dict = Depends(auth.current_user)):
    business_store.delete_row("availability", row_id, user["id"])
    return {"ok": True}


@app.get("/app/api/appointments")
def list_appointments(user: dict = Depends(auth.current_user)):
    return business_store.list_rows("appointments", user["id"], order="starts_at.asc")


@app.get("/app/api/anamneses")
def list_anamneses(user: dict = Depends(auth.current_user)):
    return business_store.list_rows("anamneses", user["id"], order="submitted_at.desc")


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
    if payload.action == "set_stage":
        stages = {"new", "awaiting_payment", "awaiting_verification", "payment_confirmed", "contacted", "anamnesis_sent", "scheduled"}
        if payload.stage not in stages:
            raise HTTPException(400, "Etapa inválida")
        actions["set_stage"] = {"workflow_status": payload.stage}
    if payload.action not in actions:
        raise HTTPException(400, "Ação inválida")
    updated = leads_store.atualizar_lead(session_id, actions[payload.action], client_id)
    if not updated:
        raise HTTPException(503, "Não foi possível atualizar o lead")
    business_store.audit(user["id"], updated.get("client_id"), f"lead.{payload.action}", "lead", session_id, {"stage": payload.stage, "amount": payload.amount})
    return updated


@app.get("/app/configuracoes")
def own_config(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "client-config.html")


def _owned_patient(patient_id: str, client_id: str) -> dict:
    rows = saas_store._request("GET", "patient_accounts", params={"select": "*", "id": f"eq.{patient_id}", "client_id": f"eq.{client_id}", "limit": "1"}) or []
    if not rows:
        raise HTTPException(404, "Paciente não encontrado")
    return rows[0]


@app.get("/app/pacientes")
def patient_management_page(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "client-patients.html", headers={"Cache-Control": "no-store"})


@app.get("/app/api/pacientes")
def list_patients(user: dict = Depends(auth.current_user)):
    return saas_store._request("GET", "patient_accounts", params={"select": "*", "client_id": f"eq.{user['id']}", "order": "created_at.desc"}) or []


@app.post("/app/api/pacientes")
def create_patient(payload: PatientRequest, user: dict = Depends(auth.current_user)):
    expires = datetime.now(timezone.utc) + timedelta(days=payload.duration_days)
    rows = saas_store._request("POST", "patient_accounts", payload={"client_id": user["id"], "name": payload.name.strip(), "identifier": (payload.identifier or "").strip() or None, "phone": normalizar_whatsapp(payload.phone) if payload.phone else None, "plan_name": payload.plan_name, "access_expires_at": expires.isoformat(), "diet_context": payload.diet_context, "message_limit": payload.message_limit}, prefer="return=representation")
    return rows[0]


@app.patch("/app/api/pacientes/{patient_id}")
def edit_patient(patient_id: str, payload: dict, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    allowed = {k: v for k, v in payload.items() if k in {"name", "identifier", "phone", "plan_name", "active", "diet_context", "message_limit"}}
    if "message_limit" in allowed: allowed["message_limit"] = max(1, min(5000, int(allowed["message_limit"])))
    if "phone" in allowed and allowed["phone"]: allowed["phone"] = normalizar_whatsapp(allowed["phone"])
    allowed["updated_at"] = datetime.now(timezone.utc).isoformat()
    rows = saas_store._request("PATCH", "patient_accounts", params={"id": f"eq.{patient_id}", "client_id": f"eq.{user['id']}"}, payload=allowed, prefer="return=representation") or []
    if allowed.get("active") is False: patient_auth.revoke(patient_id)
    return rows[0] if rows else None


@app.post("/app/api/pacientes/{patient_id}/codigo")
def generate_patient_code(patient_id: str, user: dict = Depends(auth.current_user)):
    patient = _owned_patient(patient_id, user["id"])
    if patient.get("archived_at") or not patient.get("active"): raise HTTPException(409, "Ative o paciente antes de gerar o código")
    return {"code": patient_auth.issue_code(patient_id, 24), "expires_in_hours": 24, "show_once": True}


@app.post("/app/api/pacientes/{patient_id}/renovar")
def renew_patient(patient_id: str, payload: PatientRenewRequest, user: dict = Depends(auth.current_user)):
    patient = _owned_patient(patient_id, user["id"]); now = datetime.now(timezone.utc)
    current = datetime.fromisoformat(patient["access_expires_at"].replace("Z", "+00:00")); base = current if current > now else now
    patient_auth.revoke(patient_id)
    rows = saas_store._request("PATCH", "patient_accounts", params={"id": f"eq.{patient_id}"}, payload={"active": True, "access_expires_at": (base + timedelta(days=payload.duration_days)).isoformat(), "messages_used": 0, "usage_started_at": now.isoformat(), "updated_at": now.isoformat()}, prefer="return=representation") or []
    return rows[0]


@app.post("/app/api/pacientes/{patient_id}/arquivar")
def archive_patient(patient_id: str, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"]); now = datetime.now(timezone.utc).isoformat(); patient_auth.revoke(patient_id)
    rows = saas_store._request("PATCH", "patient_accounts", params={"id": f"eq.{patient_id}"}, payload={"active": False, "archived_at": now, "updated_at": now}, prefer="return=representation") or []
    return rows[0]


@app.post("/app/api/pacientes/{patient_id}/restaurar")
def restore_patient(patient_id: str, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    rows = saas_store._request("PATCH", "patient_accounts", params={"id": f"eq.{patient_id}"}, payload={"archived_at": None, "active": False, "updated_at": datetime.now(timezone.utc).isoformat()}, prefer="return=representation") or []
    return rows[0]


@app.get("/paciente/login")
def patient_login_page():
    return FileResponse(STATIC_DIR / "patient-login.html", headers={"Cache-Control": "no-store"})


@app.post("/paciente/auth/login")
@limiter.limit("5/minute")
def patient_login(request: Request, payload: PatientLoginRequest, response: Response):
    patient = patient_auth.authenticate(payload.code)
    if not patient: raise HTTPException(401, "Código inválido, usado ou expirado")
    patient_auth.create_session(patient, response)
    return {"ok": True, "redirect": "/paciente"}


@app.post("/paciente/auth/logout")
def patient_logout(response: Response):
    patient_auth.logout(response); return {"ok": True}


@app.get("/paciente")
def patient_portal(patient: dict = Depends(patient_auth.current_patient)):
    return FileResponse(STATIC_DIR / "patient-portal.html", headers={"Cache-Control": "no-store"})


@app.get("/paciente/api/me")
def patient_me(patient: dict = Depends(patient_auth.current_patient)):
    client = saas_store.get_user(patient["client_id"]); config = (client or {}).get("ai_config") or {}
    return {"name": patient["name"], "plan_name": patient.get("plan_name"), "expires_at": patient["access_expires_at"], "messages_used": patient.get("messages_used") or 0, "message_limit": patient.get("message_limit") or 200, "professional_name": config.get("nome") or (client or {}).get("name"), "assistant_name": config.get("identidade_ia") or "NutriBot AI", "logo_url": config.get("logo_url"), "color": config.get("cor_principal") or "#4f7cff"}


@app.get("/app/api/configuracoes")
def own_config_data(request: Request, user: dict = Depends(auth.current_user)):
    public_url = f"{str(request.base_url).rstrip('/')}/n/{user.get('public_slug')}" if user.get("public_slug") else None
    config = dict(user.get("ai_config") or {})
    config["public_url"] = public_url
    return {"name": user["name"], "identifier": user["identifier"], "plan": user.get("plan"), "expires_at": user.get("expires_at"), "public_slug": user.get("public_slug"), "public_url": public_url, "ai_config": config}


@app.patch("/app/api/configuracoes")
def update_own_config(payload: dict, user: dict = Depends(auth.current_user)):
    current = user.get("ai_config") or {}
    allowed = {k: v for k, v in payload.items() if k in {"nome", "especialidade", "whatsapp", "link_consulta", "identidade_ia", "mensagem_inicial", "cta", "horario", "logo_url", "prompt", "free_message_limit", "crn", "cor_principal", "instagram", "acoes_rapidas", "anamnesis_url", "whatsapp_message_template", "payment_wait_message", "notification_email"}}
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
def claim_paid(request: Request, payload: LeadClaimPaidRequest, background_tasks: BackgroundTasks):
    client = resolver_cliente_publico(payload.client_slug, payload.client_id)
    lead = leads_store.buscar_lead(payload.session_id, client["id"])
    if not lead or not lead.get("contact_consent_at"):
        raise HTTPException(400, "Cadastre seus dados antes de informar o pagamento.")
    updated = leads_store.atualizar_lead(payload.session_id, {"workflow_status": "awaiting_verification", "claimed_paid_at": datetime.now(timezone.utc).isoformat()}, client["id"])
    if not updated:
        raise HTTPException(503, "Não foi possível registrar a solicitação.")
    config = client.get("ai_config") or {}
    notify_email = str(config.get("notification_email") or client.get("identifier") or "").strip()
    if "@" in notify_email:
        background_tasks.add_task(emailer.send_notification, notify_email, "Novo pagamento aguardando conferência — NutriBot AI", f"{lead.get('lead_name') or 'Um paciente'} informou que realizou o pagamento.\nWhatsApp: {lead.get('lead_phone') or 'não informado'}\nAcesse seu painel para conferir e dar continuidade.")
    return {"ok": True, "message": "Recebemos seu aviso. A clínica verificará o pagamento e entrará em contato pelo WhatsApp informado em até 24 horas.", "workflow_status": "awaiting_verification"}


@app.get("/n/{public_slug}/anamnese")
def public_anamnesis_page(public_slug: str, session_id: str = Query(default="")):
    resolver_cliente_publico(public_slug, None)
    return FileResponse(STATIC_DIR / "public-anamnesis.html")


@app.post("/public/clientes/{public_slug}/anamnese")
@limiter.limit("5/minute")
def submit_anamnesis(request: Request, public_slug: str, payload: AnamnesisRequest):
    client = resolver_cliente_publico(public_slug, None)
    lead = leads_store.buscar_lead(payload.session_id, client["id"])
    if not lead:
        raise HTTPException(404, "Atendimento não encontrado")
    clean = {str(k)[:60]: str(v)[:1000] for k, v in payload.answers.items() if str(v).strip()}
    row = business_store.upsert_anamnesis(client["id"], payload.session_id, {"answers": clean, "submitted_at": datetime.now(timezone.utc).isoformat()})
    leads_store.atualizar_lead(payload.session_id, {"workflow_status": "anamnesis_sent", "anamnesis_sent_at": datetime.now(timezone.utc).isoformat()}, client["id"])
    return {"ok": True, "id": row["id"]}


@app.get("/privacidade")
def privacy_page():
    return FileResponse(STATIC_DIR / "privacy.html")


@app.post("/public/clientes/{public_slug}/dados")
@limiter.limit("3/hour")
def request_personal_data(request: Request, public_slug: str, payload: DataRequestPayload):
    client = resolver_cliente_publico(public_slug, None)
    if not leads_store.buscar_lead(payload.session_id, client["id"]):
        raise HTTPException(404, "Atendimento não encontrado")
    row = business_store.create_row("data_requests", client["id"], {"session_id": payload.session_id, "request_type": payload.request_type, "status": "pending"})
    business_store.audit(None, client["id"], f"lgpd.{payload.request_type}_requested", "data_request", row["id"])
    return {"ok": True, "message": "Solicitação registrada. A clínica analisará o pedido com segurança."}


@app.get("/n/{public_slug}/agenda")
def public_schedule_page(public_slug: str, session_id: str = Query(default="")):
    resolver_cliente_publico(public_slug, None)
    return FileResponse(STATIC_DIR / "public-schedule.html")


@app.get("/public/clientes/{public_slug}/services")
def public_services(public_slug: str):
    client = resolver_cliente_publico(public_slug, None)
    rows = business_store.list_rows("client_services", client["id"], order="created_at.asc", extra={"active": "eq.true"})
    return [{k: row.get(k) for k in ("id", "name", "description", "price")} for row in rows]


@app.get("/public/clientes/{public_slug}/slots")
def public_slots(public_slug: str):
    client = resolver_cliente_publico(public_slug, None)
    availability = business_store.list_rows("availability", client["id"], order="weekday.asc", extra={"active": "eq.true"})
    appointments = business_store.list_rows("appointments", client["id"], order="starts_at.asc", extra={"starts_at": f"gte.{datetime.now(timezone.utc).isoformat()}"})
    occupied = {_parse_data_lead(x.get("starts_at")).astimezone(timezone.utc).isoformat()[:16] for x in appointments if x.get("status") != "cancelled" and _parse_data_lead(x.get("starts_at"))}
    slots = []
    config = client.get("ai_config") or {}
    try:
        clinic_tz = ZoneInfo(str(config.get("timezone") or "America/Recife"))
    except Exception:
        clinic_tz = ZoneInfo("America/Recife")
    today = datetime.now(clinic_tz).date()
    for offset in range(1, 31):
        day = today + timedelta(days=offset)
        for rule in availability:
            if day.weekday() != int(rule["weekday"]):
                continue
            start_h, start_m = map(int, str(rule["start_time"])[:5].split(":"))
            end_h, end_m = map(int, str(rule["end_time"])[:5].split(":"))
            cursor = datetime(day.year, day.month, day.day, start_h, start_m, tzinfo=clinic_tz)
            end = datetime(day.year, day.month, day.day, end_h, end_m, tzinfo=clinic_tz)
            while cursor + timedelta(minutes=int(rule["slot_minutes"])) <= end:
                if cursor.astimezone(timezone.utc).isoformat()[:16] not in occupied:
                    slots.append(cursor.isoformat())
                cursor += timedelta(minutes=int(rule["slot_minutes"]))
    return slots[:120]


@app.post("/public/clientes/{public_slug}/appointments")
@limiter.limit("5/minute")
def create_public_appointment(request: Request, public_slug: str, payload: AppointmentRequest, background_tasks: BackgroundTasks):
    client = resolver_cliente_publico(public_slug, None)
    lead = leads_store.buscar_lead(payload.session_id, client["id"])
    if not lead or not lead.get("pago"):
        raise HTTPException(403, "O agendamento é liberado após a confirmação do pagamento")
    if payload.starts_at <= datetime.now(timezone.utc):
        raise HTTPException(400, "Escolha um horário futuro")
    try:
        row = business_store.create_row("appointments", client["id"], {"session_id": payload.session_id, "service_id": payload.service_id, "patient_name": payload.patient_name.strip(), "patient_phone": normalizar_whatsapp(payload.patient_phone), "starts_at": payload.starts_at.isoformat(), "status": "scheduled"})
    except Exception:
        raise HTTPException(409, "Este horário acabou de ser ocupado. Escolha outro.")
    leads_store.atualizar_lead(payload.session_id, {"workflow_status": "scheduled", "scheduled_at": payload.starts_at.isoformat()}, client["id"])
    business_store.audit(None, client["id"], "appointment.created", "appointment", row["id"], {"starts_at": payload.starts_at.isoformat()})
    config = client.get("ai_config") or {}
    notify_email = str(config.get("notification_email") or client.get("identifier") or "")
    if "@" in notify_email:
        background_tasks.add_task(emailer.send_notification, notify_email, "Nova consulta agendada — NutriBot AI", f"Paciente: {payload.patient_name}\nWhatsApp: {payload.patient_phone}\nHorário: {payload.starts_at.isoformat()}")
    return {"ok": True, "appointment": row}


@app.get("/admin")
def admin_page(user: dict = Depends(auth.require_admin)):
    return FileResponse(STATIC_DIR / "admin-v2.html", headers={"Cache-Control": "no-store"})


@app.get("/admin/api/dashboard")
def admin_dashboard(user: dict = Depends(auth.require_admin)):
    all_clients = [u for u in saas_store.list_users() if u["role"] == "client"]
    clients = [u for u in all_clients if not u.get("archived_at")]
    archived_clients = [u for u in all_clients if u.get("archived_at")]
    leads = leads_store.listar_leads(limite=1000)
    now = datetime.now(timezone.utc)

    def parsed(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    def expired(client: dict) -> bool:
        value = parsed(client.get("expires_at"))
        return bool(value and value <= now)

    # Série mensal compacta para o dashboard mestre, sem serviço externo.
    month_starts = []
    cursor = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    for offset in range(5, -1, -1):
        year = cursor.year
        month = cursor.month - offset
        while month <= 0:
            month += 12
            year -= 1
        month_starts.append(datetime(year, month, 1, tzinfo=timezone.utc))

    series = {"labels": [], "new_clients": [], "conversations": [], "sales": [], "revenue": []}
    for start in month_starts:
        end = datetime(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1, tzinfo=timezone.utc)
        period_leads = [lead for lead in leads if (parsed(lead.get("criado_em")) or parsed(lead.get("atualizado_em"))) and start <= (parsed(lead.get("criado_em")) or parsed(lead.get("atualizado_em"))) < end]
        paid_leads = [lead for lead in leads if lead.get("pago") and parsed(lead.get("pago_em")) and start <= parsed(lead.get("pago_em")) < end]
        series["labels"].append(start.strftime("%m/%Y"))
        series["new_clients"].append(sum(start <= parsed(c.get("created_at")) < end for c in all_clients if parsed(c.get("created_at"))))
        series["conversations"].append(len(period_leads))
        series["sales"].append(len(paid_leads))
        series["revenue"].append(round(sum(float(lead.get("sale_amount") or 0) for lead in paid_leads), 2))

    paid_leads = [lead for lead in leads if lead.get("pago")]
    total_revenue = round(sum(float(lead.get("sale_amount") or 0) for lead in paid_leads), 2)

    return {
        "clients_total": len(clients),
        "clients_active": sum(bool(c["active"]) and not expired(c) for c in clients),
        "clients_expired": sum(expired(c) for c in clients),
        "leads_total": len(leads),
        "sales_total": len(paid_leads),
        "revenue_total": total_revenue,
        "conversion_rate": round((len(paid_leads) / len(leads) * 100) if leads else 0, 1),
        "ai_active": os.getenv("IA_ATIVA", "true").lower() == "true",
        "mrr": round(sum(float(c.get("monthly_price") or 0) for c in clients if c.get("billing_status") == "paid" and c.get("active")), 2),
        "billing_paid": sum(c.get("billing_status") == "paid" for c in clients),
        "billing_trial": sum((c.get("billing_status") or "trial") == "trial" for c in clients),
        "billing_overdue": sum(c.get("billing_status") == "overdue" for c in clients),
        "billing_due_soon": sum(bool(parsed(c.get("next_billing_at"))) and now <= parsed(c.get("next_billing_at")) <= now + timedelta(days=7) for c in clients),
        "clients": clients,
        "archived_count": len(archived_clients),
        "archived_clients": archived_clients,
        "series": series,
    }


@app.post("/admin/clientes")
def create_client(payload: ClienteRequest, admin: dict = Depends(auth.require_admin)):
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.duration_days)
    return saas_store.create_user({"name": payload.name, "identifier": payload.identifier.lower().strip(), "role": "client", "active": True, "plan": payload.plan, "expires_at": expires_at.isoformat(), "public_slug": criar_slug_publico(payload.name), "billing_status": "trial", "monthly_price": 0})


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
    allowed = {k: v for k, v in payload.items() if k in {"name", "identifier", "plan", "active", "expires_at", "ai_config", "monthly_price", "billing_status", "next_billing_at", "billing_notes", "custom_domain", "billing_provider", "external_subscription_id"}}
    if "active" in allowed and not allowed["active"]:
        saas_store.revoke_user_sessions(user_id)
    updated = saas_store.update_user(user_id, allowed)
    business_store.audit(admin["id"], user_id, "client.updated", "saas_user", user_id, {"fields": list(allowed)})
    return updated


@app.post("/admin/clientes/{user_id}/arquivar")
def archive_client(user_id: str, admin: dict = Depends(auth.require_admin)):
    client = saas_store.get_user(user_id)
    if not client or client.get("role") != "client":
        raise HTTPException(404, "Nutricionista não encontrado")
    now = datetime.now(timezone.utc).isoformat()
    saas_store.revoke_codes(user_id)
    saas_store.revoke_user_sessions(user_id)
    updated = saas_store.update_user(user_id, {"active": False, "billing_status": "cancelled", "archived_at": now})
    business_store.audit(admin["id"], user_id, "client.archived", "saas_user", user_id, {})
    return updated


@app.post("/admin/clientes/{user_id}/restaurar")
def restore_client(user_id: str, admin: dict = Depends(auth.require_admin)):
    client = saas_store.get_user(user_id)
    if not client or client.get("role") != "client":
        raise HTTPException(404, "Nutricionista não encontrado")
    updated = saas_store.update_user(user_id, {"archived_at": None, "active": False, "billing_status": "trial"})
    business_store.audit(admin["id"], user_id, "client.restored", "saas_user", user_id, {})
    return updated


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
        client_config = dict(client.get("ai_config") or {})
        patient_context = getattr(request.state, "patient_context", None)
        if patient_context:
            base_prompt = str(client_config.get("prompt") or "")
            client_config["prompt"] = (base_prompt + "\n\nCONTEXTO PRIVADO DO PACIENTE ATIVO:\n" + str(patient_context)).strip()
            client_config["free_message_limit"] = 5000
            ja_pago = True
            estado_convite = "pago"
        if req.session_id and not patient_context:
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


@app.post("/paciente/api/chat", response_model=RespostaResponse)
@limiter.limit("10/minute")
def patient_private_chat(request: Request, req: PerguntaRequest, patient: dict = Depends(patient_auth.current_patient)):
    used = int(patient.get("messages_used") or 0); limit = int(patient.get("message_limit") or 200)
    if used >= limit:
        raise HTTPException(429, "Seu limite de mensagens foi atingido. Fale com seu nutricionista para renovar ou ampliar o plano.")
    req.client_id = patient["client_id"]; req.client_slug = None; req.lead_source = "patient_portal"
    request.state.patient_context = patient.get("diet_context") or "Paciente ativo em acompanhamento. Responda apenas dentro das orientações gerais do nutricionista e encaminhe questões clínicas ao profissional."
    response = chat(request, req)
    saas_store._request("PATCH", "patient_accounts", params={"id": f"eq.{patient['id']}"}, payload={"messages_used": used + 1, "last_access_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")
    return response


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
