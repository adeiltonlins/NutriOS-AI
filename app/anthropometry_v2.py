"""Advanced anthropometry for NutriOS V2 without changing the existing assessment model."""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from app import auth, business_store, clinical_extensions

router = clinical_extensions.router
owned_patient = clinical_extensions.owned_patient

SKINFOLD_KEYS = {"chest","midaxillary","triceps","subscapular","abdomen","suprailiac","thigh"}
CIRC_KEYS = {"neck","chest","waist","abdomen","hip","arm_right","arm_left","thigh_right","thigh_left","calf_right","calf_left"}
POSTURE_KEYS = {"head","shoulders","spine","pelvis","knees","feet","notes"}


class AdvancedAnthropometryIn(BaseModel):
    assessed_at: date | None = None
    weight_kg: float | None = Field(default=None, ge=20, le=500)
    height_cm: float | None = Field(default=None, ge=80, le=250)
    waist_cm: float | None = Field(default=None, ge=20, le=300)
    hip_cm: float | None = Field(default=None, ge=20, le=300)
    protocol: str = Field(default="manual", pattern=r"^(manual|pollock3|pollock7)$")
    age: int | None = Field(default=None, ge=12, le=120)
    sex: str | None = Field(default=None, pattern=r"^(female|male)$")
    skinfolds: dict[str, float] = Field(default_factory=dict)
    circumferences: dict[str, float] = Field(default_factory=dict)
    posture: dict[str, str] = Field(default_factory=dict)
    body_fat_percent: float | None = Field(default=None, ge=0, le=80)
    notes: str | None = Field(default=None, max_length=3000)


def _validate_map(data: dict, allowed: set[str], *, max_value: float = 500) -> dict:
    clean = {}
    for key, value in data.items():
        if key not in allowed:
            raise HTTPException(422, f"Campo não suportado: {key}")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise HTTPException(422, f"Valor inválido para {key}")
        if number < 0 or number > max_value:
            raise HTTPException(422, f"Valor fora do intervalo para {key}")
        clean[key] = round(number, 2)
    return clean


def _validate_posture(data: dict[str, str]) -> dict[str, str]:
    clean = {}
    for key, value in data.items():
        if key not in POSTURE_KEYS:
            raise HTTPException(422, f"Campo postural não suportado: {key}")
        text = str(value or "").strip()
        if len(text) > 500:
            raise HTTPException(422, f"Descrição postural muito longa: {key}")
        if text:
            clean[key] = text
    return clean


def _pollock(protocol: str, sex: str | None, age: int | None, folds: dict[str, float]) -> tuple[float | None, float | None]:
    if protocol == "manual":
        return None, None
    if not sex or age is None:
        raise HTTPException(422, "Pollock exige sexo e idade")
    if protocol == "pollock3":
        sites = ["chest", "abdomen", "thigh"] if sex == "male" else ["triceps", "suprailiac", "thigh"]
        missing = [s for s in sites if s not in folds]
        if missing:
            raise HTTPException(422, "Pollock 3 exige as dobras: " + ", ".join(missing))
        total = sum(folds[s] for s in sites)
        if sex == "male":
            density = 1.10938 - 0.0008267 * total + 0.0000016 * total * total - 0.0002574 * age
        else:
            density = 1.0994921 - 0.0009929 * total + 0.0000023 * total * total - 0.0001392 * age
    else:
        sites = ["chest","midaxillary","triceps","subscapular","abdomen","suprailiac","thigh"]
        missing = [s for s in sites if s not in folds]
        if missing:
            raise HTTPException(422, "Pollock 7 exige as sete dobras padronizadas")
        total = sum(folds[s] for s in sites)
        if sex == "male":
            density = 1.112 - 0.00043499 * total + 0.00000055 * total * total - 0.00028826 * age
        else:
            density = 1.097 - 0.00046971 * total + 0.00000056 * total * total - 0.00012828 * age
    if density <= 0:
        raise HTTPException(422, "Não foi possível calcular densidade corporal")
    fat = 495 / density - 450
    return round(density, 6), round(max(0, min(80, fat)), 2)


@router.get("/app/api/pacientes/{patient_id}/antropometria-avancada")
def list_advanced_anthropometry(patient_id: str, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    return business_store.list_rows(
        "patient_anthropometry_advanced",
        user["id"],
        order="created_at.desc",
        extra={"patient_id": f"eq.{patient_id}"},
    )


@router.post("/app/api/pacientes/{patient_id}/antropometria-avancada")
def create_advanced_anthropometry(patient_id: str, payload: AdvancedAnthropometryIn, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    folds = _validate_map(payload.skinfolds, SKINFOLD_KEYS, max_value=100)
    circumferences = _validate_map(payload.circumferences, CIRC_KEYS, max_value=300)
    posture = _validate_posture(payload.posture)
    density, calculated_fat = _pollock(payload.protocol, payload.sex, payload.age, folds)
    body_fat = calculated_fat if calculated_fat is not None else payload.body_fat_percent

    base = {
        "patient_id": patient_id,
        "assessed_at": (payload.assessed_at or date.today()).isoformat(),
        "evaluation_method": {"pollock3":"Jackson & Pollock 3 dobras","pollock7":"Jackson & Pollock 7 dobras","manual":"Antropometria avançada"}[payload.protocol],
    }
    for key in ("weight_kg","height_cm","waist_cm","hip_cm"):
        value = getattr(payload, key)
        if value is not None:
            base[key] = value
    if body_fat is not None:
        base["body_fat_percent"] = body_fat
    if payload.notes:
        base["notes"] = payload.notes
    assessment = business_store.create_row("anthropometric_assessments", user["id"], base)

    fat_mass = lean_mass = None
    if payload.weight_kg is not None and body_fat is not None:
        fat_mass = round(payload.weight_kg * body_fat / 100, 2)
        lean_mass = round(payload.weight_kg - fat_mass, 2)

    advanced = business_store.create_row("patient_anthropometry_advanced", user["id"], {
        "patient_id": patient_id,
        "assessment_id": assessment["id"],
        "protocol": payload.protocol,
        "age": payload.age,
        "sex": payload.sex,
        "skinfolds": folds,
        "circumferences": circumferences,
        "posture": posture,
        "body_density": density,
        "calculated_body_fat_percent": body_fat,
        "calculated_fat_mass_kg": fat_mass,
        "calculated_lean_mass_kg": lean_mass,
        "notes": payload.notes,
    })
    business_store.audit(user["id"], user["id"], "anthropometry_advanced.created", "anthropometric_assessment", assessment["id"], {"patient_id": patient_id, "protocol": payload.protocol})
    return {"assessment": assessment, "advanced": advanced}


@router.delete("/app/api/pacientes/{patient_id}/antropometria-avancada/{row_id}", status_code=204)
def delete_advanced_anthropometry(patient_id: str, row_id: str, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    row = business_store.get_row("patient_anthropometry_advanced", row_id, user["id"])
    if not row or row.get("patient_id") != patient_id:
        raise HTTPException(404, "Avaliação não encontrada")
    assessment_id = row.get("assessment_id")
    business_store.delete_row("patient_anthropometry_advanced", row_id, user["id"])
    if assessment_id:
        business_store.delete_row("anthropometric_assessments", assessment_id, user["id"])
    business_store.audit(user["id"], user["id"], "anthropometry_advanced.deleted", "anthropometric_assessment", str(assessment_id or row_id), {"patient_id": patient_id})
