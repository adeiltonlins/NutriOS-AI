"""IA assistida para criar rascunhos no mesmo construtor de planos do NutriOS."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from google import genai

from app import auth, business_store, saas_store
from app.clinical_extensions import router, owned_patient

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")


class PlanAIRequest(BaseModel):
    calories_target: float | None = Field(default=None, ge=500, le=10000)
    meals_count: int = Field(default=5, ge=2, le=10)
    notes: str = Field(default="", max_length=5000)


SYSTEM = """Você é um assistente de apoio ao nutricionista. Gere APENAS um rascunho estruturado para revisão profissional.
Nunca diagnostique. Nunca invente alergias ou dados clínicos. Não transforme uma informação ausente em certeza.
Use alimentos brasileiros comuns. Restrições e preferências do paciente devem ser respeitadas.
A saída deve ser JSON válido, sem markdown, neste formato:
{"title":"...","objective":"...","professional_notes":"...","patient_notes":"...","content":[{"name":"Café da manhã","time":"07:00","items":[{"name":"...","grams":100,"substitutions":["...","..."]}]}]}
Não inclua food_id: o backend do construtor fará a validação/seleção dos alimentos.
"""


def _extract_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("A IA não retornou JSON válido")
    return json.loads(raw[start:end + 1])


def _generate(prompt: str) -> dict[str, Any]:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    last: Exception | None = None
    for model in [MODEL] + ([FALLBACK_MODEL] if FALLBACK_MODEL != MODEL else []):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={"system_instruction": SYSTEM, "response_mime_type": "application/json", "max_output_tokens": 5000},
            )
            if response.text:
                return _extract_json(response.text)
        except Exception as exc:
            last = exc
    raise HTTPException(502, f"Não foi possível gerar o rascunho com IA: {last or 'provedor indisponível'}")


def _patient(patient_id: str, client_id: str) -> dict:
    rows = saas_store._request("GET", "patient_accounts", params={"select":"*", "id":f"eq.{patient_id}", "client_id":f"eq.{client_id}", "limit":"1"}) or []
    if not rows:
        raise HTTPException(404, "Paciente não encontrado")
    return rows[0]


@router.post("/app/api/pacientes/{patient_id}/planos/ia-rascunho")
def generate_ai_plan(patient_id: str, payload: PlanAIRequest, user: dict = Depends(auth.current_user)):
    patient = _patient(patient_id, user["id"])
    prompt = {
        "paciente": {
            "nome": patient.get("name"),
            "objetivo": patient.get("energy_goal"),
            "contexto_dieta": patient.get("diet_context"),
            "metas_macro": patient.get("macro_targets") or {},
        },
        "consulta": payload.model_dump(),
    }
    pre = saas_store._request("GET", "preconsultation_forms", params={"select":"answers,summary", "patient_id":f"eq.{patient_id}", "client_id":f"eq.{user['id']}", "order":"created_at.desc", "limit":"1"}) or []
    notes = saas_store._request("GET", "consultation_notes", params={"select":"subjective,objective,assessment,plan", "patient_id":f"eq.{patient_id}", "client_id":f"eq.{user['id']}", "order":"created_at.desc", "limit":"1"}) or []
    prompt["pre_consulta"] = pre[0] if pre else {}
    prompt["registro_clinico"] = notes[0] if notes else {}
    draft = _generate(json.dumps(prompt, ensure_ascii=False, default=str))
    if not isinstance(draft.get("content"), list) or not draft["content"]:
        raise HTTPException(502, "A IA retornou um plano sem refeições")
    return {"draft": draft, "patient_id": patient_id, "builder_url": f"/app/pacientes/{patient_id}"}


@router.post("/app/api/pacientes/{patient_id}/planos/ia-rascunho/salvar")
def save_ai_plan(patient_id: str, payload: dict[str, Any], user: dict = Depends(auth.current_user)):
    _patient(patient_id, user["id"])
    draft = payload.get("draft") or {}
    content = draft.get("content") or []
    if not isinstance(content, list) or not content:
        raise HTTPException(400, "Rascunho inválido")
    # O construtor existente é a fonte de verdade: criamos um draft no mesmo meal_plans.
    # O cálculo/validação nutricional final continua no endpoint existente do construtor.
    row = business_store.create_row("meal_plans", user["id"], {
        "patient_id": patient_id,
        "title": str(draft.get("title") or "Rascunho assistido por IA")[:160],
        "objective": str(draft.get("objective") or "")[:1000],
        "content": content[:30],
        "totals": {},
        "professional_notes": str(draft.get("professional_notes") or "")[:5000],
        "patient_notes": str(draft.get("patient_notes") or "")[:5000],
        "status": "draft",
    })
    return {"plan": row, "builder_url": f"/app/pacientes/{patient_id}"}
