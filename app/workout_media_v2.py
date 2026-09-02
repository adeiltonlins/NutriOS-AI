from __future__ import annotations

import secrets
from urllib.parse import urlparse

from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import auth, clinical_extensions, patient_auth, saas_store

router = clinical_extensions.router


class ExerciseMediaIn(BaseModel):
    video_url: str | None = Field(default=None, max_length=1000)
    image_url: str | None = Field(default=None, max_length=1000)


def _org_id(user_id: str) -> str:
    rows = saas_store._request(
        "GET", "organization_members",
        params={"select": "organization_id", "user_id": f"eq.{user_id}", "limit": "1"},
    ) or []
    if not rows:
        raise HTTPException(409, "Conta sem organização clínica associada")
    return str(rows[0]["organization_id"])


def _valid_http_url(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(422, "Use um link http(s) válido")
    return value


def _owned_exercise(exercise_id: str, user_id: str) -> tuple[dict, dict]:
    org = _org_id(user_id)
    exercise = (saas_store._request(
        "GET", "workout_exercises",
        params={"select": "*", "id": f"eq.{exercise_id}", "limit": "1"},
    ) or [None])[0]
    if not exercise:
        raise HTTPException(404, "Exercício não encontrado")
    plan = (saas_store._request(
        "GET", "workout_plans",
        params={"select": "*", "id": f"eq.{exercise['workout_plan_id']}", "organization_id": f"eq.{org}", "limit": "1"},
    ) or [None])[0]
    if not plan:
        raise HTTPException(404, "Exercício não encontrado")
    return exercise, plan


@router.get("/app/api/treinos/exercicios-midias")
def list_exercise_media(user: dict = Depends(auth.current_user)):
    org = _org_id(str(user["id"]))
    plans = saas_store._request(
        "GET", "workout_plans",
        params={"select": "id,title,patient_id,status,updated_at", "organization_id": f"eq.{org}", "order": "updated_at.desc"},
    ) or []
    if not plans:
        return []
    by_id = {str(p["id"]): p for p in plans}
    ids = ",".join(by_id)
    rows = saas_store._request(
        "GET", "workout_exercises",
        params={
            "select": "id,workout_plan_id,day_label,day_name,exercise_name,sets,reps,load_text,rest_seconds,sort_order,notes,muscle_group,video_url,image_url,image_storage_path,image_mime_type",
            "workout_plan_id": f"in.({ids})",
            "order": "workout_plan_id.asc,sort_order.asc",
        },
    ) or []
    return [{**r, "plan": by_id.get(str(r["workout_plan_id"]))} for r in rows]


@router.patch("/app/api/treinos/exercicios/{exercise_id}/midia")
def update_exercise_media(exercise_id: str, payload: ExerciseMediaIn, user: dict = Depends(auth.current_user)):
    _owned_exercise(exercise_id, str(user["id"]))
    rows = saas_store._request(
        "PATCH", "workout_exercises", params={"id": f"eq.{exercise_id}"},
        payload={"video_url": _valid_http_url(payload.video_url), "image_url": _valid_http_url(payload.image_url)},
        prefer="return=representation",
    ) or []
    return rows[0] if rows else {}


@router.post("/app/api/treinos/exercicios/{exercise_id}/foto")
async def upload_exercise_photo(exercise_id: str, file: UploadFile = File(...), user: dict = Depends(auth.current_user)):
    exercise, plan = _owned_exercise(exercise_id, str(user["id"]))
    content = await file.read(8_000_001)
    mime = (file.content_type or "").lower()
    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
    if mime not in ext_map:
        raise HTTPException(400, "Envie JPG, PNG ou WebP")
    if len(content) > 8_000_000:
        raise HTTPException(413, "A imagem deve ter no máximo 8 MB")
    path = f"{plan['organization_id']}/workouts/{exercise_id}/{secrets.token_hex(16)}.{ext_map[mime]}"
    saas_store.upload_private_asset("patient-documents", path, content, mime)
    old = exercise.get("image_storage_path")
    rows = saas_store._request(
        "PATCH", "workout_exercises", params={"id": f"eq.{exercise_id}"},
        payload={"image_storage_path": path, "image_mime_type": mime, "image_url": None},
        prefer="return=representation",
    ) or []
    if old and old != path:
        try:
            saas_store.delete_private_asset("patient-documents", old)
        except Exception:
            pass
    return rows[0] if rows else {}


@router.get("/app/api/treinos/exercicios/{exercise_id}/foto")
def professional_exercise_photo(exercise_id: str, user: dict = Depends(auth.current_user)):
    exercise, _ = _owned_exercise(exercise_id, str(user["id"]))
    if not exercise.get("image_storage_path"):
        raise HTTPException(404, "Foto não cadastrada")
    return Response(
        saas_store.download_private_asset("patient-documents", exercise["image_storage_path"]),
        media_type=exercise.get("image_mime_type") or "image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/paciente/api/treino-midias")
def patient_workout_media(patient: dict = Depends(patient_auth.current_patient)):
    plans = saas_store._request(
        "GET", "workout_plans",
        params={"select": "*", "patient_id": f"eq.{patient['id']}", "status": "eq.published", "order": "updated_at.desc", "limit": "1"},
    ) or []
    if not plans:
        return {"plan": None, "exercises": []}
    plan = plans[0]
    exercises = saas_store._request(
        "GET", "workout_exercises",
        params={"select": "id,day_label,day_name,exercise_name,sets,reps,load_text,rest_seconds,sort_order,notes,muscle_group,video_url,image_url,image_storage_path,image_mime_type", "workout_plan_id": f"eq.{plan['id']}", "order": "sort_order.asc"},
    ) or []
    for row in exercises:
        if row.get("image_storage_path"):
            row["image_endpoint"] = f"/paciente/api/treino/exercicios/{row['id']}/foto"
    return {"plan": plan, "exercises": exercises}


@router.get("/paciente/api/treino/exercicios/{exercise_id}/foto")
def patient_exercise_photo(exercise_id: str, patient: dict = Depends(patient_auth.current_patient)):
    exercise = (saas_store._request("GET", "workout_exercises", params={"select": "*", "id": f"eq.{exercise_id}", "limit": "1"}) or [None])[0]
    if not exercise or not exercise.get("image_storage_path"):
        raise HTTPException(404, "Foto não encontrada")
    plans = saas_store._request(
        "GET", "workout_plans",
        params={"select": "id", "id": f"eq.{exercise['workout_plan_id']}", "patient_id": f"eq.{patient['id']}", "status": "eq.published", "limit": "1"},
    ) or []
    if not plans:
        raise HTTPException(404, "Foto não encontrada")
    return Response(
        saas_store.download_private_asset("patient-documents", exercise["image_storage_path"]),
        media_type=exercise.get("image_mime_type") or "image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )
