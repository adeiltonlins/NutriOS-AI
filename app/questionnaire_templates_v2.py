"""Manageable questionnaire templates for NutriOS clinical workflows."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from app import auth, business_store, clinical_extensions

router = clinical_extensions.router
owned_patient = clinical_extensions.owned_patient

ALLOWED_FIELD_TYPES = {"text", "textarea", "number", "scale", "boolean", "date", "select"}


class TemplateFieldIn(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=2, max_length=180)
    type: str = Field(default="text", max_length=30)
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=30)


class QuestionnaireTemplateIn(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    category: str = Field(default="custom", min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    fields: list[TemplateFieldIn] = Field(min_length=1, max_length=40)


class AssignManagedQuestionnaire(BaseModel):
    template_key: str = Field(min_length=2, max_length=120)
    due_at: datetime | None = None


def _clean_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")
    if not key:
        raise HTTPException(422, "Identificador de pergunta inválido")
    return key[:60]


def _clean_fields(fields: list[TemplateFieldIn]) -> list[list]:
    result = []
    used = set()
    for item in fields:
        key = _clean_key(item.key)
        if key in used:
            raise HTTPException(422, f"Pergunta duplicada: {item.label}")
        used.add(key)
        field_type = item.type.strip().lower()
        if field_type not in ALLOWED_FIELD_TYPES:
            raise HTTPException(422, f"Tipo de campo não suportado: {item.type}")
        options = [str(x).strip()[:100] for x in item.options if str(x).strip()][:30]
        if field_type == "select" and len(options) < 2:
            raise HTTPException(422, f"A pergunta '{item.label}' precisa de pelo menos duas opções")
        result.append([key, item.label.strip(), field_type, bool(item.required), options])
    return result


def _builtin_templates() -> list[dict]:
    return [
        {
            "key": key,
            "title": value["title"],
            "category": value["category"],
            "description": "Modelo clínico padrão do NutriOS",
            "fields": [
                [field[0], field[1], field[2], False, []]
                for field in value["fields"]
            ],
            "builtin": True,
            "editable": False,
        }
        for key, value in clinical_extensions.QUESTIONNAIRES.items()
    ]


def _custom_templates(client_id: str) -> list[dict]:
    rows = business_store.list_rows(
        "questionnaire_templates",
        client_id,
        order="created_at.desc",
        extra={"active": "eq.true"},
    )
    for row in rows:
        row["key"] = f"custom:{row['id']}"
        row["builtin"] = False
        row["editable"] = True
    return rows


def _resolve_template(template_key: str, client_id: str) -> dict:
    if template_key.startswith("custom:"):
        row_id = template_key.split(":", 1)[1]
        row = business_store.get_row("questionnaire_templates", row_id, client_id)
        if not row or not row.get("active", True):
            raise HTTPException(404, "Modelo de formulário não encontrado")
        return {
            "key": template_key,
            "title": row["title"],
            "category": row.get("category") or "custom",
            "fields": row.get("fields") or [],
        }
    builtin = clinical_extensions.QUESTIONNAIRES.get(template_key)
    if not builtin:
        raise HTTPException(404, "Modelo de formulário não encontrado")
    return {"key": template_key, **builtin}


@router.get("/app/api/questionarios/modelos-gerenciaveis")
def managed_questionnaire_library(user: dict = Depends(auth.current_user)):
    return _builtin_templates() + _custom_templates(user["id"])


@router.post("/app/api/questionarios/modelos-gerenciaveis")
def create_questionnaire_template(payload: QuestionnaireTemplateIn, user: dict = Depends(auth.current_user)):
    fields = _clean_fields(payload.fields)
    return business_store.create_row("questionnaire_templates", user["id"], {
        "title": payload.title.strip(),
        "category": payload.category.strip().lower(),
        "description": (payload.description or "").strip() or None,
        "fields": fields,
        "active": True,
    })


@router.patch("/app/api/questionarios/modelos-gerenciaveis/{row_id}")
def update_questionnaire_template(row_id: str, payload: QuestionnaireTemplateIn, user: dict = Depends(auth.current_user)):
    row = business_store.get_row("questionnaire_templates", row_id, user["id"])
    if not row:
        raise HTTPException(404, "Modelo de formulário não encontrado")
    return business_store.update_row("questionnaire_templates", row_id, user["id"], {
        "title": payload.title.strip(),
        "category": payload.category.strip().lower(),
        "description": (payload.description or "").strip() or None,
        "fields": _clean_fields(payload.fields),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


@router.delete("/app/api/questionarios/modelos-gerenciaveis/{row_id}")
def delete_questionnaire_template(row_id: str, user: dict = Depends(auth.current_user)):
    row = business_store.get_row("questionnaire_templates", row_id, user["id"])
    if not row:
        raise HTTPException(404, "Modelo de formulário não encontrado")
    return business_store.update_row("questionnaire_templates", row_id, user["id"], {
        "active": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


@router.post("/app/api/pacientes/{patient_id}/questionarios-gerenciaveis")
def assign_managed_questionnaire(patient_id: str, payload: AssignManagedQuestionnaire, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    template = _resolve_template(payload.template_key, user["id"])
    return business_store.create_row("patient_questionnaires", user["id"], {
        "patient_id": patient_id,
        "template_key": payload.template_key,
        "title": template["title"],
        "category": template["category"],
        "schema_snapshot": template["fields"],
        "due_at": payload.due_at.isoformat() if payload.due_at else None,
    })
