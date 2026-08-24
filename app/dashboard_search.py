"""Busca rápida de pacientes para o dashboard profissional."""
from __future__ import annotations

from fastapi import Depends, Query

from app import auth, clinical_extensions, patient_repository

router = clinical_extensions.router


@router.get("/app/api/pacientes")
def search_patients(
    q: str = Query(default="", max_length=80),
    user: dict = Depends(auth.require_nutritionist),
):
    rows = patient_repository.search_patients_for_client(user["id"], q, limit=8)
    return {"items": [patient_repository.serialize_patient_search_item(row) for row in rows]}
