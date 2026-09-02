"""Manageable clinical form templates using the current organization-based NutriOS schema."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from app import auth, business_store, clinical_extensions, saas_store

router = clinical_extensions.router
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


def _organization_id(user_id: str) -> str:
    return business_store.organization_id_for_user(user_id)


def owned_patient(patient_id: str, user_id: str) -> dict:
    """Organization-safe patient lookup for all clinical_extensions routes."""
    organization_id = _organization_id(user_id)
    rows = saas_store._request(
        "GET",
        "patients",
        params={
            "select": "*",
            "id": f"eq.{patient_id}",
            "organization_id": f"eq.{organization_id}",
            "limit": "1",
        },
    ) or []
    if not rows:
        raise HTTPException(404, "Paciente não encontrado")
    return rows[0]


# clinical_extensions resolves this global at request time. Replacing it here fixes
# the legacy patient_accounts/client_id lookup without duplicating every route.
clinical_extensions.owned_patient = owned_patient


def _clean_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")
    if not key:
        raise HTTPException(422, "Identificador de pergunta inválido")
    return key[:60]


def _clean_fields(fields: list[TemplateFieldIn]) -> list[list]:
    result: list[list] = []
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


def _fields_for_template(template_id: str) -> list[list]:
    rows = saas_store._request(
        "GET",
        "clinical_form_fields",
        params={"select": "*", "template_id": f"eq.{template_id}", "order": "sort_order.asc"},
    ) or []
    result = []
    for index, row in enumerate(rows):
        options = row.get("options") or []
        key = _clean_key((row.get("label") or f"campo_{index + 1}"))
        result.append([key, row.get("label") or "Pergunta", row.get("field_type") or "text", bool(row.get("required")), options])
    return result


def _replace_fields(template_id: str, fields: list[list]) -> None:
    saas_store._request("DELETE", "clinical_form_fields", params={"template_id": f"eq.{template_id}"}, prefer="return=minimal")
    for position, field in enumerate(fields):
        saas_store._request(
            "POST",
            "clinical_form_fields",
            payload={
                "template_id": template_id,
                "label": field[1],
                "field_type": field[2],
                "options": field[4] if len(field) > 4 else [],
                "required": bool(field[3]) if len(field) > 3 else False,
                "sort_order": position,
            },
            prefer="return=minimal",
        )


def _builtin_templates() -> list[dict]:
    return [
        {
            "key": key,
            "title": value["title"],
            "category": value["category"],
            "description": "Modelo clínico padrão do NutriOS",
            "fields": [[field[0], field[1], field[2], False, []] for field in value["fields"]],
            "builtin": True,
            "editable": False,
        }
        for key, value in clinical_extensions.QUESTIONNAIRES.items()
    ]


def _custom_templates(user_id: str) -> list[dict]:
    organization_id = _organization_id(user_id)
    rows = business_store.list_org_rows(
        "clinical_form_templates",
        organization_id,
        order="created_at.desc",
        extra={"is_active": "eq.true", "kind": "like.custom:%"},
    )
    result = []
    for row in rows:
        category = (row.get("kind") or "custom:custom").split(":", 1)[-1] or "custom"
        result.append({
            **row,
            "key": f"custom:{row['id']}",
            "title": row.get("name") or "Formulário",
            "category": category,
            "fields": _fields_for_template(row["id"]),
            "builtin": False,
            "editable": True,
        })
    return result


def _materialize_builtin(template_key: str, user_id: str) -> dict:
    builtin = clinical_extensions.QUESTIONNAIRES.get(template_key)
    if not builtin:
        raise HTTPException(404, "Modelo de formulário não encontrado")
    organization_id = _organization_id(user_id)
    kind = f"builtin:{template_key}"
    rows = business_store.list_org_rows(
        "clinical_form_templates",
        organization_id,
        order="created_at.asc",
        extra={"kind": f"eq.{kind}", "is_active": "eq.true", "limit": "1"},
    )
    if rows:
        return rows[0]
    template = business_store.create_org_row("clinical_form_templates", organization_id, {
        "kind": kind,
        "name": builtin["title"],
        "description": "Modelo clínico padrão do NutriOS",
        "is_active": True,
        "created_by": user_id,
    })
    _replace_fields(template["id"], [[f[0], f[1], f[2], False, []] for f in builtin["fields"]])
    return template


def _resolve_template(template_key: str, user_id: str) -> dict:
    organization_id = _organization_id(user_id)
    if template_key.startswith("custom:"):
        row_id = template_key.split(":", 1)[1]
        row = business_store.get_org_row("clinical_form_templates", row_id, organization_id)
        if not row or not row.get("is_active", True):
            raise HTTPException(404, "Modelo de formulário não encontrado")
        return row
    return _materialize_builtin(template_key, user_id)


@router.get("/app/api/questionarios/modelos-gerenciaveis")
def managed_questionnaire_library(user: dict = Depends(auth.current_user)):
    return _builtin_templates() + _custom_templates(user["id"])


@router.post("/app/api/questionarios/modelos-gerenciaveis")
def create_questionnaire_template(payload: QuestionnaireTemplateIn, user: dict = Depends(auth.current_user)):
    organization_id = _organization_id(user["id"])
    fields = _clean_fields(payload.fields)
    template = business_store.create_org_row("clinical_form_templates", organization_id, {
        "kind": f"custom:{payload.category.strip().lower()}",
        "name": payload.title.strip(),
        "description": (payload.description or "").strip() or None,
        "is_active": True,
        "created_by": user["id"],
    })
    _replace_fields(template["id"], fields)
    return {
        **template,
        "key": f"custom:{template['id']}",
        "title": template["name"],
        "category": payload.category.strip().lower(),
        "fields": fields,
        "builtin": False,
        "editable": True,
    }


@router.patch("/app/api/questionarios/modelos-gerenciaveis/{row_id}")
def update_questionnaire_template(row_id: str, payload: QuestionnaireTemplateIn, user: dict = Depends(auth.current_user)):
    organization_id = _organization_id(user["id"])
    row = business_store.get_org_row("clinical_form_templates", row_id, organization_id)
    if not row or not str(row.get("kind") or "").startswith("custom:"):
        raise HTTPException(404, "Modelo de formulário não encontrado")
    fields = _clean_fields(payload.fields)
    updated = business_store.update_org_row("clinical_form_templates", row_id, organization_id, {
        "kind": f"custom:{payload.category.strip().lower()}",
        "name": payload.title.strip(),
        "description": (payload.description or "").strip() or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    _replace_fields(row_id, fields)
    return {**(updated or row), "key": f"custom:{row_id}", "title": payload.title.strip(), "category": payload.category.strip().lower(), "fields": fields, "builtin": False, "editable": True}


@router.delete("/app/api/questionarios/modelos-gerenciaveis/{row_id}")
def delete_questionnaire_template(row_id: str, user: dict = Depends(auth.current_user)):
    organization_id = _organization_id(user["id"])
    row = business_store.get_org_row("clinical_form_templates", row_id, organization_id)
    if not row or not str(row.get("kind") or "").startswith("custom:"):
        raise HTTPException(404, "Modelo de formulário não encontrado")
    return business_store.update_org_row("clinical_form_templates", row_id, organization_id, {
        "is_active": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


@router.post("/app/api/pacientes/{patient_id}/questionarios-gerenciaveis")
def assign_managed_questionnaire(patient_id: str, payload: AssignManagedQuestionnaire, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    organization_id = _organization_id(user["id"])
    template = _resolve_template(payload.template_key, user["id"])
    assignment = business_store.create_org_row("clinical_form_assignments", organization_id, {
        "template_id": template["id"],
        "patient_id": patient_id,
        "status": "pending",
        "due_at": payload.due_at.isoformat() if payload.due_at else None,
        "created_by": user["id"],
    })
    return {
        **assignment,
        "template_key": payload.template_key,
        "title": template.get("name") or "Formulário",
        "category": (template.get("kind") or "custom").split(":", 1)[-1],
        "schema_snapshot": _fields_for_template(template["id"]),
    }
