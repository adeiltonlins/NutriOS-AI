"""IA assistida para criar rascunhos no mesmo construtor de planos do NutriOS."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from google import genai

from app import auth, business_store, saas_store
from app.clinical_extensions import router

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")
TACO = json.loads((Path(__file__).resolve().parents[1] / "data" / "alimentos_taco.json").read_text(encoding="utf-8"))


class PlanAIRequest(BaseModel):
    calories_target: float | None = Field(default=None, ge=500, le=10000)
    meals_count: int = Field(default=5, ge=2, le=10)
    notes: str = Field(default="", max_length=5000)


SYSTEM = """Você é um assistente de apoio ao nutricionista. Gere APENAS um rascunho estruturado para revisão profissional.
Nunca diagnostique. Nunca invente alergias ou dados clínicos. Não transforme uma informação ausente em certeza.
Use alimentos brasileiros comuns. Restrições e preferências do paciente devem ser respeitadas.
A saída deve ser JSON válido, sem markdown, neste formato:
{"title":"...","objective":"...","professional_notes":"...","patient_notes":"...","content":[{"name":"Café da manhã","time":"07:00","items":[{"name":"...","grams":100,"substitutions":["...","..."]}]}]}
Não inclua food_id: o backend normalizará os nomes para os alimentos existentes no construtor.
"""


def _norm(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(value).lower()) if not unicodedata.combining(c)).strip()


def _food(name: str) -> dict | None:
    target = _norm(name)
    if not target:
        return None
    exact = next((f for f in TACO if _norm(f.get("nome") or f.get("name")) == target), None)
    if exact:
        return exact
    return next((f for f in TACO if target in _norm(f.get("nome") or f.get("name")) or _norm(f.get("nome") or f.get("name")) in target), None)


def _normalize_content(content: list[dict]) -> tuple[list[dict], dict]:
    totals = {"kcal": 0.0, "proteina_g": 0.0, "carboidrato_g": 0.0, "lipideos_g": 0.0, "fibra_g": 0.0, "sodio_mg": 0.0}
    clean = []
    for meal in content[:30]:
        items = []
        for raw in list(meal.get("items") or [])[:20]:
            food = _food(raw.get("name"))
            if not food:
                continue
            grams = max(1.0, min(2000.0, float(raw.get("grams") or 0)))
            factor = grams / 100.0
            item = {"food_id": food["id"], "name": food.get("nome") or food.get("name"), "grams": grams, "source": food.get("source") or "taco", "substitutions": [str(x)[:120] for x in list(raw.get("substitutions") or [])[:8]]}
            for key in totals:
                item[key] = round(float(food.get(key) or 0) * factor, 2)
                totals[key] += item[key]
            items.append(item)
        if items:
            clean.append({"name": str(meal.get("name") or "Refeição")[:80], "time": str(meal.get("time") or "")[:20], "items": items})
    return clean, {k: round(v, 2) for k, v in totals.items()}


def _extract_json(text: str) -> dict[str, Any]:
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("A IA não retornou JSON válido")
    return json.loads(raw[start:end + 1])


def _generate(prompt: str) -> dict[str, Any]:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    last: Exception | None = None
    for model in [MODEL] + ([FALLBACK_MODEL] if FALLBACK_MODEL != MODEL else []):
        try:
            response = client.models.generate_content(model=model, contents=prompt, config={"system_instruction": SYSTEM, "response_mime_type": "application/json", "max_output_tokens": 5000})
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
    prompt = {"paciente":{"nome":patient.get("name"),"objetivo":patient.get("energy_goal"),"contexto_dieta":patient.get("diet_context"),"metas_macro":patient.get("macro_targets") or {}},"consulta":payload.model_dump()}
    pre = saas_store._request("GET", "preconsultation_forms", params={"select":"answers,summary", "patient_id":f"eq.{patient_id}", "client_id":f"eq.{user['id']}", "order":"created_at.desc", "limit":"1"}) or []
    notes = saas_store._request("GET", "consultation_notes", params={"select":"subjective,objective,assessment,plan", "patient_id":f"eq.{patient_id}", "client_id":f"eq.{user['id']}", "order":"created_at.desc", "limit":"1"}) or []
    prompt["pre_consulta"] = pre[0] if pre else {}
    prompt["registro_clinico"] = notes[0] if notes else {}
    draft = _generate(json.dumps(prompt, ensure_ascii=False, default=str))
    clean, totals = _normalize_content(draft.get("content") or [])
    if not clean:
        raise HTTPException(502, "A IA não retornou alimentos compatíveis com a biblioteca do construtor")
    draft["content"], draft["totals"] = clean, totals
    return {"draft":draft,"patient_id":patient_id,"builder_url":f"/app/pacientes/{patient_id}"}


@router.post("/app/api/pacientes/{patient_id}/planos/ia-rascunho/salvar")
def save_ai_plan(patient_id: str, payload: dict[str, Any], user: dict = Depends(auth.current_user)):
    _patient(patient_id, user["id"])
    draft = payload.get("draft") or {}
    content, totals = _normalize_content(draft.get("content") or [])
    if not content:
        raise HTTPException(400, "Rascunho sem alimentos válidos")
    row = business_store.create_row("meal_plans", user["id"], {"patient_id":patient_id,"title":str(draft.get("title") or "Rascunho assistido por IA")[:160],"objective":str(draft.get("objective") or "")[:1000],"content":content,"totals":totals,"professional_notes":str(draft.get("professional_notes") or "")[:5000],"patient_notes":str(draft.get("patient_notes") or "")[:5000],"status":"draft"})
    return {"plan":row,"builder_url":f"/app/pacientes/{patient_id}"}
