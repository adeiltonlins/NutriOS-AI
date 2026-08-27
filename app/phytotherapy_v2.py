"""Fitoterapia/receituário V2, isolado por tenant e paciente."""
from __future__ import annotations
from datetime import date, datetime, timezone
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from app import auth, business_store, clinical_extensions

router = clinical_extensions.router
owned_patient = clinical_extensions.owned_patient

class PhytoItem(BaseModel):
    active_name: str = Field(min_length=2, max_length=180)
    concentration: str | None = Field(default=None, max_length=120)
    dose: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=500)

class PhytoPrescriptionIn(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    prescription_type: str = Field(default="phytotherapy", pattern=r"^(phytotherapy|formula)$")
    pharmaceutical_form: str | None = Field(default=None, max_length=120)
    quantity: str | None = Field(default=None, max_length=120)
    usage_instructions: str | None = Field(default=None, max_length=2000)
    duration_text: str | None = Field(default=None, max_length=240)
    professional_notes: str | None = Field(default=None, max_length=3000)
    patient_notes: str | None = Field(default=None, max_length=3000)
    signature_text: str | None = Field(default=None, max_length=300)
    status: str = Field(default="draft", pattern=r"^(draft|active|completed|cancelled)$")
    starts_at: date | None = None
    ends_at: date | None = None
    items: list[PhytoItem] = Field(default_factory=list, max_length=20)

class PhytoStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(draft|active|completed|cancelled)$")


def _row(row_id: str, patient_id: str, client_id: str) -> dict:
    row = business_store.get_row("patient_phytotherapy_prescriptions", row_id, client_id)
    if not row or row.get("patient_id") != patient_id:
        raise HTTPException(404, "Prescrição não encontrada")
    return row

@router.get("/app/api/pacientes/{patient_id}/fitoterapia")
def list_prescriptions(patient_id: str, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    rows = business_store.list_rows("patient_phytotherapy_prescriptions", user["id"], order="created_at.desc", extra={"patient_id": f"eq.{patient_id}"})
    for row in rows:
        row["items"] = business_store.list_rows("patient_phytotherapy_items", user["id"], order="sort_order.asc", extra={"patient_id": f"eq.{patient_id}", "prescription_id": f"eq.{row['id']}"})
    return rows

@router.post("/app/api/pacientes/{patient_id}/fitoterapia")
def create_prescription(patient_id: str, payload: PhytoPrescriptionIn, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"])
    data = payload.model_dump(mode="json", exclude={"items"}, exclude_none=True)
    data["patient_id"] = patient_id
    row = business_store.create_row("patient_phytotherapy_prescriptions", user["id"], data)
    for idx, item in enumerate(payload.items):
        d = item.model_dump(exclude_none=True)
        d.update({"patient_id": patient_id, "prescription_id": row["id"], "sort_order": idx})
        business_store.create_row("patient_phytotherapy_items", user["id"], d)
    business_store.audit(user["id"], user["id"], "phytotherapy.created", "patient_phytotherapy_prescription", row.get("id", ""), {"patient_id": patient_id, "items": len(payload.items)})
    row["items"] = [x.model_dump(exclude_none=True) for x in payload.items]
    return row

@router.patch("/app/api/pacientes/{patient_id}/fitoterapia/{row_id}/status")
def update_status(patient_id: str, row_id: str, payload: PhytoStatusUpdate, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"]); _row(row_id, patient_id, user["id"])
    row = business_store.update_row("patient_phytotherapy_prescriptions", row_id, user["id"], {"status": payload.status, "updated_at": datetime.now(timezone.utc).isoformat()})
    business_store.audit(user["id"], user["id"], "phytotherapy.status_updated", "patient_phytotherapy_prescription", row_id, {"patient_id": patient_id, "status": payload.status})
    return row

@router.delete("/app/api/pacientes/{patient_id}/fitoterapia/{row_id}", status_code=204)
def delete_prescription(patient_id: str, row_id: str, user: dict = Depends(auth.current_user)):
    owned_patient(patient_id, user["id"]); _row(row_id, patient_id, user["id"])
    business_store.delete_row("patient_phytotherapy_prescriptions", row_id, user["id"])
    business_store.audit(user["id"], user["id"], "phytotherapy.deleted", "patient_phytotherapy_prescription", row_id, {"patient_id": patient_id})
