"""Patient-facing, read-only clinical data endpoints.

Exposes only fields intended for the authenticated patient. Every query is
scoped by both patient_id and client_id from the patient session.
"""
from __future__ import annotations

from fastapi import Depends

from app import clinical_extensions, patient_auth, saas_store

router = clinical_extensions.router


@router.get("/paciente/api/exames")
def patient_lab_exams(patient: dict = Depends(patient_auth.current_patient)):
    return saas_store._request(
        "GET",
        "patient_lab_exams",
        params={
            "select": "id,exam_name,category,collected_at,value_numeric,value_text,unit,reference_min,reference_max,reference_text,status,created_at",
            "patient_id": f"eq.{patient['id']}",
            "client_id": f"eq.{patient['client_id']}",
            "order": "collected_at.desc,created_at.desc",
            "limit": "200",
        },
    ) or []


@router.get("/paciente/api/fitoterapia")
def patient_phytotherapy(patient: dict = Depends(patient_auth.current_patient)):
    prescriptions = saas_store._request(
        "GET",
        "patient_phytotherapy_prescriptions",
        params={
            "select": "id,title,prescription_type,pharmaceutical_form,quantity,usage_instructions,duration_text,patient_notes,signature_text,status,starts_at,ends_at,created_at",
            "patient_id": f"eq.{patient['id']}",
            "client_id": f"eq.{patient['client_id']}",
            "status": "in.(active,completed)",
            "order": "created_at.desc",
            "limit": "100",
        },
    ) or []
    for prescription in prescriptions:
        prescription["items"] = saas_store._request(
            "GET",
            "patient_phytotherapy_items",
            params={
                "select": "id,active_name,concentration,dose,notes,sort_order",
                "prescription_id": f"eq.{prescription['id']}",
                "patient_id": f"eq.{patient['id']}",
                "client_id": f"eq.{patient['client_id']}",
                "order": "sort_order.asc",
            },
        ) or []
    return prescriptions
