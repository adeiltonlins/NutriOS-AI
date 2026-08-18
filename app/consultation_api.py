"""Fluxo de consulta integrado ao router clínico existente."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import auth, business_store, patient_auth, saas_store
from app.clinical_extensions import router, owned_patient

STATIC_DIR = Path(__file__).resolve().parent / "static"

PRECONSULTATION_SCHEMA = [
    ["goal", "Qual é seu principal objetivo hoje?", "text"],
    ["routine", "Como é sua rotina de alimentação e horários?", "textarea"],
    ["preferences", "Quais alimentos você gosta e quais prefere evitar?", "textarea"],
    ["restrictions", "Possui alergias, intolerâncias ou restrições alimentares?", "textarea"],
    ["training", "Como está sua rotina de atividade física?", "text"],
    ["sleep", "Como está seu sono?", "text"],
    ["hydration", "Como está sua hidratação ao longo do dia?", "text"],
    ["difficulties", "Qual é sua maior dificuldade para seguir uma alimentação?", "textarea"],
    ["supplements", "Usa medicamentos ou suplementos que gostaria de informar ao nutricionista?", "textarea"],
]


class ConsultationMode(BaseModel):
    mode: str = Field(pattern="^(presencial|online)$")


class NotesIn(BaseModel):
    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""


class AnswersIn(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)


def _appointment(appointment_id: str, client_id: str) -> dict:
    rows = saas_store._request(
        "GET", "appointments",
        params={"select": "*", "id": f"eq.{appointment_id}", "client_id": f"eq.{client_id}", "limit": "1"},
    ) or []
    if not rows:
        raise HTTPException(404, "Consulta não encontrada")
    return rows[0]


def _pre(appointment_id: str, client_id: str) -> dict | None:
    rows = saas_store._request(
        "GET", "preconsultation_forms",
        params={"select": "*", "appointment_id": f"eq.{appointment_id}", "client_id": f"eq.{client_id}", "order": "created_at.desc", "limit": "1"},
    ) or []
    return rows[0] if rows else None


def _note(appointment_id: str, client_id: str) -> dict | None:
    rows = saas_store._request(
        "GET", "consultation_notes",
        params={"select": "*", "appointment_id": f"eq.{appointment_id}", "client_id": f"eq.{client_id}", "order": "created_at.desc", "limit": "1"},
    ) or []
    return rows[0] if rows else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summary(answers: dict[str, Any]) -> dict[str, Any]:
    """Resumo estruturado e determinístico; a IA generativa entra depois da autorização do profissional."""
    labels = {
        "goal": "Objetivo", "routine": "Rotina", "preferences": "Preferências",
        "restrictions": "Restrições", "training": "Treino", "sleep": "Sono",
        "hydration": "Hidratação", "difficulties": "Dificuldades", "supplements": "Medicamentos/suplementos",
    }
    filled = [{"label": labels[k], "value": str(v).strip()} for k, v in answers.items() if k in labels and str(v).strip()]
    return {"highlights": filled[:12], "filled_fields": len(filled), "source": "preconsulta"}


@router.get("/app/consulta")
def consultation_page(user: dict = Depends(auth.current_user)):
    return FileResponse(STATIC_DIR / "consultation-workspace.html", headers={"Cache-Control": "no-store"})


@router.get("/app/api/consultas")
def list_consultations(limit: int = 30, user: dict = Depends(auth.current_user)):
    rows = business_store.list_rows("appointments", user["id"], order="starts_at.asc", extra={"limit": str(max(1, min(limit, 100)))})
    return rows


@router.get("/app/api/consultas/{appointment_id}/contexto")
def consultation_context(appointment_id: str, user: dict = Depends(auth.current_user)):
    appt = _appointment(appointment_id, user["id"])
    patient_id = appt.get("patient_id")
    if not patient_id:
        raise HTTPException(409, "Esta consulta ainda não está vinculada a um paciente")
    owned_patient(patient_id, user["id"])
    return {"appointment": appt, "preconsultation": _pre(appointment_id, user["id"]), "note": _note(appointment_id, user["id"])}


@router.post("/app/api/consultas/{appointment_id}/pre-consulta")
def create_preconsultation(appointment_id: str, user: dict = Depends(auth.current_user)):
    appt = _appointment(appointment_id, user["id"])
    patient_id = appt.get("patient_id")
    if not patient_id:
        raise HTTPException(409, "Vincule um paciente antes de enviar a pré-consulta")
    owned_patient(patient_id, user["id"])
    current = _pre(appointment_id, user["id"])
    if current:
        return current
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = {
        "appointment_id": appointment_id, "patient_id": patient_id, "client_id": user["id"],
        "status": "sent", "schema_snapshot": PRECONSULTATION_SCHEMA, "answers": {}, "summary": {},
        "token_hash": token_hash, "sent_at": _now(), "updated_at": _now(),
    }
    created = saas_store._request("POST", "preconsultation_forms", payload=row, prefer="return=representation") or []
    if not created:
        raise HTTPException(500, "Não foi possível criar a pré-consulta")
    return {**created[0], "patient_link": f"/paciente/pre-consulta?token={token}"}


@router.post("/app/api/consultas/{appointment_id}/sala")
def create_meeting(appointment_id: str, payload: ConsultationMode, user: dict = Depends(auth.current_user)):
    appt = _appointment(appointment_id, user["id"])
    data = {"consultation_mode": payload.mode}
    if payload.mode == "online":
        room = f"nutrios-{user['id'][:8]}-{secrets.token_urlsafe(18).replace('-', '').replace('_', '')}"
        data["meeting_url"] = f"https://meet.jit.si/{room}"
    else:
        data["meeting_url"] = None
    updated = saas_store._request("PATCH", "appointments", params={"id": f"eq.{appt['id']}", "client_id": f"eq.{user['id']}"}, payload=data, prefer="return=representation") or []
    return updated[0] if updated else {**appt, **data}


@router.post("/app/api/consultas/{appointment_id}/iniciar")
def start_consultation(appointment_id: str, user: dict = Depends(auth.current_user)):
    appt = _appointment(appointment_id, user["id"])
    data = {"consultation_status": "in_progress", "consultation_started_at": _now()}
    rows = saas_store._request("PATCH", "appointments", params={"id": f"eq.{appt['id']}", "client_id": f"eq.{user['id']}"}, payload=data, prefer="return=representation") or []
    return rows[0] if rows else {**appt, **data}


@router.post("/app/api/consultas/{appointment_id}/concluir")
def finish_consultation(appointment_id: str, user: dict = Depends(auth.current_user)):
    appt = _appointment(appointment_id, user["id"])
    data = {"consultation_status": "completed", "consultation_completed_at": _now()}
    rows = saas_store._request("PATCH", "appointments", params={"id": f"eq.{appt['id']}", "client_id": f"eq.{user['id']}"}, payload=data, prefer="return=representation") or []
    return rows[0] if rows else {**appt, **data}


@router.post("/app/api/consultas/{appointment_id}/notas")
def save_notes(appointment_id: str, payload: NotesIn, user: dict = Depends(auth.current_user)):
    appt = _appointment(appointment_id, user["id"])
    patient_id = appt.get("patient_id")
    if not patient_id:
        raise HTTPException(409, "Consulta sem paciente")
    owned_patient(patient_id, user["id"])
    data = {"appointment_id": appointment_id, "patient_id": patient_id, "client_id": user["id"], **payload.model_dump(), "updated_at": _now()}
    current = _note(appointment_id, user["id"])
    if current:
        rows = saas_store._request("PATCH", "consultation_notes", params={"id": f"eq.{current['id']}", "client_id": f"eq.{user['id']}"}, payload=data, prefer="return=representation") or []
    else:
        rows = saas_store._request("POST", "consultation_notes", payload={**data, "created_at": _now(), "ai_summary": {}}, prefer="return=representation") or []
    return rows[0] if rows else data


@router.get("/paciente/api/pre-consulta")
def patient_preconsultations(patient: dict = Depends(patient_auth.current_patient)):
    return saas_store._request("GET", "preconsultation_forms", params={"select": "id,appointment_id,status,schema_snapshot,answers,summary,sent_at,completed_at", "patient_id": f"eq.{patient['id']}", "order": "created_at.desc"}) or []


@router.patch("/paciente/api/pre-consulta/{form_id}")
def answer_preconsultation(form_id: str, payload: AnswersIn, patient: dict = Depends(patient_auth.current_patient)):
    rows = saas_store._request(
        "PATCH", "preconsultation_forms",
        params={"id": f"eq.{form_id}", "patient_id": f"eq.{patient['id']}"},
        payload={"answers": payload.answers, "summary": _summary(payload.answers), "status": "completed", "completed_at": _now(), "updated_at": _now()},
        prefer="return=representation",
    ) or []
    if not rows:
        raise HTTPException(404, "Pré-consulta não encontrada")
    return rows[0]
