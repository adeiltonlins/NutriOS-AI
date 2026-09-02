"""Advanced anthropometry using the current organization-based NutriOS schema."""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from app import auth, business_store, clinical_extensions

router = clinical_extensions.router

SKINFOLD_KEYS = {"chest", "midaxillary", "triceps", "subscapular", "abdomen", "suprailiac", "thigh", "calf"}
CIRC_KEYS = {"neck", "chest", "waist", "abdomen", "hip", "arm_right", "arm_left", "thigh_right", "thigh_left", "calf_right", "calf_left"}
POSTURE_KEYS = {"head", "shoulders", "spine", "pelvis", "knees", "feet", "notes"}

FOLD_LABELS = {
    "chest": "Peitoral", "midaxillary": "Axilar média", "triceps": "Tríceps",
    "subscapular": "Subescapular", "abdomen": "Abdominal", "suprailiac": "Suprailíaca",
    "thigh": "Coxa", "calf": "Panturrilha medial",
}

PROTOCOLS = {
    "manual": {
        "label": "Avaliação manual / outro método", "short_label": "Manual",
        "indication": "Quando o profissional utilizar bioimpedância, DEXA, outro protocolo ou informar o percentual de gordura manualmente.",
        "sex": "Ambos", "age_range": None,
        "required_by_sex": {"male": [], "female": []},
        "required_fields_by_sex": {"male": [], "female": []},
        "formula": "Sem cálculo automático de densidade corporal. O percentual de gordura informado é registrado como dado profissional.",
        "automatic": False,
    },
    "pollock3": {
        "label": "Jackson & Pollock — 3 dobras", "short_label": "Jackson & Pollock — 3 dobras",
        "indication": "Estimativa de densidade corporal em adultos usando três dobras específicas conforme o sexo.",
        "sex": "Masculino e feminino", "age_range": {"male": [18, 61], "female": [18, 55]},
        "required_by_sex": {"male": ["chest", "abdomen", "thigh"], "female": ["triceps", "suprailiac", "thigh"]},
        "required_fields_by_sex": {"male": ["age"], "female": ["age"]},
        "formula": "Equações generalizadas de Jackson & Pollock para densidade corporal (3 dobras), com conversão para % de gordura pela equação de Siri.",
        "automatic": True,
    },
    "pollock7": {
        "label": "Jackson & Pollock — 7 dobras", "short_label": "Jackson & Pollock — 7 dobras",
        "indication": "Avaliação por sete dobras cutâneas padronizadas e idade.",
        "sex": "Masculino e feminino", "age_range": {"male": [18, 61], "female": [18, 55]},
        "required_by_sex": {
            "male": ["chest", "midaxillary", "triceps", "subscapular", "abdomen", "suprailiac", "thigh"],
            "female": ["chest", "midaxillary", "triceps", "subscapular", "abdomen", "suprailiac", "thigh"],
        },
        "required_fields_by_sex": {"male": ["age"], "female": ["age"]},
        "formula": "Equações generalizadas de Jackson & Pollock para densidade corporal (7 dobras), com conversão para % de gordura pela equação de Siri.",
        "automatic": True,
    },
    "petroski": {
        "label": "Petroski — 4 dobras", "short_label": "Petroski",
        "indication": "Equação generalizada desenvolvida para adultos brasileiros. O NutriOS identifica explicitamente a equação utilizada.",
        "sex": "Masculino e feminino", "age_range": {"male": [18, 66], "female": [18, 51]},
        "required_by_sex": {
            "male": ["subscapular", "triceps", "suprailiac", "calf"],
            "female": ["subscapular", "triceps", "suprailiac", "calf"],
        },
        "required_fields_by_sex": {"male": ["age"], "female": ["age", "weight_kg", "height_cm"]},
        "formula": "Petroski (1995), soma de 4 dobras. Homens: D = 1,10726863 − 0,00081201·Σ4 + 0,00000212·Σ4² − 0,00041761·idade. Mulheres: D = 1,02902361 − 0,00067159·Σ4 + 0,00000242·Σ4² − 0,00026073·idade − 0,00056009·peso + 0,00054649·altura. %G pela equação de Siri.",
        "automatic": True,
    },
}


class AdvancedAnthropometryIn(BaseModel):
    assessed_at: date | None = None
    weight_kg: float | None = Field(default=None, ge=20, le=500)
    height_cm: float | None = Field(default=None, ge=80, le=250)
    waist_cm: float | None = Field(default=None, ge=20, le=300)
    hip_cm: float | None = Field(default=None, ge=20, le=300)
    protocol: str = Field(default="manual", pattern=r"^(manual|pollock3|pollock7|petroski)$")
    age: int | None = Field(default=None, ge=12, le=120)
    sex: str | None = Field(default=None, pattern=r"^(female|male)$")
    skinfolds: dict[str, float] = Field(default_factory=dict)
    circumferences: dict[str, float] = Field(default_factory=dict)
    posture: dict[str, str] = Field(default_factory=dict)
    body_fat_percent: float | None = Field(default=None, ge=0, le=80)
    notes: str | None = Field(default=None, max_length=3000)


def _organization_id(user_id: str) -> str:
    return business_store.organization_id_for_user(user_id)


def _owned_patient(patient_id: str, user_id: str) -> dict:
    organization_id = _organization_id(user_id)
    rows = business_store.list_org_rows("patients", organization_id, order="created_at.desc", extra={"id": f"eq.{patient_id}", "limit": "1"})
    if not rows:
        raise HTTPException(404, "Paciente não encontrado")
    return rows[0]


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


def _protocol_public(key: str) -> dict:
    p = PROTOCOLS[key]
    return {
        "key": key, "label": p["label"], "short_label": p["short_label"], "indication": p["indication"],
        "sex": p["sex"], "age_range": p["age_range"], "required_by_sex": p["required_by_sex"],
        "required_fields_by_sex": p["required_fields_by_sex"],
        "required_labels_by_sex": {sex: [FOLD_LABELS[x] for x in folds] for sex, folds in p["required_by_sex"].items()},
        "formula": p["formula"], "automatic": p["automatic"],
    }


def _validate_protocol_profile(payload: AdvancedAnthropometryIn, folds: dict[str, float]) -> None:
    protocol = PROTOCOLS[payload.protocol]
    if not protocol["automatic"]:
        return
    if not payload.sex:
        raise HTTPException(422, "Selecione o sexo para aplicar este protocolo")
    if payload.age is None:
        raise HTTPException(422, "Informe a idade para aplicar este protocolo")
    age_range = protocol["age_range"].get(payload.sex) if protocol["age_range"] else None
    if age_range and not (age_range[0] <= payload.age <= age_range[1]):
        raise HTTPException(422, f"{protocol['label']} não será calculado automaticamente para este perfil: faixa etária prevista no NutriOS é de {age_range[0]} a {age_range[1]} anos.")
    required_fields = protocol["required_fields_by_sex"].get(payload.sex, [])
    missing_fields = [name for name in required_fields if getattr(payload, name, None) is None]
    if missing_fields:
        labels = {"age": "idade", "weight_kg": "peso", "height_cm": "altura"}
        raise HTTPException(422, "Este protocolo exige: " + ", ".join(labels[x] for x in missing_fields))
    required_folds = protocol["required_by_sex"].get(payload.sex, [])
    missing = [name for name in required_folds if name not in folds]
    if missing:
        raise HTTPException(422, "Dobras obrigatórias: " + ", ".join(FOLD_LABELS[x] for x in missing))


def _siri(density: float) -> float:
    if density <= 0:
        raise HTTPException(422, "Não foi possível calcular densidade corporal")
    return round(max(0, min(80, 495 / density - 450)), 2)


def _calculate_protocol(payload: AdvancedAnthropometryIn, folds: dict[str, float]) -> tuple[float | None, float | None]:
    if payload.protocol == "manual":
        return None, None
    _validate_protocol_profile(payload, folds)
    sex, age = payload.sex, payload.age
    if payload.protocol == "pollock3":
        total = sum(folds[s] for s in PROTOCOLS["pollock3"]["required_by_sex"][sex])
        density = (1.10938 - 0.0008267 * total + 0.0000016 * total * total - 0.0002574 * age) if sex == "male" else (1.0994921 - 0.0009929 * total + 0.0000023 * total * total - 0.0001392 * age)
    elif payload.protocol == "pollock7":
        total = sum(folds[s] for s in PROTOCOLS["pollock7"]["required_by_sex"][sex])
        density = (1.112 - 0.00043499 * total + 0.00000055 * total * total - 0.00028826 * age) if sex == "male" else (1.097 - 0.00046971 * total + 0.00000056 * total * total - 0.00012828 * age)
    else:
        total = sum(folds[s] for s in PROTOCOLS["petroski"]["required_by_sex"][sex])
        if sex == "male":
            density = 1.10726863 - 0.00081201 * total + 0.00000212 * total * total - 0.00041761 * age
        else:
            density = 1.02902361 - 0.00067159 * total + 0.00000242 * total * total - 0.00026073 * age - 0.00056009 * payload.weight_kg + 0.00054649 * payload.height_cm
    return round(density, 6), _siri(density)


def _pollock(protocol: str, sex: str | None, age: int | None, folds: dict[str, float]) -> tuple[float | None, float | None]:
    payload = AdvancedAnthropometryIn(protocol=protocol, sex=sex, age=age, skinfolds=folds)
    return _calculate_protocol(payload, folds)


def _legacy_view(row: dict) -> dict:
    data = row.get("measurements") or {}
    protocol = data.get("protocol") or "manual"
    info = PROTOCOLS.get(protocol, PROTOCOLS["manual"])
    return {
        "id": row["id"], "organization_id": row.get("organization_id"), "patient_id": row.get("patient_id"),
        "assessment_id": row["id"], "assessed_at": row.get("measured_at"), "created_at": row.get("created_at"),
        "weight_kg": row.get("weight_kg"), "height_cm": row.get("height_cm"), "waist_cm": row.get("waist_cm"), "hip_cm": row.get("hip_cm"),
        "protocol": protocol, "protocol_label": data.get("protocol_label") or info["label"], "age": data.get("age"), "sex": data.get("sex"),
        "skinfolds": data.get("skinfolds") or {}, "circumferences": data.get("circumferences") or {}, "posture": data.get("posture") or {},
        "body_density": data.get("body_density"), "calculated_body_fat_percent": row.get("body_fat_pct"),
        "calculated_fat_mass_kg": data.get("fat_mass_kg"), "calculated_lean_mass_kg": data.get("lean_mass_kg"),
        "notes": data.get("notes"), "evaluation_method": data.get("protocol_label") or info["label"],
    }


@router.get("/app/api/antropometria/protocolos")
def list_anthropometry_protocols(user: dict = Depends(auth.current_user)):
    return [_protocol_public(key) for key in ("manual", "pollock3", "pollock7", "petroski")]


@router.get("/app/api/pacientes/{patient_id}/antropometria-avancada")
def list_advanced_anthropometry(patient_id: str, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    organization_id = _organization_id(user["id"])
    rows = business_store.list_org_rows("anthropometry_measurements", organization_id, order="measured_at.desc", extra={"patient_id": f"eq.{patient_id}"})
    return [_legacy_view(row) for row in rows]


@router.post("/app/api/pacientes/{patient_id}/antropometria-avancada")
def create_advanced_anthropometry(patient_id: str, payload: AdvancedAnthropometryIn, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    organization_id = _organization_id(user["id"])
    folds = _validate_map(payload.skinfolds, SKINFOLD_KEYS, max_value=100)
    circumferences = _validate_map(payload.circumferences, CIRC_KEYS, max_value=300)
    posture = _validate_posture(payload.posture)
    density, calculated_fat = _calculate_protocol(payload, folds)
    body_fat = calculated_fat if calculated_fat is not None else payload.body_fat_percent
    protocol_info = PROTOCOLS[payload.protocol]
    fat_mass = lean_mass = None
    if payload.weight_kg is not None and body_fat is not None:
        fat_mass = round(payload.weight_kg * body_fat / 100, 2)
        lean_mass = round(payload.weight_kg - fat_mass, 2)

    measurements = {
        "protocol": payload.protocol, "protocol_label": protocol_info["label"], "age": payload.age, "sex": payload.sex,
        "skinfolds": folds, "circumferences": circumferences, "posture": posture, "body_density": density,
        "fat_mass_kg": fat_mass, "lean_mass_kg": lean_mass, "notes": payload.notes,
    }
    row = business_store.create_org_row("anthropometry_measurements", organization_id, {
        "patient_id": patient_id,
        "measured_at": datetime.combine(payload.assessed_at or date.today(), datetime.min.time(), tzinfo=timezone.utc).isoformat(),
        "weight_kg": payload.weight_kg, "height_cm": payload.height_cm, "body_fat_pct": body_fat,
        "muscle_mass_kg": lean_mass, "waist_cm": payload.waist_cm, "hip_cm": payload.hip_cm,
        "neck_cm": circumferences.get("neck"), "measurements": measurements,
    })
    advanced = _legacy_view(row)
    assessment = {
        "id": row["id"], "patient_id": patient_id, "assessed_at": advanced["assessed_at"],
        "evaluation_method": protocol_info["label"], "weight_kg": row.get("weight_kg"), "height_cm": row.get("height_cm"),
        "waist_cm": row.get("waist_cm"), "hip_cm": row.get("hip_cm"), "body_fat_percent": row.get("body_fat_pct"), "notes": payload.notes,
    }
    business_store.audit(user["id"], organization_id, "anthropometry.created", "anthropometry_measurement", row["id"], {"patient_id": patient_id, "protocol": payload.protocol})
    return {"assessment": assessment, "advanced": advanced}


@router.delete("/app/api/pacientes/{patient_id}/antropometria-avancada/{row_id}", status_code=204)
def delete_advanced_anthropometry(patient_id: str, row_id: str, user: dict = Depends(auth.current_user)):
    _owned_patient(patient_id, user["id"])
    organization_id = _organization_id(user["id"])
    row = business_store.get_org_row("anthropometry_measurements", row_id, organization_id)
    if not row or row.get("patient_id") != patient_id:
        raise HTTPException(404, "Avaliação não encontrada")
    business_store.delete_org_row("anthropometry_measurements", row_id, organization_id)
    business_store.audit(user["id"], organization_id, "anthropometry.deleted", "anthropometry_measurement", row_id, {"patient_id": patient_id})
