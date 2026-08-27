"""NutriOS V2 clinical modules layered onto the existing authenticated router.

This module intentionally reuses clinical_extensions.router so main.py does not
need a second include_router call. Every professional operation validates patient
ownership and every patient-facing read is scoped to the authenticated account.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from app import auth, business_store, clinical_extensions, patient_auth, saas_store

router = clinical_extensions.router
owned_patient = clinical_extensions.owned_patient


class LabExamIn(BaseModel):
    exam_name: str = Field(min_length=2, max_length=180)
    category: str = Field(default="laboratory", max_length=80)
    collected_at: date | None = None
    value_numeric: float | None = None
    value_text: str | None = Field(default=None, max_length=240)
    unit: str | None = Field(default=None, max_length=40)
    reference_min: float | None = None
    reference_max: float | None = None
    reference_text: str | None = Field(default=None, max_length=240)
    notes: str | None = Field(default=None, max_length=2000)
    source: str = Field(default="manual", pattern=r"^(manual|document)$")


class LabExamUpdate(LabExamIn):
    pass


class SupplementIn(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    dose: str | None = Field(default=None, max_length=120)
    frequency: str | None = Field(default=None, max_length=120)
    schedule: str | None = Field(default=None, max_length=160)
    route: str = Field(default="oral", max_length=60)
    objective: str | None = Field(default=None, max_length=400)
    instructions: str | None = Field(default=None, max_length=1600)
    starts_at: date | None = None
    ends_at: date | None = None
    status: str = Field(default="active", pattern=r"^(active|paused|completed|cancelled)$")


class SupplementUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    dose: str | None = Field(default=None, max_length=120)
    frequency: str | None = Field(default=None, max_length=120)
    schedule: str | None = Field(default=None, max_length=160)
    route: str | None = Field(default=None, max_length=60)
    objective: str | None = Field(default=None, max_length=400)
    instructions: str | None = Field(default=None, max_length=1600)
    starts_at: date | None = None
    ends_at: date | None = None
    status: str | None = Field(default=None, pattern=r"^(active|paused|completed|cancelled)$")


def _exam_status(payload: LabExamIn) -> str:
    value = payload.value_numeric
    if value is None:
        return "normal"
    if payload.reference_min is not None and value < payload.reference_min:
        return "low"
    if payload.reference_max is not None and value > payload.reference_max:
        return "high"
    return "normal"


def _owned_row(table: str, row_id: str, patient_id: str, client_id: str) -> dict:
    row = business_store.get_row(table, row_id, client_id)
    if not row or row.get("patient_id") != patient_id:
        raise HTTPException(404, "Registro não encontrado")
    return row


@router.get("/app/api/pacientes/{patient_id}/exames")
def list_lab_exams(patient_id: str, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    return business_store.list_rows(
        "patient_lab_exams",
        user["id"],
        order="collected_at.desc,created_at.desc",
        extra={"patient_id": f"eq.{patient_id}"},
    )


@router.post("/app/api/pacientes/{patient_id}/exames")
def create_lab_exam(patient_id: str, payload: LabExamIn, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    data = payload.model_dump(mode="json", exclude_none=True)
    data["patient_id"] = patient_id
    data["status"] = _exam_status(payload)
    row = business_store.create_row("patient_lab_exams", user["id"], data)
    business_store.audit(user["id"], user["id"], "lab_exam.created", "patient_lab_exam", row.get("id", ""), {"patient_id": patient_id})
    return row


@router.patch("/app/api/pacientes/{patient_id}/exames/{row_id}")
def update_lab_exam(patient_id: str, row_id: str, payload: LabExamUpdate, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    _owned_row("patient_lab_exams", row_id, patient_id, user["id"])
    data = payload.model_dump(mode="json", exclude_none=True)
    data["status"] = _exam_status(payload)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    return business_store.update_row("patient_lab_exams", row_id, user["id"], data)


@router.delete("/app/api/pacientes/{patient_id}/exames/{row_id}", status_code=204)
def delete_lab_exam(patient_id: str, row_id: str, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    _owned_row("patient_lab_exams", row_id, patient_id, user["id"])
    business_store.delete_row("patient_lab_exams", row_id, user["id"])
    business_store.audit(user["id"], user["id"], "lab_exam.deleted", "patient_lab_exam", row_id, {"patient_id": patient_id})


@router.get("/app/api/pacientes/{patient_id}/suplementos")
def list_supplements(patient_id: str, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    return business_store.list_rows(
        "patient_supplements",
        user["id"],
        order="created_at.desc",
        extra={"patient_id": f"eq.{patient_id}"},
    )


@router.post("/app/api/pacientes/{patient_id}/suplementos")
def create_supplement(patient_id: str, payload: SupplementIn, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    data = payload.model_dump(mode="json", exclude_none=True)
    data["patient_id"] = patient_id
    row = business_store.create_row("patient_supplements", user["id"], data)
    business_store.audit(user["id"], user["id"], "supplement.created", "patient_supplement", row.get("id", ""), {"patient_id": patient_id})
    return row


@router.patch("/app/api/pacientes/{patient_id}/suplementos/{row_id}")
def update_supplement(patient_id: str, row_id: str, payload: SupplementUpdate, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    _owned_row("patient_supplements", row_id, patient_id, user["id"])
    data = payload.model_dump(mode="json", exclude_none=True)
    if not data:
        raise HTTPException(400, "Nenhuma alteração informada")
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    return business_store.update_row("patient_supplements", row_id, user["id"], data)


@router.delete("/app/api/pacientes/{patient_id}/suplementos/{row_id}", status_code=204)
def delete_supplement(patient_id: str, row_id: str, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    _owned_row("patient_supplements", row_id, patient_id, user["id"])
    business_store.delete_row("patient_supplements", row_id, user["id"])
    business_store.audit(user["id"], user["id"], "supplement.deleted", "patient_supplement", row_id, {"patient_id": patient_id})


@router.get("/paciente/api/suplementos")
def patient_supplements(patient: dict = Depends(patient_auth.current_patient)):
    return saas_store._request(
        "GET",
        "patient_supplements",
        params={
            "select": "id,name,dose,frequency,schedule,route,objective,instructions,starts_at,ends_at,status,created_at",
            "patient_id": f"eq.{patient['id']}",
            "client_id": f"eq.{patient['client_id']}",
            "status": "in.(active,paused)",
            "order": "created_at.desc",
        },
    ) or []
