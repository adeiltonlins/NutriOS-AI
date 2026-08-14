"""Módulos clínicos avançados, sempre isolados por client_id."""
from __future__ import annotations

import base64, hashlib, json, os, re, secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from app import auth, business_store, patient_auth, saas_store

router = APIRouter()
STATIC_DIR = Path(__file__).resolve().parent / "static"

QUESTIONNAIRES = {
 "metabolic": {"title":"Rastreamento metabólico","category":"metabolic","fields":[["energy","Energia ao longo do dia","scale"],["cravings","Compulsão ou desejos alimentares","scale"],["thirst","Sede excessiva","boolean"],["notes","Observações","text"]]},
 "gastro": {"title":"Sintomas gastrointestinais","category":"gastro","fields":[["bloating","Inchaço abdominal","scale"],["reflux","Refluxo ou azia","scale"],["bowel","Funcionamento intestinal","text"],["trigger","Alimentos associados","text"]]},
 "sleep": {"title":"Sono, estresse e rotina","category":"lifestyle","fields":[["sleep_hours","Horas de sono","number"],["sleep_quality","Qualidade do sono","scale"],["stress","Nível de estresse","scale"],["activity","Atividade física semanal","text"]]},
 "behavior": {"title":"Comportamento alimentar","category":"behavior","fields":[["emotional","Come por emoção","scale"],["hunger","Reconhece fome e saciedade","scale"],["episodes","Episódios de perda de controle","text"],["goals","Objetivos prioritários","text"]]},
 "maternal": {"title":"Gestação e lactação","category":"maternal","fields":[["week","Semana gestacional","number"],["nausea","Náuseas e aversões","text"],["supplements","Suplementos em uso","text"],["observation","Orientações médicas relevantes","text"]]},
}

PLAN_LIBRARY = [
 {"key":"balanced","title":"Base equilibrada","objective":"Manutenção e reeducação","meals":["Café da manhã","Almoço","Lanche","Jantar"]},
 {"key":"weight_loss","title":"Emagrecimento sustentável","objective":"Déficit energético com saciedade","meals":["Café da manhã","Almoço","Lanche","Jantar","Ceia opcional"]},
 {"key":"sports","title":"Performance esportiva","objective":"Periodização pré e pós-treino","meals":["Desjejum","Pré-treino","Pós-treino","Almoço","Lanche","Jantar"]},
 {"key":"vegetarian","title":"Vegetariano equilibrado","objective":"Distribuição proteica vegetal","meals":["Café da manhã","Almoço","Lanche","Jantar"]},
 {"key":"maternal","title":"Gestação - base de acompanhamento","objective":"Regularidade e densidade nutricional","meals":["Café da manhã","Lanche","Almoço","Lanche","Jantar","Ceia"]},
]

def owned_patient(patient_id: str, client_id: str) -> dict:
 rows = saas_store._request("GET","patient_accounts",params={"select":"*","id":f"eq.{patient_id}","client_id":f"eq.{client_id}","limit":"1"}) or []
 if not rows: raise HTTPException(404,"Paciente não encontrado")
 return rows[0]

def safe_image(file: UploadFile, content: bytes) -> str:
 mime = (file.content_type or "").lower()
 if mime not in {"image/jpeg","image/png","image/webp"}: raise HTTPException(400,"Envie JPG, PNG ou WebP")
 if len(content)>8_000_000: raise HTTPException(413,"A imagem deve ter no máximo 8 MB")
 signatures={"image/jpeg":b"\xff\xd8\xff","image/png":b"\x89PNG","image/webp":b"RIFF"}
 if not content.startswith(signatures[mime]): raise HTTPException(400,"Imagem inválida")
 return {"image/jpeg":"jpg","image/png":"png","image/webp":"webp"}[mime]

class FoodIn(BaseModel):
 name:str=Field(min_length=2,max_length=180); source:str="custom"; brand:str|None=None; household_measure:str|None=None; household_grams:float|None=Field(default=None,gt=0,le=5000); nutrients:dict[str,float]=Field(default_factory=dict)
class EquivalenceIn(BaseModel):
 source_food_ref:str; target_food_ref:str; source_grams:float=Field(gt=0,le=5000); target_grams:float=Field(gt=0,le=5000); notes:str|None=None
class AssignQuestionnaire(BaseModel): template_key:str; due_at:datetime|None=None
class QuestionnaireAnswers(BaseModel): answers:dict[str,Any]
class PatientFreeReport(BaseModel):
 text:str=Field(min_length=2,max_length=5000)
 mood:str|None=Field(default=None,max_length=80)
class MaternalIn(BaseModel):
 record_type:str; reference_date:str|None=None; gestational_week:float|None=None; pre_pregnancy_weight:float|None=None; current_weight:float|None=None; birth_date:str|None=None; sex:str|None=None; height_cm:float|None=None; head_circumference_cm:float|None=None; metrics:dict=Field(default_factory=dict); notes:str|None=None
class FinanceUpdate(BaseModel): status:str; payment_method:str|None=None; notes:str|None=None
class PeriodizationIn(BaseModel): schedule:dict=Field(default_factory=dict); periodization_notes:str|None=None

@router.get("/app/gestao-avancada")
def management_page(user:dict=Depends(auth.current_user)): return FileResponse(STATIC_DIR/"advanced-management.html",headers={"Cache-Control":"no-store"})
@router.get("/app/pacientes/{patient_id}/recursos")
def advanced_patient_page(patient_id:str,user:dict=Depends(auth.current_user)): owned_patient(patient_id,user["id"]); return FileResponse(STATIC_DIR/"advanced-clinical.html",headers={"Cache-Control":"no-store"})

@router.get("/app/api/biblioteca-planos")
def plan_library(user:dict=Depends(auth.current_user)): return PLAN_LIBRARY
@router.patch("/app/api/pacientes/{patient_id}/planos/{plan_id}/periodizacao")
def periodize_plan(patient_id:str,plan_id:str,payload:PeriodizationIn,user:dict=Depends(auth.current_user)):
 owned_patient(patient_id,user["id"]); row=business_store.get_row("meal_plans",plan_id,user["id"])
 if not row or row.get("patient_id")!=patient_id: raise HTTPException(404,"Plano não encontrado")
 return business_store.update_row("meal_plans",plan_id,user["id"],payload.model_dump())
@router.get("/app/api/questionarios/modelos")
def questionnaire_library(user:dict=Depends(auth.current_user)): return [{"key":k,**v} for k,v in QUESTIONNAIRES.items()]

@router.get("/app/api/alimentos-personalizados")
def foods(q:str="",user:dict=Depends(auth.current_user)):
 extra={"active":"eq.true"};
 if q.strip(): extra["name"]=f"ilike.*{q.strip()[:80]}*"
 return business_store.list_rows("custom_foods",user["id"],order="name.asc",extra=extra)
@router.post("/app/api/alimentos-personalizados")
def add_food(payload:FoodIn,user:dict=Depends(auth.current_user)):
 if payload.source not in {"custom","tbca","manufacturer"}: raise HTTPException(400,"Fonte inválida")
 nutrients={k:round(float(v),3) for k,v in payload.nutrients.items() if k in {"kcal","proteina_g","carboidrato_g","lipideos_g","fibra_g","sodio_mg"}}
 return business_store.create_row("custom_foods",user["id"],{**payload.model_dump(exclude={"nutrients"}),"nutrients":nutrients})
@router.delete("/app/api/alimentos-personalizados/{food_id}")
def remove_food(food_id:str,user:dict=Depends(auth.current_user)): return business_store.update_row("custom_foods",food_id,user["id"],{"active":False,"updated_at":datetime.now(timezone.utc).isoformat()})
@router.get("/app/api/equivalencias")
def equivalences(user:dict=Depends(auth.current_user)): return business_store.list_rows("food_equivalences",user["id"])
@router.post("/app/api/equivalencias")
def add_equivalence(payload:EquivalenceIn,user:dict=Depends(auth.current_user)): return business_store.create_row("food_equivalences",user["id"],payload.model_dump())

@router.get("/app/api/pacientes/{patient_id}/questionarios")
def patient_questionnaires(patient_id:str,user:dict=Depends(auth.current_user)): owned_patient(patient_id,user["id"]); return business_store.list_rows("patient_questionnaires",user["id"],extra={"patient_id":f"eq.{patient_id}"})
@router.post("/app/api/pacientes/{patient_id}/questionarios")
def assign_questionnaire(patient_id:str,payload:AssignQuestionnaire,user:dict=Depends(auth.current_user)):
 owned_patient(patient_id,user["id"]); template=QUESTIONNAIRES.get(payload.template_key)
 if not template: raise HTTPException(400,"Modelo inválido")
 return business_store.create_row("patient_questionnaires",user["id"],{"patient_id":patient_id,"template_key":payload.template_key,"title":template["title"],"category":template["category"],"schema_snapshot":template["fields"],"due_at":payload.due_at.isoformat() if payload.due_at else None})
@router.patch("/app/api/pacientes/{patient_id}/questionarios/{row_id}/revisar")
def review_questionnaire(patient_id:str,row_id:str,user:dict=Depends(auth.current_user)):
 owned_patient(patient_id,user["id"]); row=business_store.get_row("patient_questionnaires",row_id,user["id"])
 if not row or row.get("patient_id")!=patient_id: raise HTTPException(404,"Questionário não encontrado")
 return business_store.update_row("patient_questionnaires",row_id,user["id"],{"status":"reviewed","reviewed_at":datetime.now(timezone.utc).isoformat()})
@router.post("/paciente/api/relatos")
def create_patient_free_report(payload:PatientFreeReport,patient:dict=Depends(patient_auth.current_patient)):
 now=datetime.now(timezone.utc).isoformat()
 return business_store.create_row("patient_questionnaires",patient["client_id"],{
  "patient_id":patient["id"],"template_key":"patient_report","title":"Relato do paciente",
  "category":"patient_report","schema_snapshot":[["text","Relato","text"],["mood","Como está se sentindo","text"]],
  "answers":{"text":payload.text.strip(),"mood":(payload.mood or "").strip()},
  "status":"completed","completed_at":now,"updated_at":now
 })

@router.get("/paciente/api/questionarios")
def own_questionnaires(patient:dict=Depends(patient_auth.current_patient)): return saas_store._request("GET","patient_questionnaires",params={"select":"*","patient_id":f"eq.{patient['id']}","order":"created_at.desc"}) or []
@router.patch("/paciente/api/questionarios/{row_id}")
def answer_questionnaire(row_id:str,payload:QuestionnaireAnswers,patient:dict=Depends(patient_auth.current_patient)):
 rows=saas_store._request("PATCH","patient_questionnaires",params={"id":f"eq.{row_id}","patient_id":f"eq.{patient['id']}"},payload={"answers":payload.answers,"status":"completed","completed_at":datetime.now(timezone.utc).isoformat(),"updated_at":datetime.now(timezone.utc).isoformat()},prefer="return=representation") or []
 if not rows: raise HTTPException(404,"Questionário não encontrado")
 return rows[0]

@router.get("/app/api/pacientes/{patient_id}/materno-infantil")
def maternal_rows(patient_id:str,user:dict=Depends(auth.current_user)): owned_patient(patient_id,user["id"]); return business_store.list_rows("maternal_child_records",user["id"],order="reference_date.desc",extra={"patient_id":f"eq.{patient_id}"})
@router.post("/app/api/pacientes/{patient_id}/materno-infantil")
def maternal_add(patient_id:str,payload:MaternalIn,user:dict=Depends(auth.current_user)):
 owned_patient(patient_id,user["id"])
 if payload.record_type not in {"pregnancy","lactation","child","adolescent"}: raise HTTPException(400,"Modalidade inválida")
 return business_store.create_row("maternal_child_records",user["id"],{"patient_id":patient_id,**payload.model_dump(exclude_none=True)})

@router.post("/app/api/pacientes/{patient_id}/fotos-evolucao")
async def upload_progress(patient_id:str,view_type:str=Form("front"),captured_at:str=Form(""),notes:str=Form(""),file:UploadFile=File(...),user:dict=Depends(auth.current_user)):
 owned_patient(patient_id,user["id"]); content=await file.read(8_000_001); ext=safe_image(file,content)
 if view_type not in {"front","side","back","other"}: raise HTTPException(400,"Ângulo inválido")
 path=f"{user['id']}/{patient_id}/progress/{secrets.token_hex(16)}.{ext}"; saas_store.upload_private_asset("patient-documents",path,content,file.content_type)
 return business_store.create_row("patient_progress_photos",user["id"],{"patient_id":patient_id,"view_type":view_type,"captured_at":captured_at or datetime.now().date().isoformat(),"storage_path":path,"mime_type":file.content_type,"file_size":len(content),"notes":notes[:500]})
@router.get("/app/api/pacientes/{patient_id}/fotos-evolucao")
def progress_list(patient_id:str,user:dict=Depends(auth.current_user)): owned_patient(patient_id,user["id"]); return business_store.list_rows("patient_progress_photos",user["id"],order="captured_at.desc",extra={"patient_id":f"eq.{patient_id}"})
@router.get("/app/api/pacientes/{patient_id}/fotos-evolucao/{photo_id}")
def progress_image(patient_id:str,photo_id:str,user:dict=Depends(auth.current_user)):
 owned_patient(patient_id,user["id"]); row=business_store.get_row("patient_progress_photos",photo_id,user["id"])
 if not row or row["patient_id"]!=patient_id: raise HTTPException(404,"Foto não encontrada")
 return Response(saas_store.download_private_asset("patient-documents",row["storage_path"]),media_type=row["mime_type"],headers={"Cache-Control":"private, no-store"})

@router.post("/paciente/api/diario/foto")
async def diary_photo(meal_type:str=Form(...),description:str=Form(...),consumed_at:str=Form(""),file:UploadFile=File(...),patient:dict=Depends(patient_auth.current_patient)):
 content=await file.read(8_000_001); ext=safe_image(file,content); path=f"{patient['client_id']}/{patient['id']}/diary/{secrets.token_hex(16)}.{ext}"; saas_store.upload_private_asset("patient-documents",path,content,file.content_type)
 rows=saas_store._request("POST","food_diary_entries",payload={"patient_id":patient["id"],"client_id":patient["client_id"],"meal_type":meal_type[:60],"description":description[:2000],"consumed_at":consumed_at or datetime.now(timezone.utc).isoformat(),"photo_storage_path":path,"photo_mime_type":file.content_type,"photo_size":len(content)},prefer="return=representation") or []
 return rows[0]
@router.get("/app/api/pacientes/{patient_id}/diario/{entry_id}/foto")
def diary_image(patient_id:str,entry_id:str,user:dict=Depends(auth.current_user)):
 owned_patient(patient_id,user["id"]); row=business_store.get_row("food_diary_entries",entry_id,user["id"])
 if not row or row.get("patient_id")!=patient_id or not row.get("photo_storage_path"): raise HTTPException(404,"Foto não encontrada")
 return Response(saas_store.download_private_asset("patient-documents",row["photo_storage_path"]),media_type=row.get("photo_mime_type") or "image/jpeg",headers={"Cache-Control":"private, no-store"})

@router.get("/app/api/financeiro/resumo")
def finance_summary(months:int=Query(12,ge=1,le=36),user:dict=Depends(auth.current_user)):
 rows=business_store.list_rows("clinic_transactions",user["id"],order="created_at.desc"); series={}; categories={}; receivable=0.0
 for row in rows:
  amount=float(row.get("amount") or 0); month=str(row.get("competence_month") or row.get("paid_at") or row.get("due_at") or row.get("created_at") or "")[:7]; item=series.setdefault(month,{"income":0.0,"expense":0.0})
  if row.get("status")=="paid": item["income" if row.get("kind")=="income" else "expense"]+=amount
  elif row.get("kind")=="income" and row.get("status") in {"pending","overdue"}: receivable+=amount
  cat=str(row.get("category") or "Outros"); categories[cat]=categories.get(cat,0)+amount
 ordered=[{"month":k,**v,"balance":round(v["income"]-v["expense"],2)} for k,v in sorted(series.items())[-months:]]
 return {"series":ordered,"categories":categories,"receivable":round(receivable,2),"transactions":rows}
@router.patch("/app/api/financeiro/{row_id}")
def finance_update(row_id:str,payload:FinanceUpdate,user:dict=Depends(auth.current_user)):
 if payload.status not in {"pending","paid","overdue","cancelled"}: raise HTTPException(400,"Status inválido")
 data=payload.model_dump(exclude_none=True); data["paid_at"]=datetime.now(timezone.utc).isoformat() if payload.status=="paid" else None
 return business_store.update_row("clinic_transactions",row_id,user["id"],data)

def fernet()->Fernet:
 secret=os.getenv("CALENDAR_TOKEN_SECRET") or os.getenv("SESSION_SECRET") or ""
 if len(secret)<24: raise HTTPException(503,"Configure CALENDAR_TOKEN_SECRET")
 return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))
def google_config():
 cid=os.getenv("GOOGLE_CALENDAR_CLIENT_ID",""); csec=os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET",""); base=(os.getenv("URL_BASE") or "").rstrip("/")
 if not all((cid,csec,base)): raise HTTPException(503,"Google Agenda ainda não configurado")
 return cid,csec,f"{base}/app/api/google/callback"
@router.get("/app/api/google/status")
def google_status(user:dict=Depends(auth.current_user)):
 rows=business_store.list_rows("calendar_integrations",user["id"],extra={"limit":"1"}); return {"configured":bool(os.getenv("GOOGLE_CALENDAR_CLIENT_ID")),"connected":bool(rows and rows[0].get("refresh_token_encrypted")),"last_sync_at":rows[0].get("last_sync_at") if rows else None}
@router.get("/app/api/google/conectar")
def google_connect(request:Request,user:dict=Depends(auth.current_user)):
 cid,_,redirect=google_config(); expiry=int(datetime.now().timestamp())+600; raw=f"{user['id']}:{expiry}"; sig=hashlib.sha256((raw+(os.getenv('SESSION_SECRET') or '')).encode()).hexdigest(); state=base64.urlsafe_b64encode(f"{raw}:{sig}".encode()).decode()
 url="https://accounts.google.com/o/oauth2/v2/auth?"+httpx.QueryParams({"client_id":cid,"redirect_uri":redirect,"response_type":"code","scope":"https://www.googleapis.com/auth/calendar.events","access_type":"offline","prompt":"consent","state":state}).__str__(); return RedirectResponse(url)
@router.get("/app/api/google/callback")
async def google_callback(code:str,state:str):
 try: uid,expiry,sig=base64.urlsafe_b64decode(state).decode().split(":",2); raw=f"{uid}:{expiry}"; expected=hashlib.sha256((raw+(os.getenv('SESSION_SECRET') or '')).encode()).hexdigest()
 except Exception: raise HTTPException(400,"Estado inválido")
 if not secrets.compare_digest(sig,expected) or int(expiry)<int(datetime.now().timestamp()): raise HTTPException(400,"Autorização expirada")
 cid,csec,redirect=google_config()
 async with httpx.AsyncClient(timeout=20) as client: resp=await client.post("https://oauth2.googleapis.com/token",data={"code":code,"client_id":cid,"client_secret":csec,"redirect_uri":redirect,"grant_type":"authorization_code"})
 if resp.status_code!=200: raise HTTPException(400,"Google recusou a autorização")
 token=resp.json(); enc=fernet(); payload={"access_token_encrypted":enc.encrypt(token["access_token"].encode()).decode(),"refresh_token_encrypted":enc.encrypt(token.get("refresh_token","").encode()).decode(),"token_expires_at":(datetime.now(timezone.utc)+timedelta(seconds=int(token.get("expires_in",3600)))).isoformat(),"connected_at":datetime.now(timezone.utc).isoformat(),"updated_at":datetime.now(timezone.utc).isoformat()}
 rows=business_store.list_rows("calendar_integrations",uid,extra={"limit":"1"})
 if rows: business_store.update_row("calendar_integrations",rows[0]["id"],uid,payload)
 else: business_store.create_row("calendar_integrations",uid,payload)
 return RedirectResponse("/app/gestao-avancada?google=ok")

@router.post("/app/api/google/sincronizar")
async def google_sync(user:dict=Depends(auth.current_user)):
 rows=business_store.list_rows("calendar_integrations",user["id"],extra={"limit":"1"})
 if not rows or not rows[0].get("refresh_token_encrypted"): raise HTTPException(409,"Google Agenda não conectado")
 integration=rows[0]; cid,csec,_=google_config(); enc=fernet()
 async with httpx.AsyncClient(timeout=25) as client:
  token_response=await client.post("https://oauth2.googleapis.com/token",data={"client_id":cid,"client_secret":csec,"refresh_token":enc.decrypt(integration["refresh_token_encrypted"].encode()).decode(),"grant_type":"refresh_token"})
  if token_response.status_code!=200: raise HTTPException(502,"Não foi possível renovar a autorização do Google")
  access=token_response.json()["access_token"]; appointments=business_store.list_rows("appointments",user["id"],order="starts_at.asc",extra={"google_event_id":"is.null","status":"neq.cancelled","limit":"100"}); synced=0
  for row in appointments:
   start=str(row.get("starts_at") or "");
   if not start: continue
   try: start_dt=datetime.fromisoformat(start.replace("Z","+00:00")); end_dt=start_dt+timedelta(hours=1)
   except ValueError: continue
   event={"summary":f"Consulta - {row.get('patient_name') or 'Paciente'}","description":"Sincronizado pelo NutriOS","start":{"dateTime":start_dt.isoformat()},"end":{"dateTime":end_dt.isoformat()}}
   response=await client.post(f"https://www.googleapis.com/calendar/v3/calendars/{integration.get('calendar_id') or 'primary'}/events",headers={"Authorization":f"Bearer {access}"},json=event)
   if response.status_code in {200,201}: business_store.update_row("appointments",row["id"],user["id"],{"google_event_id":response.json().get("id")}); synced+=1
 business_store.update_row("calendar_integrations",integration["id"],user["id"],{"last_sync_at":datetime.now(timezone.utc).isoformat(),"updated_at":datetime.now(timezone.utc).isoformat()})
 return {"ok":True,"synced":synced}
