"""Acesso seguro a documentos clínicos no Supabase Storage.

Nunca expõe o caminho interno como URL pública. Antes de emitir uma signed URL,
valida tenant + paciente + documento no Postgres.
"""
from __future__ import annotations

import os
from urllib.parse import quote

import requests
from fastapi import APIRouter, Depends, HTTPException

from app import auth, patient_auth, saas_store

router = APIRouter()
BUCKET = "patient-documents"
SIGNED_TTL = 300


def _signed_url(storage_path: str) -> str:
    if not saas_store.ATIVO:
        raise HTTPException(503, "Armazenamento não configurado")
    # O service key fica somente no backend. A resposta devolve apenas uma URL
    # assinada e temporária para o objeto já autorizado.
    response = requests.post(
        f"{saas_store.SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{quote(storage_path, safe='/')}",
        headers={"apikey": saas_store.SUPABASE_KEY, "Authorization": f"Bearer {saas_store.SUPABASE_KEY}"},
        json={"expiresIn": SIGNED_TTL},
        timeout=8,
    )
    if response.status_code >= 400:
        raise HTTPException(502, "Não foi possível gerar acesso temporário ao documento")
    data = response.json() if response.content else {}
    signed = data.get("signedURL") or data.get("signedUrl")
    if not signed:
        raise HTTPException(502, "Storage não retornou uma URL assinada")
    if signed.startswith("http"):
        return signed
    return f"{saas_store.SUPABASE_URL}/storage/v1{signed}"


def _document_for_client(document_id: str, client_id: str, patient_id: str | None = None) -> dict:
    params = {
        "select": "id,patient_id,client_id,storage_path,title,original_name,is_current",
        "id": f"eq.{document_id}",
        "client_id": f"eq.{client_id}",
        "limit": "1",
    }
    if patient_id:
        params["patient_id"] = f"eq.{patient_id}"
    rows = saas_store._request("GET", "patient_documents", params=params) or []
    if not rows:
        raise HTTPException(404, "Documento não encontrado")
    row = rows[0]
    path = row.get("storage_path") or ""
    # Defense in depth: clinical objects must live under the tenant/patient
    # prefix used by NutriOS. Reject legacy/malformed paths rather than
    # accidentally signing an arbitrary object path.
    expected_prefix = f"{client_id}/{row['patient_id']}/"
    if not path.startswith(expected_prefix):
        raise HTTPException(403, "Documento fora do escopo autorizado")
    return row


@router.get("/app/api/pacientes/{patient_id}/documentos/{document_id}/url-segura")
def secure_document_url(patient_id: str, document_id: str, user: dict = Depends(auth.current_user)):
    row = _document_for_client(document_id, user["id"], patient_id)
    return {
        "url": _signed_url(row["storage_path"]),
        "expires_in": SIGNED_TTL,
        "document_id": row["id"],
        "filename": row.get("original_name") or row.get("title") or "documento",
    }


@router.get("/paciente/api/documentos/{document_id}/url-segura")
def secure_patient_document_url(document_id: str, patient: dict = Depends(patient_auth.current_patient)):
    row = _document_for_client(document_id, patient["client_id"], patient["id"])
    return {
        "url": _signed_url(row["storage_path"]),
        "expires_in": SIGNED_TTL,
        "document_id": row["id"],
        "filename": row.get("original_name") or row.get("title") or "documento",
    }
