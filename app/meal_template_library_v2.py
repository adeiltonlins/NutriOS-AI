"""Biblioteca real de modelos de dieta para o frontend React.

Os modelos padrão são estruturais: definem quantidade/nome/horário de refeições,
mas não prescrevem alimentos nem quantidades automaticamente. O nutricionista
continua responsável por personalizar e revisar antes de publicar.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Query

from app import auth, clinical_extensions, saas_store

router = clinical_extensions.router

CATEGORY_ALIASES = {
    "emagrecimento": "emagrecimento",
    "hipertrofia": "hipertrofia",
    "manutencao": "manutencao",
    "manutenção": "manutencao",
    "vegetariano": "vegetariano",
    "vegano": "vegano",
    "diabetes": "diabetes",
    "hipertensao": "hipertensao",
    "hipertensão": "hipertensao",
    "outros": "outros",
}

DEFAULT_TEMPLATES = [
    {"name": "Emagrecimento · 4 refeições", "category": "emagrecimento", "meals": [("Café da manhã", "07:30"), ("Almoço", "12:30"), ("Lanche", "16:30"), ("Jantar", "20:00")]},
    {"name": "Emagrecimento · 5 refeições", "category": "emagrecimento", "meals": [("Café da manhã", "07:30"), ("Lanche da manhã", "10:00"), ("Almoço", "12:30"), ("Lanche", "16:30"), ("Jantar", "20:00")]},
    {"name": "Hipertrofia · 5 refeições", "category": "hipertrofia", "meals": [("Café da manhã", "07:00"), ("Lanche", "10:00"), ("Almoço", "12:30"), ("Pré/Pós-treino", "17:00"), ("Jantar", "20:30")]},
    {"name": "Hipertrofia · 6 refeições", "category": "hipertrofia", "meals": [("Café da manhã", "07:00"), ("Lanche da manhã", "10:00"), ("Almoço", "12:30"), ("Lanche da tarde", "15:30"), ("Pré/Pós-treino", "18:00"), ("Jantar/Ceia", "21:00")]},
    {"name": "Manutenção · 4 refeições", "category": "manutencao", "meals": [("Café da manhã", "07:30"), ("Almoço", "12:30"), ("Lanche", "16:30"), ("Jantar", "20:00")]},
    {"name": "Manutenção · 5 refeições", "category": "manutencao", "meals": [("Café da manhã", "07:30"), ("Lanche da manhã", "10:00"), ("Almoço", "12:30"), ("Lanche", "16:30"), ("Jantar", "20:00")]},
    {"name": "Vegetariano · 4 refeições", "category": "vegetariano", "meals": [("Café da manhã", "07:30"), ("Almoço", "12:30"), ("Lanche", "16:30"), ("Jantar", "20:00")]},
    {"name": "Vegetariano · 5 refeições", "category": "vegetariano", "meals": [("Café da manhã", "07:30"), ("Lanche da manhã", "10:00"), ("Almoço", "12:30"), ("Lanche", "16:30"), ("Jantar", "20:00")]},
    {"name": "Vegano · 4 refeições", "category": "vegano", "meals": [("Café da manhã", "07:30"), ("Almoço", "12:30"), ("Lanche", "16:30"), ("Jantar", "20:00")]},
    {"name": "Vegano · 5 refeições", "category": "vegano", "meals": [("Café da manhã", "07:30"), ("Lanche da manhã", "10:00"), ("Almoço", "12:30"), ("Lanche", "16:30"), ("Jantar", "20:00")]},
    {"name": "Diabetes · 5 refeições", "category": "diabetes", "meals": [("Café da manhã", "07:30"), ("Lanche da manhã", "10:00"), ("Almoço", "12:30"), ("Lanche", "16:00"), ("Jantar", "19:30")]},
    {"name": "Diabetes · 6 refeições", "category": "diabetes", "meals": [("Café da manhã", "07:00"), ("Lanche da manhã", "10:00"), ("Almoço", "12:30"), ("Lanche da tarde", "15:30"), ("Jantar", "19:00"), ("Ceia", "21:30")]},
    {"name": "Hipertensão · 5 refeições", "category": "hipertensao", "meals": [("Café da manhã", "07:30"), ("Lanche da manhã", "10:00"), ("Almoço", "12:30"), ("Lanche", "16:30"), ("Jantar", "20:00")]},
    {"name": "Hipertensão · 6 refeições", "category": "hipertensao", "meals": [("Café da manhã", "07:00"), ("Lanche da manhã", "10:00"), ("Almoço", "12:30"), ("Lanche da tarde", "15:30"), ("Jantar", "19:30"), ("Ceia", "21:30")]},
    {"name": "Outros · 4 refeições", "category": "outros", "meals": [("Café da manhã", "07:30"), ("Almoço", "12:30"), ("Lanche", "16:30"), ("Jantar", "20:00")]},
]


def _organization_id(user_id: str) -> str:
    rows = saas_store._request(
        "GET",
        "organization_members",
        params={"select": "organization_id", "user_id": f"eq.{user_id}", "limit": "1"},
    ) or []
    if not rows:
        raise HTTPException(409, "Conta sem organização clínica associada")
    return str(rows[0]["organization_id"])


def _normalize_category(value: str | None) -> str | None:
    if not value:
        return None
    key = str(value).strip().lower()
    return CATEGORY_ALIASES.get(key, key)


def _ensure_defaults(organization_id: str, user_id: str) -> None:
    existing = saas_store._request(
        "GET",
        "meal_plan_templates",
        params={
            "select": "id,name,category,is_archived",
            "organization_id": f"eq.{organization_id}",
        },
    ) or []
    existing_keys = {(str(row.get("name") or "").strip().lower(), _normalize_category(row.get("category"))) for row in existing}

    for spec in DEFAULT_TEMPLATES:
        key = (spec["name"].strip().lower(), spec["category"])
        if key in existing_keys:
            continue
        created = saas_store._request(
            "POST",
            "meal_plan_templates",
            payload={
                "organization_id": organization_id,
                "created_by": user_id,
                "name": spec["name"],
                "category": spec["category"],
                "notes": "Modelo estrutural NutriOS. Personalize alimentos, quantidades, macros e orientações antes de publicar.",
                "is_archived": False,
            },
            prefer="return=representation",
        ) or []
        if not created:
            continue
        template_id = created[0]["id"]
        payload = [
            {
                "template_id": template_id,
                "name": meal_name,
                "suggested_time": meal_time,
                "sort_order": index,
            }
            for index, (meal_name, meal_time) in enumerate(spec["meals"], start=1)
        ]
        if payload:
            saas_store._request("POST", "meal_plan_template_meals", payload=payload, prefer="return=minimal")


def _serialize_templates(organization_id: str, category: str | None) -> list[dict]:
    params = {
        "select": "id,name,category,notes,is_archived,created_at",
        "organization_id": f"eq.{organization_id}",
        "is_archived": "eq.false",
        "order": "category.asc,name.asc",
    }
    if category:
        params["category"] = f"eq.{category}"
    templates = saas_store._request("GET", "meal_plan_templates", params=params) or []
    if not templates:
        return []

    ids = [str(row["id"]) for row in templates]
    meals = saas_store._request(
        "GET",
        "meal_plan_template_meals",
        params={
            "select": "id,template_id,name,suggested_time,sort_order",
            "template_id": f"in.({','.join(ids)})",
            "order": "sort_order.asc",
        },
    ) or []
    by_template: dict[str, list[dict]] = {}
    for meal in meals:
        by_template.setdefault(str(meal["template_id"]), []).append(meal)

    return [
        {
            **row,
            "category": _normalize_category(row.get("category")),
            "meals": by_template.get(str(row["id"]), []),
            "meal_count": len(by_template.get(str(row["id"]), [])),
        }
        for row in templates
    ]


@router.get("/app/api/modelos-dieta-biblioteca")
def list_meal_template_library(
    categoria: str | None = Query(default=None, max_length=60),
    user: dict = Depends(auth.current_user),
):
    organization_id = _organization_id(str(user["id"]))
    _ensure_defaults(organization_id, str(user["id"]))
    category = _normalize_category(categoria)
    return {
        "category": category,
        "models": _serialize_templates(organization_id, category),
        "source": "meal_plan_templates",
    }
