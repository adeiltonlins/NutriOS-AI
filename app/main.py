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
import math
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel, Field

from app.knowledge_base import base_conhecimento
from app.llm import gerar_resposta, LINK_AGENDAMENTO, MARCADOR_LINK_PAGAMENTO, NUTRICIONISTA_NOME
from app import leads_store
from app import pagamento
from app import auth, business_store, emailer, patient_auth, saas_store, clinical_extensions
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
app.include_router(clinical_extensions.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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
    is_patient_pdf = request.method == "POST" and request.url.path.endswith("/documentos") and request.url.path.startswith("/app/api/pacientes/")
    is_clinical_image = request.method == "POST" and (request.url.path.endswith("/fotos-evolucao") or request.url.path == "/paciente/api/diario/foto")
    body_limit = 10_500_000 if is_patient_pdf else (8_500_000 if is_clinical_image else MAX_BODY_BYTES)
    if length and int(length) > body_limit:
        return Response("Corpo da requisição excede o limite", status_code=413)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path != "/pagamento/webhook":
        origin = request.headers.get("origin")
        if origin:
            # Sempre aceite requisições same-origin do próprio host atual.
            # Isso mantém a proteção contra CSRF/origens externas e permite
            # domínios personalizados (ex.: usenutrios.com.br) sem depender
            # exclusivamente de URL_BASE/ALLOWED_ORIGINS.
            current_origin = f"{request.url.scheme}://{request.url.netloc}".rstrip("/")
            configured_origins = {x.rstrip("/") for x in ALLOWED_ORIGINS}
            allowed_origins = configured_origins | {current_origin}
            if origin.rstrip("/") not in allowed_origins:
                return Response("Origem não autorizada", status_code=403)
        multipart_allowed = request.url.path == "/app/api/logo" or is_patient_pdf or is_clinical_image
        # Requisições sem corpo (por exemplo, ações PATCH idempotentes) não
        # possuem mídia para validar. Quando houver corpo, JSON continua
        # obrigatório, preservando a proteção já existente.
        has_body = bool(
            int(request.headers.get("content-length") or "0") > 0
            or request.headers.get("transfer-encoding")
        )
        if request.method in {"POST", "PUT", "PATCH"} and has_body and request.url.path != "/auth/logout" and not multipart_allowed and request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
            return Response("Content-Type inválido", status_code=415)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    # O laboratório mestre usa um iframe da própria origem. Qualquer outra
    # página continua proibida de ser embutida por sites externos.
    is_admin_preview = (
        bool(re.fullmatch(r"/admin/testes/[^/]+/chat", request.url.path))
        or (request.url.path == "/static/index.html" and bool(request.query_params.get("admin_test")))
    )
    response.headers["X-Frame-Options"] = "SAMEORIGIN" if is_admin_preview else "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(self)"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if request.url.scheme == "https" or os.getenv("URL_BASE", "").lower().startswith("https://"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/")
def servir_interface():
    """Vitrine comercial com conversa real, limitada pela configuração mestre."""
    return FileResponse(STATIC_DIR / "saas-landing.html", headers={"Cache-Control": "no-store"})


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
    test_mode: bool = False


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
    patient_limit: int | None = Field(default=None, ge=-1, le=100000)


class AdminDeleteRequest(BaseModel):
    confirmation: str = Field(..., min_length=3, max_length=220)
    master_code: str = Field(..., min_length=1, max_length=512)


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
    code: str | None = Field(default=None, min_length=8, max_length=64)
    identifier: str | None = Field(default=None, min_length=4, max_length=160)
    password: str | None = Field(default=None, min_length=10, max_length=128)


class PatientCredentialRequest(BaseModel):
    identifier: str = Field(..., min_length=4, max_length=160)
    password: str = Field(..., min_length=10, max_length=128)


class PatientCodeRequest(BaseModel):
    expires_in_hours: int = Field(default=24, ge=1, le=8760)


class PatientRenewRequest(BaseModel):
    duration_days: int = Field(default=30, ge=1, le=730)


class PatientRecordRequest(BaseModel):
    notes: str = Field(default="", max_length=12000)
    hunger_status: str | None = Field(default=None, max_length=30)
    energy_status: str | None = Field(default=None, max_length=30)
    sleep_status: str | None = Field(default=None, max_length=30)
    bowel_status: str | None = Field(default=None, max_length=30)
    adherence_status: str | None = Field(default=None, max_length=30)
    clinical_alerts: str | None = Field(default=None, max_length=3000)


class PatientCheckinRequest(BaseModel):
    hunger: int = Field(..., ge=0, le=10)
    energy: int = Field(..., ge=0, le=10)
    sleep: int = Field(..., ge=0, le=10)
    adherence: int = Field(..., ge=0, le=10)
    water_liters: float | None = Field(default=None, ge=0, le=20)
    training_sessions: int | None = Field(default=None, ge=0, le=30)
    weight_kg: float | None = Field(default=None, ge=20, le=500)
    bowel_status: str | None = Field(default=None, max_length=80)
    cravings: bool = False
    symptoms: str | None = Field(default=None, max_length=2000)
    difficulties: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=3000)


class AnthropometryRequest(BaseModel):
    assessed_at: str | None = None
    weight_kg: float | None = Field(default=None, ge=20, le=500)
    height_cm: float | None = Field(default=None, ge=80, le=250)
    waist_cm: float | None = Field(default=None, ge=20, le=300)
    hip_cm: float | None = Field(default=None, ge=20, le=300)
    body_fat_percent: float | None = Field(default=None, ge=0, le=80)
    muscle_mass_kg: float | None = Field(default=None, ge=0, le=300)
    body_water_percent: float | None = Field(default=None, ge=0, le=100)
    evaluation_method: str | None = Field(default=None, max_length=120)
    front_photo_id: str | None = Field(default=None, max_length=80)
    side_photo_id: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=3000)


class MealPlanRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=160)
    objective: str | None = Field(default=None, max_length=1000)
    content: list[dict] = Field(default_factory=list, max_length=30)
    professional_notes: str | None = Field(default=None, max_length=5000)
    patient_notes: str | None = Field(default=None, max_length=5000)
    template_name: str | None = Field(default=None, max_length=120)
    is_template: bool = False
    signature_text: str | None = Field(default=None, max_length=300)


class EnergyCalculationRequest(BaseModel):
    weight_kg: float = Field(..., ge=20, le=500)
    height_cm: float = Field(..., ge=80, le=250)
    age: int = Field(..., ge=12, le=120)
    sex: str = Field(..., pattern=r"^(female|male|other)$")
    activity_factor: float = Field(default=1.2, ge=1.0, le=2.5)
    goal: str = Field(default="maintenance", pattern=r"^(loss|maintenance|gain)$")
    protein_g_per_kg: float = Field(default=1.6, ge=0.8, le=3.5)
    fat_percent: float = Field(default=25, ge=15, le=45)


class FullAnamnesisRequest(BaseModel):
    birth_date: str | None = None
    sex: str | None = Field(default=None, pattern=r"^(female|male|other)$")
    occupation: str | None = Field(default=None, max_length=160)
    objective: str | None = Field(default=None, max_length=1000)
    diagnoses: str | None = Field(default=None, max_length=3000)
    medications: str | None = Field(default=None, max_length=3000)
    allergies: str | None = Field(default=None, max_length=2000)
    intolerances: str | None = Field(default=None, max_length=2000)
    surgeries: str | None = Field(default=None, max_length=2000)
    family_history: str | None = Field(default=None, max_length=3000)
    food_routine: str | None = Field(default=None, max_length=5000)
    preferred_foods: str | None = Field(default=None, max_length=3000)
    disliked_foods: str | None = Field(default=None, max_length=3000)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    sleep_quality: str | None = Field(default=None, max_length=80)
    bowel_habits: str | None = Field(default=None, max_length=500)
    water_liters: float | None = Field(default=None, ge=0, le=20)
    exercise: str | None = Field(default=None, max_length=2000)
    alcohol: str | None = Field(default=None, max_length=500)
    smoking: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    lgpd_consent: bool = False
    lgpd_consent_version: str = Field(default="1.0", max_length=20)


class DiaryFeedbackRequest(BaseModel):
    professional_feedback: str = Field(..., min_length=2, max_length=3000)


class FoodDiaryRequest(BaseModel):
    meal_type: str = Field(..., min_length=2, max_length=60)
    consumed_at: datetime | None = None
    description: str = Field(..., min_length=2, max_length=3000)
    hunger_before: int | None = Field(default=None, ge=0, le=10)
    satiety_after: int | None = Field(default=None, ge=0, le=10)
    mood: str | None = Field(default=None, max_length=80)
    symptoms: str | None = Field(default=None, max_length=1000)


class TransactionRequest(BaseModel):
    patient_id: str | None = Field(default=None, max_length=64)
    kind: str = Field(..., pattern=r"^(income|expense)$")
    category: str = Field(default="consulta", max_length=80)
    description: str = Field(..., min_length=2, max_length=300)
    amount: float = Field(..., ge=0, le=10000000)
    status: str = Field(default="pending", pattern=r"^(pending|paid|cancelled)$")
    due_date: str | None = None


class PatientAppointmentRequest(BaseModel):
    starts_at: datetime
    end_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ReminderRequest(BaseModel):
    patient_id: str | None = Field(default=None, max_length=64)
    title: str = Field(..., min_length=2, max_length=200)
    reminder_at: datetime
    type: str = Field(default="followup", max_length=60)
    notes: str | None = Field(default=None, max_length=1000)


class WorkoutPlanRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=160)
    goal: str | None = Field(default=None, max_length=500)
    exercises: list[dict] = Field(default_factory=list, max_length=40)
    professional_notes: str | None = Field(default=None, max_length=3000)
    patient_notes: str | None = Field(default=None, max_length=3000)


class WorkoutLogRequest(BaseModel):
    sleep: int = Field(..., ge=1, le=5)
    energy: int = Field(..., ge=1, le=5)
    pain: int = Field(..., ge=0, le=5)
    perceived_exertion: int = Field(..., ge=1, le=10)
    exercise_results: list[dict] = Field(default_factory=list, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)


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
    if client_id == "master":
        admins = [u for u in saas_store.list_users() if u.get("role") == "admin" and u.get("active")]
        if not admins:
            raise HTTPException(404, "Assistente indisponível")
        return admins[0]
    client = saas_store.get_user_by_slug(client_slug) if client_slug else saas_store.get_user(client_id) if client_id else None
    if not client or client.get("role") != "client" or not client.get("active"):
        raise HTTPException(404, "Assistente indisponível")
    if client.get("expires_at") and datetime.fromisoformat(client["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        raise HTTPException(404, "Assistente indisponível")
    return client


def master_chat_user() -> dict | None:
    """Conta mestre que também funciona como tenant de demonstração real."""
    try:
        admins = [u for u in saas_store.list_users() if u.get("role") == "admin" and u.get("active")]
        return admins[0] if admins else None
    except Exception:
        # Mantém o chatbot legado operacional em ambiente local sem banco.
        return None


def payment_next_steps(lead: dict | None, owner: dict | None, base_url: str = "") -> dict:
    """Monta somente ações pós-pagamento verificadas pelo backend."""
    if not lead or not lead.get("pago"):
        return {"liberado": False, "workflow_status": (lead or {}).get("workflow_status")}
    config = dict((owner or {}).get("ai_config") or {})
    raw_whatsapp = str(config.get("whatsapp") or "").strip()
    whatsapp_url = CONTATO_NUTRICIONISTA
    if raw_whatsapp:
        try:
            phone = normalizar_whatsapp(raw_whatsapp)
            message = str(config.get("whatsapp_message_template") or "Olá! Meu pagamento foi confirmado no NutriOS e gostaria de continuar meu atendimento.").strip()
            from urllib.parse import quote
            whatsapp_url = f"https://wa.me/{phone}?text={quote(message)}"
        except HTTPException:
            pass
    public_slug = (owner or {}).get("public_slug")
    path = f"/n/{public_slug}/anamnese" if public_slug else "/assistente/anamnese"
    anamnesis_url = f"{base_url.rstrip('/')}{path}?session_id={lead.get('session_id', '')}"
    return {
        "liberado": True,
        "workflow_status": "payment_confirmed",
        "message": "Pagamento confirmado! Você já pode preencher sua anamnese e falar com o profissional. O atendimento humano pode ocorrer em até 24 horas.",
        "contato": whatsapp_url,
        "whatsapp_url": whatsapp_url,
        "anamnesis_url": anamnesis_url,
        "response_deadline_hours": 24,
    }


def public_chat_config(user: dict) -> dict:
    config = dict(user.get("ai_config") or {})
    safe_keys = {"nome", "especialidade", "identidade_ia", "mensagem_inicial", "horario", "logo_url", "crn", "cor_principal", "instagram", "acoes_rapidas"}
    safe = {k: config.get(k) for k in safe_keys if config.get(k)}
    safe["nome"] = safe.get("nome") or user.get("name") or "NutriOS"
    safe["identidade_ia"] = safe.get("identidade_ia") or f"Assistente de {safe['nome']}"
    color = safe.get("cor_principal", "#2563eb")
    safe["cor_principal"] = color if re.fullmatch(r"#[0-9a-fA-F]{6}", str(color)) else "#2563eb"
    if safe.get("logo_url") and not str(safe["logo_url"]).startswith("https://"):
        safe.pop("logo_url", None)
    if safe.get("instagram") and not str(safe["instagram"]).startswith("https://"):
        safe.pop("instagram", None)
    return safe


def normalizar_whatsapp(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if not 10 <= len(digits) <= 15:
        raise HTTPException(400, "Informe um WhatsApp válido com DDD e código do país.")
    # No Brasil é comum informar apenas DDD + número. O wa.me exige o
    # código do país; números já internacionais permanecem inalterados.
    if len(digits) in {10, 11}:
        digits = f"55{digits}"
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
    except RuntimeError:
        raise HTTPException(503, "Serviço de autenticação temporariamente indisponível")
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
            background_tasks.add_task(emailer.send_notification, address, "Seu relatório semanal — NutriOS", body)
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


@app.get("/assistente")
def master_public_chat():
    if not master_chat_user():
        raise HTTPException(404, "Assistente indisponível")
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/public/chatbot-mestre")
def master_public_branding():
    user = master_chat_user()
    if not user:
        raise HTTPException(404, "Assistente indisponível")
    return public_chat_config(user)


@app.get("/n/{public_slug}")
def public_client_chat(public_slug: str):
    client = saas_store.get_user_by_slug(public_slug)
    if not client or client.get("role") != "client" or not client.get("active"):
        raise HTTPException(404, "Assistente indisponível")
    if client.get("expires_at") and datetime.fromisoformat(client["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        raise HTTPException(404, "Assistente indisponível")
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/public/clientes/{public_slug}")
def public_client_branding(public_slug: str):
    client = saas_store.get_user_by_slug(public_slug)
    if not client or client.get("role") != "client" or not client.get("active"):
        raise HTTPException(404, "Assistente indisponível")
    if client.get("expires_at") and datetime.fromisoformat(client["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        raise HTTPException(404, "Assistente indisponível")
    return public_chat_config(client)


@app.get("/app/leads")
def own_leads(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "client-leads.html")


@app.get("/app/conversas")
def own_conversations(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "client-conversations.html", headers={"Cache-Control": "no-store"})


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


_TACO_ROWS = json.loads((Path(__file__).resolve().parents[1] / "data" / "alimentos_taco.json").read_text(encoding="utf-8"))
_TACO_BY_ID = {int(row["id"]): row for row in _TACO_ROWS}


def _meal_plan_content(content: list[dict], custom_foods: dict[str, dict] | None = None) -> tuple[list[dict], dict]:
    clean: list[dict] = []
    totals = {"kcal": 0.0, "proteina_g": 0.0, "carboidrato_g": 0.0, "lipideos_g": 0.0, "fibra_g": 0.0, "sodio_mg": 0.0}
    for meal in content[:30]:
        meal_name = str(meal.get("name") or "Refeição")[:80]
        items = []
        for raw in list(meal.get("items") or [])[:40]:
            food_id = raw.get("food_id")
            try:
                food = _TACO_BY_ID.get(int(food_id or 0))
            except (TypeError, ValueError):
                food = (custom_foods or {}).get(str(food_id).replace("custom:", ""))
            grams = max(1.0, min(2000.0, float(raw.get("grams") or 0)))
            if not food:
                continue
            factor = grams / 100.0
            snapshot = {"food_id": food["id"], "name": food.get("nome") or food.get("name"), "grams": grams, "source": food.get("source") or "taco", "substitutions": [str(x)[:120] for x in list(raw.get("substitutions") or [])[:8]]}
            for key in totals:
                source = key if key != "kcal" else "kcal"
                value = round(float(food.get(source) or (food.get("nutrients") or {}).get(source) or 0) * factor, 2)
                snapshot[key] = value
                totals[key] += value
            items.append(snapshot)
        if items:
            clean.append({"name": meal_name, "time": str(meal.get("time") or "")[:5], "items": items})
    return clean, {key: round(value, 2) for key, value in totals.items()}


def _energy_targets(payload: EnergyCalculationRequest) -> dict:
    sex_adjustment = 5 if payload.sex == "male" else (-161 if payload.sex == "female" else -78)
    bmr = 10 * payload.weight_kg + 6.25 * payload.height_cm - 5 * payload.age + sex_adjustment
    expenditure = bmr * payload.activity_factor
    target = expenditure + ({"loss": -400, "maintenance": 0, "gain": 300}[payload.goal])
    protein = payload.weight_kg * payload.protein_g_per_kg
    fat = target * (payload.fat_percent / 100) / 9
    carbs = max(0, (target - protein * 4 - fat * 9) / 4)
    return {"bmr_kcal": round(bmr), "expenditure_kcal": round(expenditure), "target_kcal": round(target), "protein_g": round(protein), "fat_g": round(fat), "carbohydrate_g": round(carbs), "formula": "Mifflin-St Jeor", "requires_professional_review": True}


def _refresh_clinical_alerts(patient: dict, checkins: list[dict], assessments: list[dict], client_id: str) -> list[dict]:
    all_alerts = business_store.list_rows("clinical_alerts", client_id, order="created_at.desc", extra={"patient_id": f"eq.{patient['id']}"})
    existing = [row for row in all_alerts if not row.get("resolved_at")]
    active_types = {x.get("alert_type") for x in existing}
    cooldown = datetime.now(timezone.utc) - timedelta(days=7)
    recently_resolved = {
        row.get("alert_type") for row in all_alerts
        if row.get("resolved_at") and _parse_data_lead(row.get("resolved_at"))
        and _parse_data_lead(row.get("resolved_at")) >= cooldown
    }
    candidates = []
    latest = checkins[0] if checkins else {}
    if latest and (int(latest.get("energy") or 10) <= 3 or int(latest.get("sleep") or 10) <= 3): candidates.append(("low_wellbeing", "high", "Check-in com energia ou sono muito baixos"))
    if latest and latest.get("symptoms"): candidates.append(("symptoms", "high", "Paciente relatou sintomas no check-in"))
    if latest and int(latest.get("adherence") or 10) <= 3: candidates.append(("low_adherence", "medium", "Baixa adesão ao plano"))
    if len(assessments) >= 2 and assessments[0].get("weight_kg") and assessments[1].get("weight_kg"):
        delta = abs(float(assessments[0]["weight_kg"]) - float(assessments[1]["weight_kg"]))
        if delta >= max(3, float(assessments[1]["weight_kg"]) * .05): candidates.append(("weight_change", "medium", "Variação relevante de peso entre avaliações"))
    if not checkins: candidates.append(("missing_checkin", "low", "Paciente ainda não realizou check-in"))
    for alert_type, severity, title in candidates:
        if alert_type not in active_types and alert_type not in recently_resolved:
            business_store.create_row("clinical_alerts", client_id, {"patient_id": patient["id"], "alert_type": alert_type, "severity": severity, "title": title})
    return business_store.list_rows("clinical_alerts", client_id, order="created_at.desc", extra={"patient_id": f"eq.{patient['id']}", "resolved_at": "is.null"})



# NutriOS V22 — compatibility aliases for dashboard navigation
@app.get("/app/agenda")
def app_agenda_alias(user: dict = Depends(auth.current_user)):
    return RedirectResponse("/app/gestao", status_code=307)

@app.get("/app/planos")
def app_planos_alias(user: dict = Depends(auth.current_user)):
    return RedirectResponse("/app/clinica#planos", status_code=307)

@app.get("/app/evolucao")
def app_evolucao_alias(user: dict = Depends(auth.current_user)):
    return RedirectResponse("/app/clinica#evolucao", status_code=307)

@app.get("/app/analise-corporal")
def app_analise_corporal_alias(user: dict = Depends(auth.current_user)):
    return RedirectResponse("/app/clinica#assessment", status_code=307)

@app.get("/app/financeiro")
def app_financeiro_alias(user: dict = Depends(auth.current_user)):
    return RedirectResponse("/app/metricas", status_code=307)

@app.get("/app/relatorios")
def app_relatorios_alias(user: dict = Depends(auth.current_user)):
    return RedirectResponse("/app/metricas", status_code=307)

@app.get("/app/pacientes")
def patient_management_page(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "client-patients.html", headers={"Cache-Control": "no-store"})


@app.get("/app/clinica")
def clinical_dashboard_page(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "clinical-dashboard.html", headers={"Cache-Control": "no-store"})


@app.get("/app/treinos")
def training_module_page(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "training-module.html", headers={"Cache-Control": "no-store"})


def _clean_exercises(exercises: list[dict]) -> list[dict]:
    clean = []
    for raw in exercises[:40]:
        name = str(raw.get("name") or "").strip()[:120]
        if not name: continue
        clean.append({"name": name, "sets": max(1, min(20, int(raw.get("sets") or 1))), "reps": str(raw.get("reps") or "")[:30], "load": str(raw.get("load") or "")[:40], "rest_seconds": max(0, min(900, int(raw.get("rest_seconds") or 0))), "instructions": str(raw.get("instructions") or "")[:500]})
    if not clean: raise HTTPException(400, "Adicione pelo menos um exercício")
    return clean


@app.get("/app/api/treinos/config")
def training_config(user: dict = Depends(auth.current_user)):
    return {"enabled": bool((user.get("ai_config") or {}).get("training_enabled"))}


@app.patch("/app/api/treinos/config")
def update_training_config(payload: dict, user: dict = Depends(auth.current_user)):
    config = dict(user.get("ai_config") or {}); config["training_enabled"] = bool(payload.get("enabled"))
    saas_store.update_user(user["id"], {"ai_config": config})
    business_store.audit(user["id"], user["id"], "training.config.updated", "training", metadata={"enabled": config["training_enabled"]})
    return {"ok": True, "enabled": config["training_enabled"]}


@app.get("/app/api/treinos")
def list_workout_plans(patient_id: str | None = None, user: dict = Depends(auth.current_user)):
    return business_store.list_rows("workout_plans", user["id"], order="created_at.desc", extra={"patient_id": f"eq.{patient_id}"} if patient_id else None)


@app.post("/app/api/pacientes/{patient_id}/treinos")
def create_workout_plan(patient_id: str, payload: WorkoutPlanRequest, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    if not (user.get("ai_config") or {}).get("training_enabled"): raise HTTPException(409, "Ative o módulo de treinos antes de criar uma ficha")
    data = payload.model_dump(exclude_none=True); data["patient_id"] = patient_id; data["exercises"] = _clean_exercises(payload.exercises)
    return business_store.create_row("workout_plans", user["id"], data)


@app.patch("/app/api/treinos/{plan_id}/publicar")
def publish_workout_plan(plan_id: str, user: dict = Depends(auth.current_user)):
    plan = business_store.get_row("workout_plans", plan_id, user["id"])
    if not plan: raise HTTPException(404, "Treino não encontrado")
    now = datetime.now(timezone.utc).isoformat()
    saas_store._request("PATCH", "workout_plans", params={"client_id": f"eq.{user['id']}", "patient_id": f"eq.{plan['patient_id']}", "status": "eq.published"}, payload={"status": "archived", "updated_at": now}, prefer="return=minimal")
    return business_store.update_row("workout_plans", plan_id, user["id"], {"status": "published", "published_at": now, "updated_at": now})


@app.get("/app/api/dashboard-clinico")
def clinical_dashboard_data(user: dict = Depends(auth.current_user)):
    client_id = user["id"]
    def optional_rows(loader):
        try:
            return loader() or []
        except Exception as exc:
            print(f"[dashboard-clinico] Modulo opcional indisponivel: {type(exc).__name__}")
            return []

    patients = optional_rows(lambda: saas_store._request("GET", "patient_accounts", params={"select": "id,name,active,access_expires_at,last_seen_at,created_at,macro_targets", "client_id": f"eq.{client_id}", "hidden_at": "is.null", "order": "created_at.desc"}))
    for patient in patients:
        patient_checkins = optional_rows(lambda p=patient: business_store.list_rows("patient_checkins", client_id, order="created_at.desc", extra={"patient_id": f"eq.{p['id']}", "limit": "50"}))
        patient_assessments = optional_rows(lambda p=patient: business_store.list_rows("anthropometric_assessments", client_id, order="assessed_at.desc", extra={"patient_id": f"eq.{p['id']}", "limit": "10"}))
        try:
            _refresh_clinical_alerts(patient, patient_checkins, patient_assessments, client_id)
        except Exception as exc:
            print(f"[dashboard-clinico] Alertas indisponiveis: {type(exc).__name__}")
    alerts = optional_rows(lambda: business_store.list_rows("clinical_alerts", client_id, order="created_at.desc", extra={"resolved_at": "is.null"}))
    appointments = optional_rows(lambda: business_store.list_rows("appointments", client_id, order="starts_at.asc", extra={"starts_at": f"gte.{datetime.now(timezone.utc).isoformat()}", "limit": "12"}))
    plans = optional_rows(lambda: business_store.list_rows("meal_plans", client_id, order="created_at.desc"))
    transactions = optional_rows(lambda: business_store.list_rows("clinic_transactions", client_id, order="created_at.desc"))
    checkins = optional_rows(lambda: business_store.list_rows("patient_checkins", client_id, order="created_at.desc"))
    assessments = optional_rows(lambda: business_store.list_rows("anthropometric_assessments", client_id, order="assessed_at.desc"))
    leads = optional_rows(lambda: leads_store.listar_leads(limite=500, client_id=client_id))
    patient_names = {p["id"]: p["name"] for p in patients}
    for collection in (alerts, plans, checkins):
        for row in collection:
            row["patient_name"] = patient_names.get(row.get("patient_id"), "Paciente")
    for row in appointments:
        row["patient_name"] = patient_names.get(row.get("patient_id")) or row.get("patient_name") or "Paciente"
    today = datetime.now(timezone.utc).date()
    paid = [r for r in transactions if r.get("status") == "paid" and r.get("kind") == "income"]
    monthly_income = sum(float(r.get("amount") or 0) for r in paid if str(r.get("paid_at") or r.get("created_at") or "")[:7] == today.isoformat()[:7])
    latest_checkin = {}
    for row in checkins:
        latest_checkin.setdefault(row.get("patient_id"), row)
    paid_leads = [lead for lead in leads if lead.get("pago")]
    appointment_leads = [lead for lead in leads if lead.get("quis_agendar")]
    qualified_leads = [lead for lead in leads if int(lead.get("lead_score") or 0) >= 60 or str(lead.get("lead_status") or "").lower() in {"quente", "convertido"}]

    # Dashboard analítico real: séries calculadas exclusivamente a partir dos
    # registros do próprio profissional. Nenhum valor de demonstração é usado.
    now = datetime.now(timezone.utc)
    months = []
    cursor = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    for _ in range(11, -1, -1):
        offset = _
        year = cursor.year
        month = cursor.month - offset
        while month <= 0:
            month += 12
            year -= 1
        months.append(f"{year:04d}-{month:02d}")

    finance_map = {m: {"income": 0.0, "expense": 0.0} for m in months}
    for row in transactions:
        if row.get("status") != "paid":
            continue
        stamp = str(row.get("competence_month") or row.get("paid_at") or row.get("created_at") or "")[:7]
        if stamp not in finance_map:
            continue
        amount = float(row.get("amount") or 0)
        if row.get("kind") == "income":
            finance_map[stamp]["income"] += amount
        elif row.get("kind") == "expense":
            finance_map[stamp]["expense"] += amount

    patient_map = {m: 0 for m in months}
    for patient in patients:
        stamp = str(patient.get("created_at") or "")[:7]
        if stamp in patient_map:
            patient_map[stamp] += 1

    appointment_map = {m: {"scheduled": 0, "completed": 0, "cancelled": 0, "other": 0} for m in months}
    all_appointments = optional_rows(lambda: business_store.list_rows("appointments", client_id, order="starts_at.desc"))
    for row in all_appointments:
        stamp = str(row.get("starts_at") or row.get("created_at") or "")[:7]
        if stamp not in appointment_map:
            continue
        status = str(row.get("status") or "scheduled").lower()
        if status in {"scheduled", "confirmed", "pending"}:
            appointment_map[stamp]["scheduled"] += 1
        elif status in {"completed", "done", "attended", "realized"}:
            appointment_map[stamp]["completed"] += 1
        elif status in {"cancelled", "canceled", "no_show"}:
            appointment_map[stamp]["cancelled"] += 1
        else:
            appointment_map[stamp]["other"] += 1

    adherence_buckets = {m: [] for m in months}
    for row in checkins:
        stamp = str(row.get("created_at") or "")[:7]
        if stamp in adherence_buckets and row.get("adherence") is not None:
            adherence_buckets[stamp].append(float(row.get("adherence") or 0))

    assessment_map = {m: 0 for m in months}
    for row in assessments:
        stamp = str(row.get("assessed_at") or row.get("created_at") or "")[:7]
        if stamp in assessment_map:
            assessment_map[stamp] += 1

    finance_series = []
    appointment_series = []
    for month in months:
        f = finance_map[month]
        finance_series.append({"month": month, "income": round(f["income"], 2), "expense": round(f["expense"], 2), "balance": round(f["income"] - f["expense"], 2)})
        a = appointment_map[month]
        appointment_series.append({"month": month, **a, "total": sum(a.values())})

    analytics = {
        "months": months,
        "finance": finance_series,
        "patients_new": [{"month": m, "value": patient_map[m]} for m in months],
        "patient_status": {"active": sum(bool(p.get("active")) for p in patients), "inactive": sum(not bool(p.get("active")) for p in patients)},
        "appointments": appointment_series,
        "checkin_adherence": [{"month": m, "value": round(sum(adherence_buckets[m]) / len(adherence_buckets[m]), 1) if adherence_buckets[m] else None, "count": len(adherence_buckets[m])} for m in months],
        "assessments": [{"month": m, "value": assessment_map[m]} for m in months],
        "totals": {
            "transactions": len(transactions),
            "appointments": len(all_appointments),
            "checkins": len(checkins),
            "assessments": len(assessments),
        },
    }

    return {
        "metrics": {"patients": len(patients), "active": sum(bool(p.get("active")) for p in patients), "open_alerts": len(alerts), "upcoming_appointments": len(appointments), "monthly_income": round(monthly_income, 2), "without_checkin": sum(p["id"] not in latest_checkin for p in patients), "visitors": len(leads), "qualified_leads": len(qualified_leads), "appointment_leads": len(appointment_leads), "converted_leads": len(paid_leads)},
        "analytics": analytics,
        "patients": patients, "alerts": alerts[:30], "appointments": appointments, "plans": plans[:30], "checkins": list(latest_checkin.values())[:30]
    }


@app.patch("/app/api/alertas/{alert_id}/resolver")
def resolve_clinical_alert(alert_id: str, user: dict = Depends(auth.current_user)):
    resolved_at = datetime.now(timezone.utc).isoformat()
    alert = business_store.update_row("clinical_alerts", alert_id, user["id"], {"resolved_at": resolved_at})
    if not alert:
        # A consulta inclui client_id: um profissional não consegue resolver
        # alerta pertencente a outra conta.
        raise HTTPException(404, "Alerta não encontrado ou já resolvido")
    business_store.audit(user["id"], user["id"], "clinical_alert.resolved", "clinical_alert", alert_id)
    return {"status": "resolved", "alert": alert}


@app.get("/app/pacientes/{patient_id}")
def patient_record_page(patient_id: str, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    return FileResponse(STATIC_DIR / "patient-record.html", headers={"Cache-Control": "no-store"})


@app.get("/app/api/pacientes")
def list_patients(user: dict = Depends(auth.current_user)):
    return saas_store._request("GET", "patient_accounts", params={"select": "*", "client_id": f"eq.{user['id']}", "hidden_at": "is.null", "order": "created_at.desc"}) or []


@app.post("/app/api/pacientes")
def create_patient(payload: PatientRequest, user: dict = Depends(auth.current_user)):
    limit = int(user.get("patient_limit") if user.get("patient_limit") is not None else 10)
    visible = saas_store._request("GET", "patient_accounts", params={"select": "id", "client_id": f"eq.{user['id']}", "hidden_at": "is.null", "archived_at": "is.null"}) or []
    if limit >= 0 and len(visible) >= limit:
        raise HTTPException(409, f"Limite do plano atingido ({limit} pacientes). Solicite um ajuste ao administrador.")
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
def generate_patient_code(patient_id: str, payload: PatientCodeRequest, user: dict = Depends(auth.current_user)):
    patient = _owned_patient(patient_id, user["id"])
    if patient.get("archived_at") or not patient.get("active"): raise HTTPException(409, "Ative o paciente antes de gerar o código")
    return {"code": patient_auth.issue_code(patient_id, payload.expires_in_hours), "expires_in_hours": payload.expires_in_hours, "show_once": True}


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


@app.post("/app/api/pacientes/{patient_id}/ocultar")
def hide_patient(patient_id: str, user: dict = Depends(auth.current_user)):
    """Remove da visão profissional sem apagar prontuário, métricas ou documentos."""
    _owned_patient(patient_id, user["id"])
    now = datetime.now(timezone.utc).isoformat()
    patient_auth.revoke(patient_id)
    rows = saas_store._request("PATCH", "patient_accounts", params={"id": f"eq.{patient_id}", "client_id": f"eq.{user['id']}"}, payload={"active": False, "hidden_at": now, "updated_at": now}, prefer="return=representation") or []
    business_store.audit(user["id"], user["id"], "patient.hidden", "patient_account", patient_id, {})
    return rows[0] if rows else {"ok": True}


@app.get("/app/api/pacientes/{patient_id}/acompanhamento")
def patient_followup_data(patient_id: str, user: dict = Depends(auth.current_user)):
    patient = _owned_patient(patient_id, user["id"])
    records = saas_store._request("GET", "patient_records", params={"select": "*", "patient_id": f"eq.{patient_id}", "client_id": f"eq.{user['id']}", "order": "created_at.desc"}) or []
    checkins = saas_store._request("GET", "patient_checkins", params={"select": "*", "patient_id": f"eq.{patient_id}", "client_id": f"eq.{user['id']}", "order": "created_at.desc", "limit": "50"}) or []
    documents = saas_store._request("GET", "patient_documents", params={"select": "id,title,original_name,version,is_current,category,created_at", "patient_id": f"eq.{patient_id}", "client_id": f"eq.{user['id']}", "order": "created_at.desc"}) or []
    anthropometry = business_store.list_rows("anthropometric_assessments", user["id"], order="assessed_at.desc", extra={"patient_id": f"eq.{patient_id}"})
    meal_plans = business_store.list_rows("meal_plans", user["id"], order="created_at.desc", extra={"patient_id": f"eq.{patient_id}"})
    diary = business_store.list_rows("food_diary_entries", user["id"], order="consumed_at.desc", extra={"patient_id": f"eq.{patient_id}", "limit": "100"})
    appointments = business_store.list_rows("appointments", user["id"], order="starts_at.desc", extra={"patient_id": f"eq.{patient_id}"})
    transactions = business_store.list_rows("clinic_transactions", user["id"], order="created_at.desc", extra={"patient_id": f"eq.{patient_id}"})
    reminders = business_store.list_rows("clinic_reminders", user["id"], order="reminder_at.asc", extra={"patient_id": f"eq.{patient_id}"})
    alerts = _refresh_clinical_alerts(patient, checkins, anthropometry, user["id"])
    questionnaires = business_store.list_rows("patient_questionnaires", user["id"], order="created_at.desc", extra={"patient_id": f"eq.{patient_id}"})
    maternal_child = business_store.list_rows("maternal_child_records", user["id"], order="reference_date.desc", extra={"patient_id": f"eq.{patient_id}"})
    progress_photos = business_store.list_rows("patient_progress_photos", user["id"], order="captured_at.desc", extra={"patient_id": f"eq.{patient_id}"})
    return {"patient": patient, "records": records, "checkins": checkins, "documents": documents, "anthropometry": anthropometry, "meal_plans": meal_plans, "diary": diary, "appointments": appointments, "transactions": transactions, "reminders": reminders, "alerts": alerts, "questionnaires": questionnaires, "maternal_child": maternal_child, "progress_photos": progress_photos}


@app.post("/app/api/pacientes/{patient_id}/calculo-energetico")
def calculate_energy(patient_id: str, payload: EnergyCalculationRequest, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    targets = _energy_targets(payload)
    saas_store._request("PATCH", "patient_accounts", params={"id": f"eq.{patient_id}", "client_id": f"eq.{user['id']}"}, payload={"activity_factor": payload.activity_factor, "energy_goal": payload.goal, "macro_targets": targets, "updated_at": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")
    return targets


@app.patch("/app/api/pacientes/{patient_id}/anamnese")
def save_full_anamnesis(patient_id: str, payload: FullAnamnesisRequest, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    data = payload.model_dump(exclude={"lgpd_consent", "lgpd_consent_version"})
    update = {"full_anamnesis": data, "birth_date": payload.birth_date, "sex": payload.sex, "updated_at": datetime.now(timezone.utc).isoformat()}
    if payload.lgpd_consent:
        update.update({"lgpd_consent_at": datetime.now(timezone.utc).isoformat(), "lgpd_consent_version": payload.lgpd_consent_version})
    rows = saas_store._request("PATCH", "patient_accounts", params={"id": f"eq.{patient_id}", "client_id": f"eq.{user['id']}"}, payload=update, prefer="return=representation") or []
    return rows[0]


@app.get("/app/api/alimentos")
def search_foods(q: str = Query(default="", max_length=80), user: dict = Depends(auth.current_user)):
    needle = unicodedata.normalize("NFKD", q.lower()).encode("ascii", "ignore").decode().strip()
    if len(needle) < 2: return []
    found = []
    for food in _TACO_ROWS:
        name = unicodedata.normalize("NFKD", food["nome"].lower()).encode("ascii", "ignore").decode()
        if needle in name: found.append(food)
        if len(found) >= 25: break
    custom = business_store.list_rows("custom_foods", user["id"], order="name.asc", extra={"active": "eq.true", "name": f"ilike.*{q.strip()}*", "limit": "25"})
    for food in custom:
        found.append({"id": f"custom:{food['id']}", "nome": food["name"], "source": food.get("source"), **(food.get("nutrients") or {})})
    return found[:40]


def _visual_body_metrics(values: dict) -> dict:
    """Indicadores transparentes; não faz inferência a partir das fotografias."""
    weight = float(values.get("weight_kg") or 0)
    height_cm = float(values.get("height_cm") or 0)
    waist = float(values.get("waist_cm") or 0)
    hip = float(values.get("hip_cm") or 0)
    fat_pct = float(values.get("body_fat_percent") or 0)
    height_m = height_cm / 100 if height_cm else 0
    result: dict[str, float | int | str] = {}
    if weight and height_m:
        result["bmi"] = round(weight / height_m**2, 2)
    if waist and height_cm:
        result["waist_height_ratio"] = round(waist / height_cm, 3)
    if waist and hip:
        result["waist_hip_ratio"] = round(waist / hip, 3)
    if weight and fat_pct:
        fat_mass = weight * fat_pct / 100
        lean_mass = weight - fat_mass
        result.update({"fat_mass_kg": round(fat_mass, 2), "lean_mass_kg": round(lean_mass, 2)})
        if height_m:
            result.update({"fat_mass_index": round(fat_mass / height_m**2, 2), "lean_mass_index": round(lean_mass / height_m**2, 2)})
    if waist and weight and height_m:
        result["conicity_index"] = round((waist / 100) / (0.109 * math.sqrt(weight / height_m)), 3)
    if values.get("body_water_percent") is not None and weight:
        result["body_water_kg"] = round(weight * float(values["body_water_percent"]) / 100, 2)
    expected = ("weight_kg", "height_cm", "waist_cm", "hip_cm", "body_fat_percent", "evaluation_method")
    completed = sum(bool(values.get(key)) for key in expected) + int(bool(values.get("front_photo_id"))) + int(bool(values.get("side_photo_id")))
    result["assessment_completeness"] = round(completed / 8 * 100)
    result["method_notice"] = "Medidas informadas e validadas pelo nutricionista; fotos usadas somente como apoio visual."
    return result


def _assessment_photo(patient_id: str, photo_id: str | None, client_id: str) -> dict | None:
    if not photo_id:
        return None
    row = business_store.get_row("patient_progress_photos", photo_id, client_id)
    if not row or row.get("patient_id") != patient_id:
        raise HTTPException(400, "Uma das fotos selecionadas não pertence a este paciente")
    return row


@app.post("/app/api/pacientes/{patient_id}/avaliacoes")
def create_anthropometry(patient_id: str, payload: AnthropometryRequest, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    data = payload.model_dump(exclude_none=True)
    _assessment_photo(patient_id, data.get("front_photo_id"), user["id"])
    _assessment_photo(patient_id, data.get("side_photo_id"), user["id"])
    analysis = _visual_body_metrics(data)
    data["bmi"] = analysis.get("bmi")
    data["analysis_data"] = analysis
    data["assessed_at"] = data.get("assessed_at") or datetime.now(timezone.utc).date().isoformat()
    return business_store.create_row("anthropometric_assessments", user["id"], {"patient_id": patient_id, **data})


def _visual_analysis_pdf(assessment: dict, history: list[dict], patient: dict, owner: dict, photos: list[dict | None]) -> bytes:
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    buffer = io.BytesIO(); page_w, page_h = A4
    cfg = owner.get("ai_config") or {}; brand = HexColor(str(cfg.get("cor_principal") or "#2878ff")); navy = HexColor("#071526"); muted = HexColor("#60718a"); pale = HexColor("#edf4ff")
    c = canvas.Canvas(buffer, pagesize=A4); c.setTitle("Análise Corporal Visual NutriOS")
    def text(x, y, value, size=9, color=navy, bold=False):
        c.setFillColor(color); c.setFont("Helvetica-Bold" if bold else "Helvetica", size); c.drawString(x, y, str(value))
    def metric(x, y, label, value, width=42*mm):
        c.setFillColor(pale); c.roundRect(x, y, width, 18*mm, 3*mm, fill=1, stroke=0); text(x+4*mm,y+11*mm,label,7,muted); text(x+4*mm,y+4*mm,value,12,navy,True)
    c.setFillColor(navy); c.rect(0,page_h-39*mm,page_w,39*mm,fill=1,stroke=0); c.setFillColor(brand); c.rect(0,page_h-4*mm,page_w,4*mm,fill=1,stroke=0)
    text(16*mm,page_h-17*mm,"NUTRIOS CLÍNICA",9,white,True); text(16*mm,page_h-28*mm,"Análise Corporal Visual",21,white,True)
    text(16*mm,page_h-48*mm,f"Paciente: {patient.get('name') or 'Não informado'}",11,navy,True); text(16*mm,page_h-55*mm,f"Avaliação: {assessment.get('assessed_at')}  •  Método: {assessment.get('evaluation_method') or 'Não informado'}",8,muted)
    analysis = assessment.get("analysis_data") or {}
    items = [("Peso",f"{assessment.get('weight_kg') or '—'} kg"),("IMC",analysis.get("bmi") or "—"),("Cintura/altura",analysis.get("waist_height_ratio") or "—"),("Cintura/quadril",analysis.get("waist_hip_ratio") or "—"),("Massa magra",f"{analysis.get('lean_mass_kg','—')} kg"),("Massa gorda",f"{analysis.get('fat_mass_kg','—')} kg"),("Índice magro",analysis.get("lean_mass_index") or "—"),("Conicidade",analysis.get("conicity_index") or "—")]
    for index,(label,value) in enumerate(items): metric(16*mm+(index%4)*45*mm,page_h-80*mm-(index//4)*22*mm,label,value)
    text(16*mm,page_h-132*mm,"Registro fotográfico de apoio",13,navy,True); text(16*mm,page_h-139*mm,"Guias são referências visuais; não representam detecção automática nem reconstrução 3D.",7,muted)
    for index, photo in enumerate(photos):
        x=16*mm+index*89*mm; y=41*mm; w=82*mm; h=93*mm
        c.setFillColor(HexColor("#f3f7fc")); c.roundRect(x,y,w,h,3*mm,fill=1,stroke=0)
        if photo:
            try:
                raw=saas_store.download_private_asset("patient-documents",photo["storage_path"]); img=ImageReader(io.BytesIO(raw)); iw,ih=img.getSize(); scale=min((w-6*mm)/iw,(h-12*mm)/ih); dw,dh=iw*scale,ih*scale; ix=x+(w-dw)/2; iy=y+6*mm+(h-12*mm-dh)/2; c.drawImage(img,ix,iy,dw,dh,mask='auto')
                c.setStrokeColor(HexColor("#38bdf8")); c.setLineWidth(.6); c.line(x+w/2,y+7*mm,x+w/2,y+h-4*mm)
                for frac in (.28,.48,.68): c.line(x+8*mm,y+h*frac,x+w-8*mm,y+h*frac)
                for frac in (.28,.48,.68): c.setFillColor(HexColor("#ff7a45")); c.circle(x+w/2,y+h*frac,1.3*mm,fill=1,stroke=0)
            except Exception: text(x+19*mm,y+h/2,"Imagem indisponível",9,muted)
        else: text(x+23*mm,y+h/2,"Foto não vinculada",9,muted)
        text(x+3*mm,y+2.3*mm,"FRONTAL" if index==0 else "LATERAL",7,navy,True)
    text(16*mm,28*mm,"Composição informada",11,navy,True); fat=assessment.get("body_fat_percent")
    text(16*mm,21*mm,f"Gordura corporal: {fat if fat is not None else '—'}%  •  Água corporal: {assessment.get('body_water_percent') if assessment.get('body_water_percent') is not None else '—'}%",8,muted)
    text(16*mm,12*mm,"Documento de apoio. A interpretação e a conduta são responsabilidade do nutricionista.",7,muted)
    c.showPage(); c.setFillColor(navy); c.rect(0,page_h-31*mm,page_w,31*mm,fill=1,stroke=0); text(16*mm,page_h-19*mm,"Evolução antropométrica",20,white,True)
    def chart(y,key,label,unit):
        rows=[r for r in reversed(history) if r.get(key) is not None][-12:]; text(16*mm,y+44*mm,label,11,navy,True); c.setFillColor(HexColor("#f3f7fc")); c.roundRect(16*mm,y,178*mm,39*mm,3*mm,fill=1,stroke=0)
        if len(rows)<2: text(72*mm,y+18*mm,"São necessárias duas avaliações",8,muted); return
        vals=[float(r[key]) for r in rows]; lo,hi=min(vals),max(vals); span=hi-lo or 1; points=[]
        for i,v in enumerate(vals): points.append((22*mm+i*164*mm/(len(vals)-1),y+7*mm+(v-lo)*24*mm/span))
        c.setStrokeColor(brand); c.setLineWidth(2)
        for a,b in zip(points,points[1:]): c.line(a[0],a[1],b[0],b[1])
        for px,py in points: c.setFillColor(brand); c.circle(px,py,1.2*mm,fill=1,stroke=0)
        text(22*mm,y+32*mm,f"{vals[-1]:g} {unit}",8,navy,True)
    chart(page_h-86*mm,"weight_kg","Peso","kg"); chart(page_h-142*mm,"body_fat_percent","Gordura corporal","%"); chart(page_h-198*mm,"waist_cm","Cintura","cm")
    text(16*mm,39*mm,"Observações profissionais",11,navy,True); notes=str(assessment.get("notes") or "Nenhuma observação registrada.")[:700]
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words=notes.split(); lines=[]; current=""
    for word in words:
        test=(current+" "+word).strip()
        if stringWidth(test,"Helvetica",8)>175*mm: lines.append(current); current=word
        else: current=test
    lines.append(current)
    for i,line in enumerate(lines[:5]): text(16*mm,32*mm-i*5*mm,line,8,muted)
    text(16*mm,8*mm,"Análise Corporal Visual NutriOS • sem promessa de escaneamento 3D",7,muted); c.save(); return buffer.getvalue()


@app.get("/app/api/pacientes/{patient_id}/avaliacoes/{assessment_id}/relatorio.pdf")
def visual_body_report(patient_id: str, assessment_id: str, user: dict = Depends(auth.current_user)):
    patient = _owned_patient(patient_id, user["id"]); assessment = business_store.get_row("anthropometric_assessments", assessment_id, user["id"])
    if not assessment or assessment.get("patient_id") != patient_id: raise HTTPException(404, "Avaliação não encontrada")
    history = business_store.list_rows("anthropometric_assessments", user["id"], order="assessed_at.desc", extra={"patient_id": f"eq.{patient_id}", "limit": "24"})
    photos = [_assessment_photo(patient_id, assessment.get("front_photo_id"), user["id"]), _assessment_photo(patient_id, assessment.get("side_photo_id"), user["id"])]
    content = _visual_analysis_pdf(assessment, history, patient, user, photos)
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="analise-corporal-{patient_id[:8]}.pdf"', "Cache-Control": "private, no-store"})


@app.post("/app/api/pacientes/{patient_id}/planos")
def create_meal_plan(patient_id: str, payload: MealPlanRequest, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    custom_ids = {str(item.get("food_id") or "").replace("custom:", "") for meal in payload.content for item in list(meal.get("items") or []) if str(item.get("food_id") or "").startswith("custom:")}
    custom_foods = {}
    for food_id in custom_ids:
        row = business_store.get_row("custom_foods", food_id, user["id"])
        if row and row.get("active"): custom_foods[food_id] = row
    content, totals = _meal_plan_content(payload.content, custom_foods)
    if not content: raise HTTPException(400, "Adicione ao menos um alimento válido ao plano")
    return business_store.create_row("meal_plans", user["id"], {"patient_id": patient_id, **payload.model_dump(exclude={"content"}), "content": content, "totals": totals})


@app.patch("/app/api/pacientes/{patient_id}/planos/{plan_id}/aprovar")
def approve_meal_plan(patient_id: str, plan_id: str, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    row = business_store.get_row("meal_plans", plan_id, user["id"])
    if not row or row.get("patient_id") != patient_id: raise HTTPException(404, "Plano não encontrado")
    saas_store._request("PATCH", "meal_plans", params={"patient_id": f"eq.{patient_id}", "client_id": f"eq.{user['id']}", "status": "eq.approved"}, payload={"status": "archived", "updated_at": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")
    return business_store.update_row("meal_plans", plan_id, user["id"], {"status": "approved", "approved_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()})


@app.post("/app/api/pacientes/{patient_id}/planos/{plan_id}/duplicar")
def duplicate_meal_plan(patient_id: str, plan_id: str, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"]); row = business_store.get_row("meal_plans", plan_id, user["id"])
    if not row or row.get("patient_id") != patient_id: raise HTTPException(404, "Plano não encontrado")
    return business_store.create_row("meal_plans", user["id"], {"patient_id": patient_id, "title": f"Cópia de {row['title']}"[:160], "objective": row.get("objective"), "content": row.get("content") or [], "totals": row.get("totals") or {}, "professional_notes": row.get("professional_notes"), "patient_notes": row.get("patient_notes"), "signature_text": row.get("signature_text"), "status": "draft"})


@app.get("/app/api/modelos-planos")
def list_plan_templates(user: dict = Depends(auth.current_user)):
    return business_store.list_rows("meal_plans", user["id"], order="created_at.desc", extra={"is_template": "eq.true"})


def _meal_plan_pdf(plan: dict, patient: dict, owner: dict) -> bytes:
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    font_dir = Path(reportlab.__file__).resolve().parent / "fonts"
    pdfmetrics.registerFont(TTFont("Vera", font_dir / "Vera.ttf")); pdfmetrics.registerFont(TTFont("Vera-Bold", font_dir / "VeraBd.ttf")); pdfmetrics.registerFont(TTFont("Vera-Italic", font_dir / "VeraIt.ttf"))
    pdfmetrics.registerFontFamily("Vera", normal="Vera", bold="Vera-Bold", italic="Vera-Italic", boldItalic="Vera-Bold")
    buffer = io.BytesIO(); cfg = owner.get("ai_config") or {}; styles = getSampleStyleSheet()
    for style in styles.byName.values(): style.fontName = "Vera"
    brand = colors.HexColor(str(cfg.get("cor_principal") or "#2563eb"))
    title_style = ParagraphStyle("Title", parent=styles["Title"], fontName="Vera-Bold", textColor=brand, alignment=TA_CENTER, spaceAfter=8)
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=16*mm)
    story = [Paragraph(html.escape(str(cfg.get("nome") or owner.get("name") or "Nutricionista")), title_style), Paragraph(html.escape(str(cfg.get("especialidade") or "Nutrição")), ParagraphStyle("center", parent=styles["Normal"], alignment=TA_CENTER)), Spacer(1, 8), Paragraph(f"<b>Plano alimentar:</b> {html.escape(plan['title'])}", styles["Heading2"]), Paragraph(f"<b>Paciente:</b> {html.escape(patient['name'])}", styles["Normal"]), Paragraph(f"<b>Objetivo:</b> {html.escape(str(plan.get('objective') or 'Acompanhamento nutricional'))}", styles["Normal"]), Spacer(1, 12)]
    for meal in plan.get("content") or []:
        heading = html.escape(str(meal.get("name") or "Refeição")) + (f" - {html.escape(str(meal.get('time')))}" if meal.get("time") else "")
        story.append(Paragraph(heading, styles["Heading3"]))
        rows = [["Alimento", "Quantidade", "Substituições"]]
        for item in meal.get("items") or []: rows.append([str(item.get("name") or ""), f"{item.get('grams') or 0:g} g", ", ".join(item.get("substitutions") or []) or "-"])
        table = Table(rows, colWidths=[78*mm, 28*mm, 54*mm], repeatRows=1)
        table.setStyle(TableStyle([("FONTNAME",(0,0),(-1,-1),"Vera"),("FONTNAME",(0,0),(-1,0),"Vera-Bold"),("BACKGROUND",(0,0),(-1,0),brand),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#ccd5e3")),("VALIGN",(0,0),(-1,-1),"TOP"),("FONTSIZE",(0,0),(-1,-1),8),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f3f6fa")])]))
        story.extend([table, Spacer(1, 10)])
    totals = plan.get("totals") or {}; story.append(Paragraph(f"<b>Totais aproximados:</b> {totals.get('kcal',0)} kcal | Proteínas {totals.get('proteina_g',0)} g | Carboidratos {totals.get('carboidrato_g',0)} g | Gorduras {totals.get('lipideos_g',0)} g", styles["Normal"]))
    if plan.get("patient_notes"): story.extend([Spacer(1,8),Paragraph("<b>Orientações:</b>",styles["Heading3"]),Paragraph(html.escape(str(plan["patient_notes"])).replace("\n","<br/>"),styles["Normal"])])
    signature = plan.get("signature_text") or f"{cfg.get('nome') or owner.get('name')} - CRN {cfg.get('crn') or 'não informado'}"
    story.extend([Spacer(1,20),Paragraph(html.escape(str(signature)),ParagraphStyle("sig",parent=styles["Normal"],alignment=TA_CENTER)),Spacer(1,8),Paragraph("Documento de apoio ao acompanhamento nutricional. Alterações devem ser avaliadas pelo nutricionista responsável.",ParagraphStyle("foot",parent=styles["Normal"],fontSize=7,textColor=colors.grey,alignment=TA_CENTER))])
    doc.build(story); return buffer.getvalue()


@app.get("/app/api/pacientes/{patient_id}/planos/{plan_id}/pdf")
def professional_plan_pdf(patient_id: str, plan_id: str, user: dict = Depends(auth.current_user)):
    patient = _owned_patient(patient_id, user["id"]); plan = business_store.get_row("meal_plans", plan_id, user["id"])
    if not plan or plan.get("patient_id") != patient_id: raise HTTPException(404, "Plano não encontrado")
    content = _meal_plan_pdf(plan, patient, user)
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="plano-{patient_id[:8]}.pdf"', "Cache-Control": "private, no-store"})


@app.get("/paciente/api/plano/pdf")
def patient_plan_pdf(patient: dict = Depends(patient_auth.current_patient)):
    rows = saas_store._request("GET", "meal_plans", params={"select": "*", "patient_id": f"eq.{patient['id']}", "status": "eq.approved", "order": "approved_at.desc", "limit": "1"}) or []
    if not rows: raise HTTPException(404, "Plano ainda não publicado")
    owner = saas_store.get_user(patient["client_id"]) or {}; content = _meal_plan_pdf(rows[0], patient, owner)
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="meu-plano-alimentar.pdf"', "Cache-Control": "private, no-store"})


@app.patch("/app/api/pacientes/{patient_id}/diario/{entry_id}")
def review_diary(patient_id: str, entry_id: str, payload: DiaryFeedbackRequest, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    row = business_store.get_row("food_diary_entries", entry_id, user["id"])
    if not row or row.get("patient_id") != patient_id: raise HTTPException(404, "Registro não encontrado")
    return business_store.update_row("food_diary_entries", entry_id, user["id"], {"professional_feedback": payload.professional_feedback, "reviewed_at": datetime.now(timezone.utc).isoformat()})


@app.post("/app/api/pacientes/{patient_id}/financeiro")
def create_patient_transaction(patient_id: str, payload: TransactionRequest, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    data = payload.model_dump(); data["patient_id"] = patient_id
    if data["status"] == "paid": data["paid_at"] = datetime.now(timezone.utc).isoformat()
    return business_store.create_row("clinic_transactions", user["id"], data)


@app.post("/app/api/pacientes/{patient_id}/consultas")
def create_patient_appointment(patient_id: str, payload: PatientAppointmentRequest, user: dict = Depends(auth.current_user)):
    patient = _owned_patient(patient_id, user["id"])
    if payload.end_at and payload.end_at <= payload.starts_at:
        raise HTTPException(400, "O horário final deve ser posterior ao início")
    data = {"patient_id": patient_id, "session_id": f"manual-{secrets.token_hex(12)}", "patient_name": patient.get("name") or "Paciente", "patient_phone": patient.get("phone") or "não informado", "starts_at": payload.starts_at.isoformat(), "status": "scheduled", "notes": payload.notes}
    if payload.end_at:
        data["end_at"] = payload.end_at.isoformat()
    row = business_store.create_row("appointments", user["id"], data)
    business_store.audit(user["id"], user["id"], "appointment.created", "appointment", row.get("id", ""), {"patient_id": patient_id})
    return row


@app.get("/app/api/financeiro")
def clinic_finance(user: dict = Depends(auth.current_user)):
    rows = business_store.list_rows("clinic_transactions", user["id"], order="created_at.desc")
    paid = [r for r in rows if r.get("status") == "paid"]
    income = sum(float(r.get("amount") or 0) for r in paid if r.get("kind") == "income")
    expense = sum(float(r.get("amount") or 0) for r in paid if r.get("kind") == "expense")
    return {"rows": rows, "income": round(income,2), "expense": round(expense,2), "balance": round(income-expense,2)}


@app.post("/app/api/pacientes/{patient_id}/lembretes")
def create_reminder(patient_id: str, payload: ReminderRequest, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    data = payload.model_dump(); data["patient_id"] = patient_id
    return business_store.create_row("clinic_reminders", user["id"], data)


@app.patch("/app/api/lembretes/{reminder_id}/concluir")
def complete_reminder(reminder_id: str, user: dict = Depends(auth.current_user)):
    if not business_store.get_row("clinic_reminders", reminder_id, user["id"]): raise HTTPException(404, "Lembrete não encontrado")
    return business_store.update_row("clinic_reminders", reminder_id, user["id"], {"completed_at": datetime.now(timezone.utc).isoformat()})


@app.post("/app/api/pacientes/{patient_id}/prontuario")
def save_patient_record(patient_id: str, payload: PatientRecordRequest, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    rows = saas_store._request("POST", "patient_records", payload={"patient_id": patient_id, "client_id": user["id"], **payload.model_dump()}, prefer="return=representation") or []
    return rows[0]


@app.post("/app/api/pacientes/{patient_id}/documentos")
async def upload_patient_document(patient_id: str, title: str = Form(..., min_length=2, max_length=160), category: str = Form(default="diet", max_length=30), file: UploadFile = File(...), user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    if file.content_type != "application/pdf" or not str(file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Envie somente arquivo PDF")
    content = await file.read(10_000_001)
    if len(content) > 10_000_000: raise HTTPException(413, "O PDF deve ter no máximo 10 MB")
    if not content.startswith(b"%PDF-"): raise HTTPException(400, "O arquivo não é um PDF válido")
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", Path(file.filename or "dieta.pdf").name)[:120]
    object_path = f"{user['id']}/{patient_id}/{secrets.token_hex(16)}-{safe_name}"
    saas_store.upload_private_asset("patient-documents", object_path, content, "application/pdf")
    previous = saas_store._request("GET", "patient_documents", params={"select": "version", "patient_id": f"eq.{patient_id}", "order": "version.desc", "limit": "1"}) or []
    version = int(previous[0]["version"]) + 1 if previous else 1
    saas_store._request("PATCH", "patient_documents", params={"patient_id": f"eq.{patient_id}", "is_current": "eq.true"}, payload={"is_current": False}, prefer="return=minimal")
    if category not in {"diet", "exam", "report", "prescription", "other"}: category = "other"
    rows = saas_store._request("POST", "patient_documents", payload={"patient_id": patient_id, "client_id": user["id"], "title": title.strip(), "category": category, "original_name": safe_name, "storage_path": object_path, "version": version, "is_current": True}, prefer="return=representation") or []
    return {"ok": True, "document": rows[0]}


def _patient_document(document_id: str) -> dict:
    rows = saas_store._request("GET", "patient_documents", params={"select": "*", "id": f"eq.{document_id}", "limit": "1"}) or []
    if not rows: raise HTTPException(404, "Documento não encontrado")
    return rows[0]


@app.get("/app/api/documentos/{document_id}/baixar")
def professional_download_document(document_id: str, user: dict = Depends(auth.current_user)):
    doc = _patient_document(document_id)
    if doc["client_id"] != user["id"]: raise HTTPException(403, "Acesso negado")
    content = saas_store.download_private_asset("patient-documents", doc["storage_path"])
    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", doc.get("original_name") or "dieta.pdf")
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "private, no-store"})


@app.get("/paciente/login")
def patient_login_page():
    return FileResponse(STATIC_DIR / "patient-login.html", headers={"Cache-Control": "no-store"})


@app.post("/paciente/auth/login")
@limiter.limit("5/minute")
def patient_login(request: Request, payload: PatientLoginRequest, response: Response):
    try:
        if payload.code:
            patient = patient_auth.authenticate(payload.code)
            method = "code"
        elif payload.identifier and payload.password:
            patient = patient_auth.authenticate_password(payload.identifier, payload.password)
            method = "password"
        else:
            raise HTTPException(400, "Informe o código ou suas credenciais")
    except RuntimeError:
        raise HTTPException(503, "Serviço de autenticação temporariamente indisponível")
    if not patient: raise HTTPException(401, "Acesso inválido, expirado ou indisponível")
    patient_auth.create_session(patient, response)
    redirect = "/paciente/primeiro-acesso" if method == "code" and not patient.get("password_hash") else "/paciente"
    return {"ok": True, "redirect": redirect}


@app.get("/paciente/primeiro-acesso")
def patient_first_access_page(patient: dict = Depends(patient_auth.current_patient)):
    return FileResponse(STATIC_DIR / "patient-first-access.html", headers={"Cache-Control": "no-store"})


@app.post("/paciente/auth/credenciais")
@limiter.limit("5/minute")
def patient_create_credentials(request: Request, payload: PatientCredentialRequest, patient: dict = Depends(patient_auth.current_patient)):
    try:
        updated = patient_auth.set_credentials(patient, payload.identifier, payload.password)
    except ValueError as error:
        raise HTTPException(400, str(error))
    return {"ok": True, "identifier": updated.get("login_identifier"), "redirect": "/paciente"}


@app.post("/paciente/auth/logout")
def patient_logout(response: Response):
    patient_auth.logout(response); return {"ok": True}


@app.get("/paciente")
def patient_portal(patient: dict = Depends(patient_auth.current_patient)):
    return FileResponse(STATIC_DIR / "patient-portal.html", headers={"Cache-Control": "no-store"})


@app.get("/paciente/api/me")
def patient_me(patient: dict = Depends(patient_auth.current_patient)):
    client = saas_store.get_user(patient["client_id"]); config = (client or {}).get("ai_config") or {}
    return {"name": patient["name"], "plan_name": patient.get("plan_name"), "expires_at": patient["access_expires_at"], "messages_used": patient.get("messages_used") or 0, "message_limit": patient.get("message_limit") or 200, "professional_name": config.get("nome") or (client or {}).get("name"), "assistant_name": config.get("identidade_ia") or "NutriOS", "logo_url": config.get("logo_url"), "color": config.get("cor_principal") or "#4f7cff"}


@app.get("/paciente/api/documentos")
def patient_documents(patient: dict = Depends(patient_auth.current_patient)):
    return saas_store._request("GET", "patient_documents", params={"select": "id,title,original_name,version,is_current,created_at", "patient_id": f"eq.{patient['id']}", "order": "created_at.desc"}) or []


@app.get("/paciente/api/plano")
def patient_meal_plan(patient: dict = Depends(patient_auth.current_patient)):
    rows = saas_store._request("GET", "meal_plans", params={"select": "id,title,objective,content,totals,patient_notes,approved_at", "patient_id": f"eq.{patient['id']}", "status": "eq.approved", "order": "approved_at.desc", "limit": "1"}) or []
    return rows[0] if rows else None


@app.get("/paciente/api/treino")
def patient_workout(patient: dict = Depends(patient_auth.current_patient)):
    owner = saas_store.get_user(patient["client_id"])
    if not ((owner or {}).get("ai_config") or {}).get("training_enabled"):
        return {"enabled": False, "plan": None, "logs": []}
    rows = saas_store._request("GET", "workout_plans", params={"select": "*", "patient_id": f"eq.{patient['id']}", "client_id": f"eq.{patient['client_id']}", "status": "eq.published", "order": "published_at.desc", "limit": "1"}) or []
    logs = saas_store._request("GET", "workout_logs", params={"select": "id,completed_at,perceived_exertion,readiness,notes", "patient_id": f"eq.{patient['id']}", "order": "completed_at.desc", "limit": "10"}) or []
    return {"enabled": True, "plan": rows[0] if rows else None, "logs": logs}


@app.post("/paciente/api/treino/{plan_id}/concluir")
def complete_patient_workout(plan_id: str, payload: WorkoutLogRequest, patient: dict = Depends(patient_auth.current_patient)):
    rows = saas_store._request("GET", "workout_plans", params={"select": "id", "id": f"eq.{plan_id}", "patient_id": f"eq.{patient['id']}", "client_id": f"eq.{patient['client_id']}", "status": "eq.published", "limit": "1"}) or []
    if not rows: raise HTTPException(404, "Treino não encontrado")
    data = {"patient_id": patient["id"], "workout_plan_id": plan_id, "readiness": {"sleep": payload.sleep, "energy": payload.energy, "pain": payload.pain}, "exercise_results": payload.exercise_results, "perceived_exertion": payload.perceived_exertion, "notes": payload.notes}
    return business_store.create_row("workout_logs", patient["client_id"], data)


@app.get("/paciente/api/diario")
def patient_food_diary(patient: dict = Depends(patient_auth.current_patient)):
    return saas_store._request("GET", "food_diary_entries", params={"select": "*", "patient_id": f"eq.{patient['id']}", "order": "consumed_at.desc", "limit": "100"}) or []


@app.post("/paciente/api/diario")
def create_food_diary(payload: FoodDiaryRequest, patient: dict = Depends(patient_auth.current_patient)):
    rows = saas_store._request("POST", "food_diary_entries", payload={"patient_id": patient["id"], "client_id": patient["client_id"], **payload.model_dump(exclude_none=True, mode="json")}, prefer="return=representation") or []
    return rows[0]


@app.get("/paciente/api/documentos/{document_id}/baixar")
def patient_download_document(document_id: str, patient: dict = Depends(patient_auth.current_patient)):
    doc = _patient_document(document_id)
    if doc["patient_id"] != patient["id"]: raise HTTPException(403, "Acesso negado")
    content = saas_store.download_private_asset("patient-documents", doc["storage_path"])
    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", doc.get("original_name") or "dieta.pdf")
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "private, no-store"})


@app.get("/paciente/api/checkins")
def patient_checkins(patient: dict = Depends(patient_auth.current_patient)):
    return saas_store._request("GET", "patient_checkins", params={"select": "*", "patient_id": f"eq.{patient['id']}", "order": "created_at.desc", "limit": "20"}) or []


@app.post("/paciente/api/checkins")
def create_patient_checkin(payload: PatientCheckinRequest, patient: dict = Depends(patient_auth.current_patient)):
    rows = saas_store._request("POST", "patient_checkins", payload={"patient_id": patient["id"], "client_id": patient["client_id"], **payload.model_dump()}, prefer="return=representation") or []
    return rows[0]


@app.get("/app/api/configuracoes")
def own_config_data(request: Request, user: dict = Depends(auth.current_user)):
    public_url = f"{str(request.base_url).rstrip('/')}/n/{user.get('public_slug')}" if user.get("public_slug") else None
    config = dict(user.get("ai_config") or {})
    config["public_url"] = public_url
    return {"name": user["name"], "identifier": user["identifier"], "plan": user.get("plan"), "expires_at": user.get("expires_at"), "public_slug": user.get("public_slug"), "public_url": public_url, "ai_config": config}


@app.patch("/app/api/configuracoes")
def update_own_config(payload: dict, user: dict = Depends(auth.current_user)):
    current = user.get("ai_config") or {}
    allowed = {k: v for k, v in payload.items() if k in {"nome", "especialidade", "whatsapp", "link_consulta", "identidade_ia", "mensagem_inicial", "cta", "horario", "logo_url", "prompt", "free_message_limit", "crn", "cor_principal", "instagram", "acoes_rapidas", "anamnesis_url", "whatsapp_message_template", "payment_wait_message", "notification_email", "training_enabled"}}
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
    is_master = payload.client_id == "master"
    if is_master and not payment_url.startswith("https://") and pagamento.PAGAMENTO_ATIVO:
        payment_url = pagamento.criar_link_pagamento(payload.session_id)
    if not payment_url.startswith("https://"):
        raise HTTPException(409, "O profissional ainda não configurou o link de pagamento.")
    owner_id = None if is_master else client["id"]
    lead = leads_store.buscar_lead(payload.session_id, owner_id)
    if not lead:
        leads_store.salvar_lead(payload.session_id, [], True, owner_id, {"lead_status": "quente", "lead_score": 70, "lead_summary": "Solicitou atendimento", "message_count": 0})
    updated = leads_store.atualizar_lead(payload.session_id, {"lead_name": payload.name.strip(), "lead_phone": normalizar_whatsapp(payload.phone), "contact_consent_at": datetime.now(timezone.utc).isoformat(), "workflow_status": "awaiting_payment", "lead_status": "quente", "lead_source": (payload.lead_source or "direto").strip().lower()[:80]}, owner_id)
    if not updated:
        raise HTTPException(503, "Não foi possível registrar seus dados.")
    message = config.get("payment_wait_message") or "Após realizar o pagamento, clique em ‘Já realizei o pagamento’. A clínica fará a conferência e entrará em contato pelo WhatsApp informado em até 24 horas."
    return {"ok": True, "payment_url": payment_url, "message": message, "workflow_status": "awaiting_payment"}


@app.post("/leads/claim-paid")
@limiter.limit("5/minute")
def claim_paid(request: Request, payload: LeadClaimPaidRequest, background_tasks: BackgroundTasks):
    client = resolver_cliente_publico(payload.client_slug, payload.client_id)
    owner_id = None if payload.client_id == "master" else client["id"]
    lead = leads_store.buscar_lead(payload.session_id, owner_id)
    if not lead or not lead.get("contact_consent_at"):
        raise HTTPException(400, "Cadastre seus dados antes de informar o pagamento.")
    # O clique é apenas um aviso. A liberação imediata só acontece depois
    # de consultar a situação real pela referência no Mercado Pago.
    if payload.client_id == "master" and pagamento.PAGAMENTO_ATIVO:
        matches = pagamento.buscar_pagamentos_por_referencia(payload.session_id)
        approved = next((item for item in matches if item.get("status") == "approved"), None)
        if approved:
            leads_store.marcar_pago(payload.session_id, str(approved.get("id") or ""), approved.get("transaction_amount"))
            verified_lead = leads_store.buscar_lead(payload.session_id, owner_id)
            return {"ok": True, **payment_next_steps(verified_lead, client, str(request.base_url))}
    updated = leads_store.atualizar_lead(payload.session_id, {"workflow_status": "awaiting_verification", "claimed_paid_at": datetime.now(timezone.utc).isoformat()}, owner_id)
    if not updated:
        raise HTTPException(503, "Não foi possível registrar a solicitação.")
    config = client.get("ai_config") or {}
    notify_email = str(config.get("notification_email") or client.get("identifier") or "").strip()
    if "@" in notify_email:
        background_tasks.add_task(emailer.send_notification, notify_email, "Novo pagamento aguardando conferência — NutriOS", f"{lead.get('lead_name') or 'Um paciente'} informou que realizou o pagamento.\nWhatsApp: {lead.get('lead_phone') or 'não informado'}\nAcesse seu painel para conferir e dar continuidade.")
    return {"ok": True, "message": "Recebemos seu aviso. A clínica verificará o pagamento e entrará em contato pelo WhatsApp informado em até 24 horas.", "workflow_status": "awaiting_verification"}


@app.get("/n/{public_slug}/anamnese")
def public_anamnesis_page(public_slug: str, session_id: str = Query(default="")):
    resolver_cliente_publico(public_slug, None)
    return FileResponse(STATIC_DIR / "public-anamnesis.html")


@app.get("/assistente/anamnese")
def master_anamnesis_page(session_id: str = Query(default="")):
    if not master_chat_user():
        raise HTTPException(404, "Assistente indisponível")
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


@app.post("/public/master/anamnese")
@limiter.limit("5/minute")
def submit_master_anamnesis(request: Request, payload: AnamnesisRequest):
    owner = master_chat_user()
    if not owner:
        raise HTTPException(404, "Assistente indisponível")
    lead = leads_store.buscar_lead(payload.session_id)
    if not lead or lead.get("client_id"):
        raise HTTPException(404, "Atendimento não encontrado")
    if not lead.get("pago"):
        raise HTTPException(403, "Anamnese liberada após a confirmação do pagamento")
    clean = {str(k)[:60]: str(v)[:1000] for k, v in payload.answers.items() if str(v).strip()}
    row = business_store.upsert_anamnesis(owner["id"], payload.session_id, {"answers": clean, "submitted_at": datetime.now(timezone.utc).isoformat()})
    leads_store.atualizar_lead(payload.session_id, {"workflow_status": "anamnesis_sent", "anamnesis_sent_at": datetime.now(timezone.utc).isoformat()})
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
        background_tasks.add_task(emailer.send_notification, notify_email, "Nova consulta agendada — NutriOS", f"Paciente: {payload.patient_name}\nWhatsApp: {payload.patient_phone}\nHorário: {payload.starts_at.isoformat()}")
    return {"ok": True, "appointment": row}


@app.get("/admin")
def admin_page(user: dict = Depends(auth.require_admin)):
    return FileResponse(STATIC_DIR / "admin-v2.html", headers={"Cache-Control": "no-store"})


@app.get("/admin/clinica")
def admin_clinical_page(user: dict = Depends(auth.require_admin)):
    return FileResponse(STATIC_DIR / "admin-clinical.html", headers={"Cache-Control": "no-store"})


@app.get("/admin/leads")
def admin_leads_page(user: dict = Depends(auth.require_admin)):
    return FileResponse(STATIC_DIR / "admin-leads.html", headers={"Cache-Control": "no-store"})


@app.get("/admin/api/leads")
def admin_all_leads(admin: dict = Depends(auth.require_admin)):
    """Todas as conversas para o mestre, identificadas por proprietário."""
    leads = leads_store.listar_leads(limite=2000)
    owners = {str(user.get("id")): user for user in saas_store.list_users()}
    result = []
    mercado_pago_lookups = 0
    for row in leads:
        owner = owners.get(str(row.get("client_id"))) if row.get("client_id") else None
        lead_name = row.get("lead_name")
        lead_phone = row.get("lead_phone")
        payer_email = None
        # Recupera a identidade de pagamentos antigos que foram confirmados
        # antes de nome/WhatsApp passarem a ser salvos no lead.
        if row.get("pago") and row.get("payment_id") and (not lead_name or not lead_phone) and mercado_pago_lookups < 50:
            payment_data = pagamento.consultar_pagamento(str(row["payment_id"]))
            mercado_pago_lookups += 1
            if payment_data:
                payer = payment_data.get("payer") or {}
                payer_email = payer.get("email")
                payer_name = " ".join(filter(None, [payer.get("first_name"), payer.get("last_name")])).strip()
                lead_name = lead_name or payer_name or payer_email
                phone = payer.get("phone") or {}
                lead_phone = lead_phone or "".join(filter(None, [str(phone.get("area_code") or ""), str(phone.get("number") or "")])) or None
        result.append({
            **row,
            "lead_name": lead_name,
            "lead_phone": lead_phone,
            "payer_email": payer_email,
            "owner_name": owner.get("name") if owner else "Minha experiência pública",
            "owner_identifier": owner.get("identifier") if owner else "admin mestre",
            "owner_type": "nutritionist" if owner else "master",
        })
    result.sort(key=lambda item: str(item.get("atualizado_em") or item.get("criado_em") or ""), reverse=True)
    return result


@app.get("/admin/testes")
def admin_test_lab(user: dict = Depends(auth.require_admin)):
    return FileResponse(STATIC_DIR / "admin-testing.html", headers={"Cache-Control": "no-store"})


@app.get("/admin/testes/{user_id}/chat")
def admin_test_chat(user_id: str, admin: dict = Depends(auth.require_admin)):
    if user_id == "master":
        return HTMLResponse(
            (STATIC_DIR / "index.html").read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )
    client = saas_store.get_user(user_id)
    if not client or client.get("role") != "client":
        raise HTTPException(404, "Nutricionista não encontrado")
    return HTMLResponse(
        (STATIC_DIR / "index.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.post("/admin/api/clientes/{user_id}/link-publico")
def admin_generate_public_link(request: Request, user_id: str, admin: dict = Depends(auth.require_admin)):
    """Gera uma URL pública persistente sem compartilhar a sessão do ADMIN."""
    client = saas_store.get_user(user_id)
    if not client or client.get("role") != "client":
        raise HTTPException(404, "Nutricionista não encontrado")
    slug = client.get("public_slug")
    if not slug:
        slug = criar_slug_publico(client.get("name") or "nutricionista")
        saas_store.update_user(user_id, {"public_slug": slug})
    public_url = f"{str(request.base_url).rstrip('/')}/n/{slug}"
    business_store.audit(admin["id"], user_id, "client.public_link_generated", "saas_user", user_id, {})
    return {"ok": True, "public_url": public_url}


@app.post("/admin/api/chatbot-mestre/link-publico")
def admin_generate_master_public_link(request: Request, admin: dict = Depends(auth.require_admin)):
    """Retorna apenas o endereço público; nunca inclui cookie ou token mestre."""
    return {"ok": True, "public_url": f"{str(request.base_url).rstrip('/')}/assistente"}


@app.get("/admin/api/chatbot-mestre/teste")
def admin_master_chat_data(request: Request, admin: dict = Depends(auth.require_admin)):
    config = dict(admin.get("ai_config") or {})
    base = str(request.base_url).rstrip("/")
    today = datetime.now(timezone.utc).date().isoformat()
    leads = leads_store.listar_leads(limite=1000, only_unassigned=True)
    today_sessions = {str(row.get("session_id")) for row in leads if str(row.get("criado_em") or "").startswith(today)}
    return {
        "id": "master", "name": admin.get("name"), "identifier": admin.get("identifier"),
        "ai_config": config, "public_url": f"{base}/assistente",
        "test_chat_url": f"{base}/static/index.html?admin_test=mestre",
        "whatsapp_url": f"https://wa.me/{normalizar_whatsapp(str(config.get('whatsapp') or ''))}" if config.get("whatsapp") else None,
        "payment_url": config.get("link_consulta") if str(config.get("link_consulta") or "").startswith("https://") else None,
        "mercado_pago_api": bool(pagamento.PAGAMENTO_ATIVO),
        "visitors_today": len(today_sessions),
    }


@app.patch("/admin/api/chatbot-mestre/teste")
def admin_update_master_chat(payload: dict, admin: dict = Depends(auth.require_admin)):
    allowed_keys = {"nome", "especialidade", "whatsapp", "link_consulta", "identidade_ia", "mensagem_inicial", "prompt", "free_message_limit", "crn", "cor_principal", "acoes_rapidas", "daily_visitor_limit", "demo_duration_minutes", "public_chat_enabled"}
    updates = {k: v for k, v in payload.items() if k in allowed_keys}
    if "whatsapp" in updates and updates["whatsapp"]:
        updates["whatsapp"] = normalizar_whatsapp(str(updates["whatsapp"]))
    if "link_consulta" in updates and updates["link_consulta"] and not str(updates["link_consulta"]).startswith("https://"):
        raise HTTPException(400, "O link deve começar com https://")
    for key, default, maximum in (("free_message_limit", 8, 100), ("daily_visitor_limit", 30, 10000), ("demo_duration_minutes", 30, 1440)):
        if key in updates:
            updates[key] = max(1, min(maximum, int(updates[key] or default)))
    if "public_chat_enabled" in updates:
        updates["public_chat_enabled"] = bool(updates["public_chat_enabled"])
    current = dict(admin.get("ai_config") or {}); current.update(updates)
    saas_store.update_user(admin["id"], {"ai_config": current})
    business_store.audit(admin["id"], admin["id"], "master_chat.updated", "saas_user", admin["id"], {"fields": list(updates)})
    return {"ok": True, "ai_config": current}


@app.get("/admin/api/clientes/{user_id}/teste")
def admin_test_client_data(request: Request, user_id: str, admin: dict = Depends(auth.require_admin)):
    client = saas_store.get_user(user_id)
    if not client or client.get("role") != "client":
        raise HTTPException(404, "Nutricionista não encontrado")
    config = dict(client.get("ai_config") or {})
    base = str(request.base_url).rstrip("/")
    slug = client.get("public_slug")
    return {
        "id": client["id"], "name": client["name"], "identifier": client["identifier"],
        "active": client.get("active"), "public_slug": slug, "ai_config": config,
        "public_url": f"{base}/n/{slug}" if slug else None,
        "test_chat_url": f"{base}/static/index.html?admin_test={client['id']}",
        "whatsapp_url": f"https://wa.me/{normalizar_whatsapp(str(config.get('whatsapp') or ''))}" if config.get("whatsapp") else None,
        "payment_url": config.get("link_consulta") if str(config.get("link_consulta") or "").startswith("https://") else None,
    }


@app.patch("/admin/api/clientes/{user_id}/teste")
def admin_update_test_client(user_id: str, payload: dict, admin: dict = Depends(auth.require_admin)):
    client = saas_store.get_user(user_id)
    if not client or client.get("role") != "client":
        raise HTTPException(404, "Nutricionista não encontrado")
    allowed_keys = {"nome", "especialidade", "whatsapp", "link_consulta", "identidade_ia", "mensagem_inicial", "cta", "horario", "prompt", "free_message_limit", "crn", "cor_principal", "instagram", "acoes_rapidas", "payment_wait_message"}
    updates = {k: v for k, v in payload.items() if k in allowed_keys}
    if "whatsapp" in updates and updates["whatsapp"]:
        updates["whatsapp"] = normalizar_whatsapp(str(updates["whatsapp"]))
    if "link_consulta" in updates and updates["link_consulta"] and not str(updates["link_consulta"]).startswith("https://"):
        raise HTTPException(400, "O link de pagamento deve começar com https://")
    if "free_message_limit" in updates:
        updates["free_message_limit"] = max(1, min(50, int(updates["free_message_limit"] or 8)))
    current = dict(client.get("ai_config") or {}); current.update(updates)
    saas_store.update_user(user_id, {"ai_config": current})
    business_store.audit(admin["id"], user_id, "client.test_config_updated", "saas_user", user_id, {"fields": list(updates)})
    return {"ok": True, "ai_config": current}


@app.get("/admin/api/dashboard")
def admin_dashboard(user: dict = Depends(auth.require_admin)):
    all_clients = [u for u in saas_store.list_users() if u["role"] == "client"]
    patient_rows = saas_store._request("GET", "patient_accounts", params={"select": "client_id,active,archived_at,hidden_at,access_expires_at"}) or []
    # Mantém o painel mestre disponível durante uma implantação incremental,
    # inclusive se a migration clínica ainda não tiver sido executada.
    try:
        clinical_alert_rows = saas_store._request("GET", "clinical_alerts", params={"select": "id,client_id,patient_id,severity,title,created_at,resolved_at", "resolved_at": "is.null", "order": "created_at.desc", "limit": "200"}) or []
    except Exception:
        clinical_alert_rows = []
    try:
        clinical_plan_rows = saas_store._request("GET", "meal_plans", params={"select": "id,client_id,patient_id,status,created_at", "order": "created_at.desc", "limit": "500"}) or []
    except Exception:
        clinical_plan_rows = []
    try:
        questionnaire_rows = saas_store._request("GET", "patient_questionnaires", params={"select": "id,client_id,status", "limit": "1000"}) or []
        progress_photo_rows = saas_store._request("GET", "patient_progress_photos", params={"select": "id,client_id", "limit": "1000"}) or []
        maternal_rows = saas_store._request("GET", "maternal_child_records", params={"select": "id,client_id", "limit": "1000"}) or []
    except Exception:
        questionnaire_rows, progress_photo_rows, maternal_rows = [], [], []
    patient_counts: dict[str, int] = {}
    for patient in patient_rows:
        if patient.get("hidden_at") or patient.get("archived_at"):
            continue
        patient_counts[patient["client_id"]] = patient_counts.get(patient["client_id"], 0) + 1
    for client in all_clients:
        client["patients_used"] = patient_counts.get(client["id"], 0)
    clients = [u for u in all_clients if not u.get("archived_at")]
    archived_clients = [u for u in all_clients if u.get("archived_at")]
    leads = leads_store.listar_leads(limite=1000)
    now = datetime.now(timezone.utc)
    master_config = dict(user.get("ai_config") or {})

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
        "master_visitors_today": len({str(row.get("session_id")) for row in leads if not row.get("client_id") and str(row.get("criado_em") or "").startswith(now.date().isoformat())}),
        "master_daily_limit": max(1, int(master_config.get("daily_visitor_limit") or 30)),
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
        "clinical": {
            "patients_total": len(patient_rows),
            "patients_active": sum(bool(row.get("active")) and not row.get("archived_at") and not row.get("hidden_at") for row in patient_rows),
            "alerts_open": len(clinical_alert_rows),
            "alerts_high": sum(row.get("severity") == "high" for row in clinical_alert_rows),
            "plans_total": len(clinical_plan_rows),
            "plans_published": sum(row.get("status") == "approved" for row in clinical_plan_rows),
            "questionnaires": len(questionnaire_rows),
            "questionnaires_pending": sum(row.get("status") == "assigned" for row in questionnaire_rows),
            "progress_photos": len(progress_photo_rows),
            "maternal_records": len(maternal_rows),
            "by_nutritionist": [{"id": client["id"], "name": client["name"], "patients": patient_counts.get(client["id"], 0), "alerts": sum(a.get("client_id") == client["id"] for a in clinical_alert_rows), "plans": sum(p.get("client_id") == client["id"] for p in clinical_plan_rows)} for client in clients]
        },
        "series": series,
    }


@app.get("/admin/api/pagamentos-mestre")
def admin_master_payments(admin: dict = Depends(auth.require_admin)):
    """Fila financeira do chatbot mestre, separada das mensalidades SaaS."""
    leads = leads_store.listar_leads(limite=1000, only_unassigned=True)
    relevant = [
        row for row in leads
        if row.get("pago") or row.get("payment_id") or row.get("claimed_paid_at")
        or row.get("workflow_status") in {"awaiting_payment", "awaiting_verification", "payment_confirmed", "contacted", "scheduled"}
    ]
    relevant.sort(key=lambda row: str(row.get("pago_em") or row.get("claimed_paid_at") or row.get("atualizado_em") or ""), reverse=True)
    return [{
        "session_id": row.get("session_id"),
        "name": row.get("lead_name") or "Visitante",
        "phone": row.get("lead_phone"),
        "status": "approved" if row.get("pago") else "verification" if row.get("claimed_paid_at") else "pending",
        "workflow_status": row.get("workflow_status") or "new",
        "amount": float(row.get("sale_amount") or 0),
        "payment_id": row.get("payment_id"),
        "paid_at": row.get("pago_em"),
        "updated_at": row.get("atualizado_em") or row.get("criado_em"),
        "contact_released": bool(row.get("pago")),
    } for row in relevant[:200]]


@app.post("/admin/api/pagamentos-mestre/{session_id}/verificar")
def admin_verify_master_payment(session_id: str, admin: dict = Depends(auth.require_admin)):
    """Consulta o Mercado Pago antes de liberar; nunca confia no navegador."""
    lead = leads_store.buscar_lead(session_id)
    if not lead or lead.get("client_id"):
        raise HTTPException(404, "Pagamento do chatbot mestre não encontrado")
    if lead.get("pago"):
        return {"ok": True, "status": "approved", "already_confirmed": True}
    payment_data = None
    if lead.get("payment_id"):
        payment_data = pagamento.consultar_pagamento(str(lead["payment_id"]))
    if not payment_data:
        matches = pagamento.buscar_pagamentos_por_referencia(session_id)
        payment_data = next((item for item in matches if item.get("status") == "approved"), matches[0] if matches else None)
    if not payment_data or payment_data.get("status") != "approved":
        return {"ok": True, "status": (payment_data or {}).get("status") or "pending"}
    leads_store.marcar_pago(session_id, str(payment_data.get("id") or ""), payment_data.get("transaction_amount"))
    business_store.audit(admin["id"], admin["id"], "master_payment.verified", "lead", session_id, {"payment_id": payment_data.get("id")})
    return {"ok": True, "status": "approved", "amount": payment_data.get("transaction_amount")}


@app.get("/admin/api/system-health")
def admin_system_health(user: dict = Depends(auth.require_admin)):
    """Estado operacional sem expor chaves, tokens ou valores secretos."""
    checks = {
        "ai": bool(os.getenv("GEMINI_API_KEY")) and os.getenv("IA_ATIVA", "true").lower() == "true",
        "database": bool(os.getenv("SUPABASE_URL")) and bool(os.getenv("SUPABASE_KEY")),
        "payment": bool(pagamento.PAGAMENTO_ATIVO),
        "email": bool(os.getenv("SMTP_HOST")) and bool(os.getenv("SMTP_FROM") or os.getenv("SMTP_USER")),
    }
    return {
        "ok": checks["ai"] and checks["database"],
        "checks": checks,
        "labels": {"ai": "Inteligência artificial", "database": "Banco e isolamento", "payment": "Mercado Pago", "email": "Notificações por e-mail"},
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/admin/clientes")
def create_client(payload: ClienteRequest, admin: dict = Depends(auth.require_admin)):
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.duration_days)
    defaults = {"basico": 10, "básico": 10, "essencial": 10, "pro": 50, "profissional": 50, "premium": 150, "clinica": -1, "clínica": -1}
    plan = (payload.plan or "essencial").lower()
    patient_limit = payload.patient_limit if payload.patient_limit is not None else defaults.get(plan, 10)
    return saas_store.create_user({"name": payload.name, "identifier": payload.identifier.lower().strip(), "role": "client", "active": True, "plan": payload.plan, "patient_limit": patient_limit, "expires_at": expires_at.isoformat(), "public_slug": criar_slug_publico(payload.name), "billing_status": "trial", "monthly_price": 0})


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
    allowed = {k: v for k, v in payload.items() if k in {"name", "identifier", "plan", "patient_limit", "active", "expires_at", "ai_config", "monthly_price", "billing_status", "next_billing_at", "billing_notes", "custom_domain", "billing_provider", "external_subscription_id"}}
    if "patient_limit" in allowed:
        allowed["patient_limit"] = max(-1, min(100000, int(allowed["patient_limit"])))
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


@app.delete("/admin/clientes/{user_id}")
def permanently_delete_client(user_id: str, payload: AdminDeleteRequest, admin: dict = Depends(auth.require_admin)):
    client = saas_store.get_user(user_id)
    if not client or client.get("role") != "client":
        raise HTTPException(404, "Nutricionista não encontrado")
    expected = f"EXCLUIR {client['identifier']}"
    if payload.confirmation.strip() != expected:
        raise HTTPException(400, f"Digite exatamente: {expected}")
    master = auth.authenticate_master(payload.master_code)
    if not master or master.get("id") != admin.get("id"):
        raise HTTPException(403, "Código mestre inválido")
    documents = saas_store._request("GET", "patient_documents", params={"select": "storage_path", "client_id": f"eq.{user_id}"}) or []
    for document in documents:
        path = document.get("storage_path")
        if path:
            saas_store.delete_private_asset("patient-documents", path)
    business_store.audit(admin["id"], None, "client.permanently_deleted", "saas_user", user_id, {"name": client.get("name"), "identifier": client.get("identifier")})
    # A FK legado de leads não possui CASCADE; a exclusão explícita evita
    # deixar dados pessoais órfãos e permite remover a conta com segurança.
    saas_store._request("DELETE", "leads", params={"client_id": f"eq.{user_id}"}, prefer="return=minimal")
    saas_store.delete_user(user_id)
    return {"ok": True}


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

    # O laboratório mestre usa a configuração real do nutricionista, mas
    # não cria leads, não consome franquia pública e não dispara pagamento.
    if req.test_mode:
        admin = auth.user_from_token(request, request.cookies.get(auth.COOKIE_NAME))
        if admin.get("role") != "admin":
            raise HTTPException(403, "Modo de teste disponível somente ao admin mestre")
        if not req.client_id:
            raise HTTPException(400, "Selecione um nutricionista para o teste")
        req.lead_source = "admin_test_lab"

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
    master_context = req.client_id == "master" or (not req.client_slug and not req.client_id)
    if req.client_id == "master":
        client = master_chat_user()
        resolved_client_id = None
        if not client:
            raise HTTPException(404, "Assistente indisponível")
        client_config = dict(client.get("ai_config") or {})
    elif req.client_slug:
        client = saas_store.get_user_by_slug(req.client_slug)
        resolved_client_id = client.get("id") if client else None
    elif req.client_id:
        client = saas_store.get_user(req.client_id)
    elif master_context:
        client = master_chat_user()
        client_config = dict((client or {}).get("ai_config") or {})
    if (req.client_slug or req.client_id) and req.client_id != "master":
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
    if master_context and not req.test_mode:
        if client_config.get("public_chat_enabled", True) is False:
            raise HTTPException(503, "O assistente público está temporariamente pausado.")
        daily_limit = max(1, int(client_config.get("daily_visitor_limit") or 30))
        today = datetime.now(timezone.utc).date().isoformat()
        master_leads = leads_store.listar_leads(limite=1000, only_unassigned=True)
        sessions_today = {str(row.get("session_id")) for row in master_leads if str(row.get("criado_em") or "").startswith(today)}
        if req.session_id and req.session_id not in sessions_today and len(sessions_today) >= daily_limit:
            raise HTTPException(429, "O limite de atendimentos de hoje foi alcançado. Tente novamente amanhã ou use o canal de contato disponível.")
        existing_master_lead = leads_store.buscar_lead(req.session_id) if req.session_id else None
        duration = max(1, int(client_config.get("demo_duration_minutes") or 30))
        if existing_master_lead and existing_master_lead.get("criado_em"):
            started = datetime.fromisoformat(str(existing_master_lead["criado_em"]).replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > started + timedelta(minutes=duration):
                raise HTTPException(403, "O tempo desta conversa terminou. Inicie uma nova demonstração ou fale com nossa equipe.")
    limite_gratuito = int(client_config.get("free_message_limit") or os.getenv("FREE_MESSAGE_LIMIT", "8"))
    historico_salvo = []
    if lead_atual:
        raw = lead_atual.get("historico") or []
        try:
            historico_salvo = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            historico_salvo = []
    mensagens_anteriores = sum(1 for m in historico_salvo if m.get("autor") == "user")
    atingiu_limite = False if req.test_mode else mensagens_anteriores >= limite_gratuito
    cta_cliente = client_config.get("link_consulta")
    fallback_cliente = cta_cliente or "O canal de agendamento deste profissional ainda não foi configurado. Solicite o contato diretamente à clínica."
    texto_normalizado = req.pergunta.casefold()
    intencao_consulta = any(term in texto_normalizado for term in ("consulta", "agendar", "agendamento", "marcar horário", "marcar horario", "quero pagar", "valor da consulta", "preço da consulta", "preco da consulta"))
    if intencao_consulta and resolved_client_id and not ja_pago:
        resposta = "Claro! Para dar continuidade com um atendimento personalizado, use este acesso seguro: " + MARCADOR_LINK_PAGAMENTO
    elif atingiu_limite and not ja_pago:
        resposta = "Já consegui entender melhor o que você busca. Para continuar com uma orientação realmente personalizada, o próximo passo é conversar com a nutricionista e avaliar seu caso com segurança. " + (fallback_cliente if resolved_client_id else LINK_AGENDAMENTO)
    else:
        try:
            resposta = gerar_resposta(req.pergunta, contexto, historico_dict, estado_convite, client_config)
            if not str(resposta or "").strip():
                raise RuntimeError("Resposta vazia do provedor")
        except Exception:
            # Falha transitória do provedor não derruba a experiência nem
            # expõe detalhes técnicos. O usuário pode tentar novamente.
            resposta = "Tive uma instabilidade rápida ao preparar essa resposta. Pode repetir sua dúvida em uma frase? Se você deseja marcar uma consulta, escreva ‘quero agendar’."

    # O Bruce usa um marcador em vez de escrever o link — aqui a gente
    # detecta a intenção de convidar pra consulta e troca pelo link real.
    #
    # TRAVA DE SEGURANÇA (independe do modelo obedecer a instrução ou não):
    # se o pagamento já foi confirmado, NUNCA gera uma preferência nova no
    # Mercado Pago — troca o marcador pelo contato de verdade direto. Isso
    # evita duplicar links/preferências e evita confundir quem já pagou.
    quis_agendar = atingiu_limite or MARCADOR_LINK_PAGAMENTO in resposta
    requires_contact = False
    if quis_agendar and (resolved_client_id or master_context) and not req.test_mode and not (lead_atual and lead_atual.get("lead_phone")):
        resposta = "Para enviar o link de pagamento com segurança, preciso primeiro do seu nome e WhatsApp. Preencha os dados abaixo; eles serão usados somente pela clínica para falar com você sobre este atendimento."
        requires_contact = True
    elif quis_agendar:
        if ja_pago:
            resposta = resposta.replace(MARCADOR_LINK_PAGAMENTO, CONTATO_NUTRICIONISTA)
        else:
            link_real = cta_cliente or None
            if master_context and not link_real and pagamento.PAGAMENTO_ATIVO and req.session_id:
                link_real = pagamento.criar_link_pagamento(req.session_id)
            resposta = resposta.replace(MARCADOR_LINK_PAGAMENTO, link_real or (fallback_cliente if resolved_client_id else LINK_AGENDAMENTO))

    fontes = []
    for r in resultados:
        if r["tipo"] == "alimento":
            fontes.append(r["dado"]["nome"])
        else:
            fontes.append(r["dado"]["titulo"])

    # Salva o histórico atualizado da conversa (não derruba a resposta se falhar)
    if req.session_id and not req.test_mode:
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
    request: Request,
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
        confirmed_lead = leads_store.buscar_lead(session_id_confirmado) if session_id_confirmado else None
        confirmed_owner = saas_store.get_user(confirmed_lead.get("client_id")) if confirmed_lead and confirmed_lead.get("client_id") else master_chat_user()
        steps = payment_next_steps(confirmed_lead, confirmed_owner, str(request.base_url))
        whatsapp_url = html.escape(str(steps.get("whatsapp_url") or CONTATO_NUTRICIONISTA), quote=True)
        anamnesis_url = html.escape(str(steps.get("anamnesis_url") or ""), quote=True)
        corpo = f"""
        <div id="conteudo">
            <h1>✅ Pagamento confirmado!</h1>
            <p>Você já pode adiantar seus dados. O profissional poderá responder em até 24 horas.</p>
            <p><a href="{anamnesis_url}" style="display:inline-block;padding:12px 18px;background:#2563eb;color:white;border-radius:10px;text-decoration:none;font-weight:bold;">Preencher anamnese</a></p>
            <p><a href="{whatsapp_url}" style="display:inline-block;padding:12px 18px;background:#059669;color:white;border-radius:10px;text-decoration:none;font-weight:bold;">Falar no WhatsApp</a></p>
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
                            <p>Você já pode adiantar seus dados. O profissional poderá responder em até 24 horas.</p>
                            <p><a href="${{dados.anamnesis_url}}" style="display:inline-block;padding:12px 18px;background:#2563eb;color:white;border-radius:10px;text-decoration:none;font-weight:bold;">Preencher anamnese</a></p>
                            <p><a href="${{dados.whatsapp_url || dados.contato}}" style="display:inline-block;padding:12px 18px;background:#059669;color:white;border-radius:10px;text-decoration:none;font-weight:bold;">Falar no WhatsApp</a></p>
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
def verificar_contato(request: Request, session_id: str = Query(default="")):
    """
    Endpoint que o frontend pode consultar pra saber se já pode mostrar o
    contato do nutricionista pra essa sessão (só libera se pago=true).
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id é obrigatório.")

    lead = leads_store.buscar_lead(session_id)
    owner = saas_store.get_user(lead.get("client_id")) if lead and lead.get("client_id") else master_chat_user()
    return payment_next_steps(lead, owner, str(request.base_url))


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
