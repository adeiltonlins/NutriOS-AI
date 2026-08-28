"""Compatibility APIs for the AI Studio React interface.

These endpoints keep Gemini access on the FastAPI server, require an authenticated
professional session, validate patient ownership when a patient id is provided,
and never expose provider credentials to the browser.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Query
from google import genai
from google.genai import errors

from app import auth, business_store, clinical_extensions, llm, saas_store

router = clinical_extensions.router
owned_patient = clinical_extensions.owned_patient

_TACO_PATH = Path(__file__).resolve().parents[1] / "data" / "alimentos_taco.json"
try:
    _TACO_ROWS = json.loads(_TACO_PATH.read_text(encoding="utf-8"))
except Exception:
    _TACO_ROWS = []

def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()

def _resolve_taco_food(name: str) -> dict | None:
    needle = _norm(name)
    if not needle:
        return None
    exact = next((row for row in _TACO_ROWS if _norm(row.get("nome")) == needle), None)
    if exact:
        return exact
    tokens = {x for x in needle.split() if len(x) > 2}
    best = None
    best_score = 0.0
    for row in _TACO_ROWS:
        hay = _norm(row.get("nome"))
        if needle in hay or hay in needle:
            score = 10.0 + min(len(needle), len(hay)) / max(1, max(len(needle), len(hay)))
        else:
            htokens = {x for x in hay.split() if len(x) > 2}
            overlap = len(tokens & htokens)
            score = overlap / max(1, len(tokens | htokens))
        if score > best_score:
            best_score, best = score, row
    return best if best_score >= 0.34 else None

def _enrich_generated_diet(data: dict) -> dict:
    meals = data.get("meals") if isinstance(data.get("meals"), list) else []
    clean_meals = []
    for meal in meals[:10]:
        if not isinstance(meal, dict):
            continue
        clean_items = []
        for item in list(meal.get("items") or [])[:12]:
            if not isinstance(item, dict):
                continue
            food = _resolve_taco_food(str(item.get("name") or ""))
            if not food:
                continue
            try:
                grams = max(1.0, min(2000.0, float(item.get("grams") or 100)))
            except (TypeError, ValueError):
                grams = 100.0
            factor = grams / 100.0
            clean_items.append({
                **item,
                "food_id": str(food.get("id")),
                "name": food.get("nome"),
                "grams": grams,
                "portion": item.get("portion") or f"{grams:g} g",
                "calories": round(float(food.get("kcal") or 0) * factor, 1),
                "protein": round(float(food.get("proteina_g") or 0) * factor, 1),
                "carbs": round(float(food.get("carboidrato_g") or 0) * factor, 1),
                "fats": round(float(food.get("lipideos_g") or 0) * factor, 1),
                "fiber": round(float(food.get("fibra_g") or 0) * factor, 1),
            })
        if clean_items:
            clean_meals.append({**meal, "items": clean_items})
    data["meals"] = clean_meals
    return data


def _ensure_ai(user: dict) -> None:
    if (user.get("ai_config") or {}).get("ai_locked"):
        raise HTTPException(403, "A IA desta conta está temporariamente bloqueada pelo administrador")
    if not os.getenv("GEMINI_API_KEY") or os.getenv("IA_ATIVA", "true").lower() != "true":
        raise HTTPException(503, "IA não configurada neste ambiente")


def _patient_id(payload: dict) -> str | None:
    for key in ("patientData", "patientInfo", "patientContext"):
        value = payload.get(key)
        if isinstance(value, dict) and value.get("id"):
            return str(value["id"])
    value = payload.get("patient_id") or payload.get("patientId")
    return str(value) if value else None


def _validate_patient(payload: dict, user: dict) -> str | None:
    patient_id = _patient_id(payload)
    if patient_id:
        owned_patient(patient_id, user["id"])
    return patient_id


def _enrich_substitutions(data: dict) -> dict:
    clean = []
    for item in list(data.get("substitutions") or [])[:6]:
        if not isinstance(item, dict):
            continue
        food = _resolve_taco_food(str(item.get("name") or ""))
        if not food:
            continue
        try:
            grams = max(1.0, min(2000.0, float(item.get("grams") or 100)))
        except (TypeError, ValueError):
            grams = 100.0
        factor = grams / 100.0
        clean.append({
            **item,
            "food_id": str(food.get("id")),
            "name": food.get("nome"),
            "grams": grams,
            "portion": item.get("portion") or f"{grams:g} g",
            "calories": round(float(food.get("kcal") or 0) * factor, 1),
            "protein": round(float(food.get("proteina_g") or 0) * factor, 1),
            "carbs": round(float(food.get("carboidrato_g") or 0) * factor, 1),
            "fats": round(float(food.get("lipideos_g") or 0) * factor, 1),
            "fiber": round(float(food.get("fibra_g") or 0) * factor, 1),
        })
    data["substitutions"] = clean
    return data


def _generate_json(prompt: str, *, temperature: float = 0.2) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(503, "IA não configurada")
    client = genai.Client(api_key=api_key)
    models = [llm.MODEL] + ([llm.FALLBACK_MODEL] if llm.FALLBACK_MODEL and llm.FALLBACK_MODEL != llm.MODEL else [])
    last_error: Exception | None = None
    for model in models:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={"response_mime_type": "application/json", "temperature": temperature, "max_output_tokens": 3500},
            )
            text = str(response.text or "{}").strip()
            data = json.loads(text)
            if isinstance(data, dict):
                return data
            raise ValueError("Resposta JSON inválida")
        except Exception as exc:
            last_error = exc
            if isinstance(exc, errors.APIError) and exc.code in {400, 401, 403, 429}:
                break
    raise HTTPException(503, "IA temporariamente indisponível") from last_error


@router.post("/api/ai/generate-diet")
def react_generate_diet(payload: dict, user: dict = Depends(auth.current_user)):
    _ensure_ai(user); _validate_patient(payload, user)
    patient = payload.get("patientData") or {}
    macros = payload.get("targetMacros") or {}
    preferences = payload.get("preferences") or {}
    prompt = f"""Você é um copiloto de prescrição nutricional para um profissional autenticado no NutriOS.
Crie uma SUGESTÃO de plano alimentar para revisão profissional. Não diagnostique, não prescreva medicamentos e não trate a saída como conduta automática.
Use alimentos comuns no Brasil e quantidades plausíveis. Responda somente JSON válido.
Paciente: {json.dumps(patient, ensure_ascii=False)}
Meta calórica: {payload.get('targetCalories')}
Metas de macros: {json.dumps(macros, ensure_ascii=False)}
Restrições e observações: {json.dumps(preferences, ensure_ascii=False)}
Número de refeições: {payload.get('mealsCount') or 5}
Formato obrigatório:
{{"title":"Plano alimentar sugerido","dailyCalories":0,"macros":{{"protein":0,"carbs":0,"fats":0,"fiber":0}},"clinicalNotes":"Revisar e individualizar antes de publicar","meals":[{{"name":"Café da manhã","time":"07:30","items":[{{"name":"Alimento","portion":"porção","grams":0,"calories":0,"protein":0,"carbs":0,"fats":0,"fiber":0,"substitutes":"opção equivalente"}}]}}]}}"""
    data = _generate_json(prompt, temperature=0.25)
    data = _enrich_generated_diet(data)
    if not data.get("meals"):
        raise HTTPException(422, "A IA não conseguiu relacionar os alimentos sugeridos à base TACO. Ajuste as preferências e tente novamente.")
    return {"success": True, "data": data}


@router.post("/api/ai/substitute-food")
def react_substitute_food(payload: dict, user: dict = Depends(auth.current_user)):
    _ensure_ai(user); _validate_patient(payload, user)
    prompt = f"""Apoie um nutricionista na escolha de equivalentes alimentares. Não trate como prescrição automática.
Alimento atual: {payload.get('foodName')}; porção: {payload.get('portion')}; macros: {json.dumps(payload.get('currentMacros') or {}, ensure_ascii=False)}; motivo: {payload.get('reason') or ''}.
Retorne somente JSON: {{"originalFood":"...","substitutions":[{{"name":"...","portion":"...","calories":0,"protein":0,"carbs":0,"fats":0,"explanation":"..."}}]}}. Gere 3 opções."""
    data = _enrich_substitutions(_generate_json(prompt, temperature=0.2))
    return {"success": True, "data": data}


@router.post("/api/ai/analyze-exam")
def react_analyze_exam(payload: dict, user: dict = Depends(auth.current_user)):
    _ensure_ai(user); _validate_patient(payload, user)
    prompt = f"""Você é um copiloto clínico para nutricionista. Organize os exames abaixo sem emitir diagnóstico médico.
Diferencie valor registrado de inferência, sinalize somente pontos para revisão profissional e nunca sugira alteração de medicamento.
Paciente: {json.dumps(payload.get('patientInfo') or {}, ensure_ascii=False)}
Exames: {json.dumps(payload.get('examsList') or [], ensure_ascii=False)}
Retorne JSON: {{"overallAssessment":"resumo objetivo","abnormalBiomarkers":[{{"name":"...","value":"...","referenceRange":"...","status":"elevado|baixo|limítrofe","nutritionalImpact":"ponto para revisão","dietaryRecommendation":"possibilidade alimentar para avaliação profissional"}}],"suggestedNutrientsAndPhytotherapy":[],"followUpExamRecommendations":[]}}."""
    return {"success": True, "data": _generate_json(prompt, temperature=0.15)}


@router.post("/api/ai/generate-phytotherapy")
def react_generate_phytotherapy(payload: dict, user: dict = Depends(auth.current_user)):
    _ensure_ai(user); _validate_patient(payload, user)
    prompt = f"""Você apoia um nutricionista habilitado. Gere apenas um RASCUNHO de organização de fitoterapia para revisão do profissional conforme sua habilitação e legislação aplicável.
Não use linguagem de diagnóstico, não inclua medicamento de prescrição e destaque contraindicações/necessidade de revisão.
Objetivo informado: {payload.get('clinicalObjective') or ''}
Dados: {json.dumps(payload, ensure_ascii=False)}
Retorne JSON: {{"title":"Rascunho para revisão","clinicalObjective":"...","formulas":[{{"name":"...","form":"Cápsulas","actives":[{{"substance":"...","dosage":"...","mechanism":"..."}}],"posology":"...","treatmentDuration":"...","warnings":"Revisar contraindicações, interações e limites profissionais antes de liberar"}}],"dietarySynergy":"...","expectedOutcomes":"..."}}."""
    data = _generate_json(prompt, temperature=0.2)
    return {"success": True, "data": data, "prescription": data}


@router.post("/api/ai/analyze-msq")
def react_analyze_msq(payload: dict, user: dict = Depends(auth.current_user)):
    _ensure_ai(user); _validate_patient(payload, user)
    prompt = f"""Interprete o questionário MSQ apenas como instrumento de triagem nutricional, sem diagnóstico médico.
Dados: {json.dumps(payload, ensure_ascii=False)}
Retorne JSON: {{"riskLevel":"Baixo|Moderado|Alto","summary":"...","primaryOrgansAffected":[],"priorityInterventions":[],"recommendedNutritionalTactics":[]}}. Use linguagem de pontos para revisão profissional."""
    data = _generate_json(prompt, temperature=0.15)
    return {"success": True, "data": data, "analysis": data}


@router.post("/api/ai/analyze-patient")
def react_analyze_patient(payload: dict, user: dict = Depends(auth.current_user)):
    _ensure_ai(user); _validate_patient(payload, user)
    prompt = f"""Organize os dados deste paciente para apoiar a revisão do nutricionista. Não faça diagnóstico médico e não altere condutas automaticamente.
{json.dumps(payload, ensure_ascii=False)}
Retorne JSON: {{"summary":"...","metabolicStatus":"...","identifiedRisks":[],"recommendedStrategy":"pontos para revisão profissional","supplementationSuggestions":[],"lifestyleTips":[]}}."""
    return {"success": True, "data": _generate_json(prompt, temperature=0.2)}


@router.post("/app/api/alimentos-personalizados")
def react_create_custom_food(payload: dict, user: dict = Depends(auth.current_user)):
    name = str(payload.get("name") or "").strip()
    if len(name) < 2 or len(name) > 180:
        raise HTTPException(422, "Nome do alimento inválido")
    def clamp(key: str, maximum: float = 100000.0) -> float:
        try:
            return max(0.0, min(maximum, float(payload.get(key) or 0)))
        except (TypeError, ValueError):
            raise HTTPException(422, f"Valor inválido em {key}")
    nutrients = {
        "porcao_g": max(1.0, clamp("standardGrams", 2000.0) or 100.0),
        "kcal": clamp("calories", 2000.0),
        "proteina_g": clamp("protein", 200.0),
        "carboidrato_g": clamp("carbs", 300.0),
        "lipideos_g": clamp("fats", 200.0),
        "fibra_g": clamp("fiber", 100.0),
        "sodio_mg": clamp("sodiumMg", 100000.0),
    }
    row = business_store.create_row("custom_foods", user["id"], {
        "name": name,
        "source": "professional",
        "nutrients": nutrients,
        "active": True,
    })
    business_store.audit(user["id"], user["id"], "custom_food.created", "custom_food", str(row.get("id") or ""), {"name": name})
    return {"id": f"custom:{row.get('id')}", "nome": name, "source": "professional", **nutrients}


@router.get("/app/api/react/alimentos")
def react_food_catalog(q: str = Query(default="", max_length=80), user: dict = Depends(auth.current_user)):
    needle = _norm(q)
    found: list[dict] = []
    for food in _TACO_ROWS:
        if needle and needle not in _norm(food.get("nome")):
            continue
        found.append(food)
        if len(found) >= 60:
            break
    try:
        extra = {"active": "eq.true", "limit": "30"}
        if q.strip():
            extra["name"] = f"ilike.*{q.strip()}*"
        custom = business_store.list_rows("custom_foods", user["id"], order="name.asc", extra=extra)
    except Exception:
        custom = []
    for food in custom:
        found.append({"id": f"custom:{food['id']}", "nome": food.get("name"), "source": food.get("source"), **(food.get("nutrients") or {})})
    return found[:80]


@router.get("/admin/api/react/overview")
def react_admin_overview(admin: dict = Depends(auth.require_admin)):
    now = datetime.now(timezone.utc)
    month_key = now.strftime("%Y-%m")
    try:
        transactions = saas_store._request("GET", "clinic_transactions", params={"select": "client_id,amount,status,kind,paid_at,created_at", "limit": "10000"}) or []
    except Exception:
        transactions = []
    try:
        appointments = saas_store._request("GET", "appointments", params={"select": "client_id,status,starts_at,created_at", "limit": "10000"}) or []
    except Exception:
        appointments = []
    clients = [u for u in saas_store.list_users() if u.get("role") == "client" and not u.get("archived_at")]
    ranking = []
    total_revenue = 0.0
    for client in clients:
        client_id = str(client.get("id"))
        paid_income = [r for r in transactions if str(r.get("client_id")) == client_id and r.get("status") == "paid" and r.get("kind") == "income" and str(r.get("paid_at") or r.get("created_at") or "")[:7] == month_key]
        revenue = round(sum(float(r.get("amount") or 0) for r in paid_income), 2)
        consults = [a for a in appointments if str(a.get("client_id")) == client_id and str(a.get("starts_at") or a.get("created_at") or "")[:7] == month_key and str(a.get("status") or "").lower() not in {"cancelled", "canceled", "cancelada"}]
        patients = 0
        try:
            patients = len(saas_store._request("GET", "patient_accounts", params={"select": "id", "client_id": f"eq.{client_id}", "active": "eq.true", "archived_at": "is.null", "hidden_at": "is.null", "limit": "10000"}) or [])
        except Exception:
            patients = 0
        total_revenue += revenue
        config = client.get("ai_config") or {}
        ranking.append({
            "id": client_id,
            "name": client.get("name") or "Nutricionista",
            "clinic": config.get("nome") or client.get("name") or "Clínica",
            "avatar": config.get("photo_url") or config.get("logo_url") or "",
            "monthly_revenue": revenue,
            "consultations": len(consults),
            "active_patients": patients,
            "average_ticket": round(revenue / len(paid_income), 2) if paid_income else 0.0,
            "plan": client.get("plan") or "starter",
        })
    ranking.sort(key=lambda row: (row["monthly_revenue"], row["active_patients"]), reverse=True)
    return {"month": month_key, "clinic_revenue_month": round(total_revenue, 2), "ranking": ranking}
