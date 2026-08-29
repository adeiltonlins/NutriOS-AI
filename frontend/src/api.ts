import type {
  AuthUser, Patient, MealPlan, WorkoutPlan, AnthropometryRecord,
  LabExamRecord, Appointment, PhytotherapyPrescription
} from './types';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const res = await fetch(url, { ...init, headers, credentials: 'same-origin', cache: 'no-store' });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data?.detail || data?.message || `Erro HTTP ${res.status}`);
  return data as T;
}

export const api = {
  me: () => request<any>('/api/me'),
  patientMe: () => request<any>('/paciente/api/me'),
  loginProfessional: (identifier: string, password: string) => request<{redirect:string}>('/auth/login', {method:'POST', body:JSON.stringify({identifier,password})}),
  loginProfessionalCode: (code: string) => request<{redirect:string}>('/auth/login', {method:'POST', body:JSON.stringify({code})}),
  loginPatient: (identifier: string, password: string) => request<{redirect:string}>('/paciente/auth/login', {method:'POST', body:JSON.stringify({identifier,password})}),
  loginPatientCode: (code: string) => request<{redirect:string}>('/paciente/auth/login', {method:'POST', body:JSON.stringify({code})}),
  logout: () => request('/auth/logout', {method:'POST'}),
  patientLogout: () => request('/paciente/auth/logout', {method:'POST'}),
  patients: () => request<any[]>('/app/api/pacientes'),
  createPatient: (payload:any) => request<any>('/app/api/pacientes', {method:'POST', body:JSON.stringify(payload)}),
  updatePatient: (id:string,payload:any) => request<any>(`/app/api/pacientes/${encodeURIComponent(id)}`, {method:'PATCH', body:JSON.stringify(payload)}),
  patientFollowup: (id:string) => request<any>(`/app/api/pacientes/${encodeURIComponent(id)}/acompanhamento`),
  dashboard: () => request<any>('/app/api/dashboard-clinico'),
  finance: () => request<any>('/app/api/financeiro'),
  foods: (q:string) => request<any[]>(`/app/api/alimentos?q=${encodeURIComponent(q)}`),
  createMealPlan: (patientId:string,payload:any) => request<any>(`/app/api/pacientes/${patientId}/planos`, {method:'POST', body:JSON.stringify(payload)}),
  approveMealPlan: (patientId:string,planId:string) => request<any>(`/app/api/pacientes/${patientId}/planos/${planId}/aprovar`, {method:'PATCH'}),
  createAnthropometry: (patientId:string,payload:any) => request<any>(`/app/api/pacientes/${patientId}/antropometria-avancada`, {method:'POST', body:JSON.stringify(payload)}),
  exams: (patientId:string) => request<any[]>(`/app/api/pacientes/${patientId}/exames`),
  createExam: (patientId:string,payload:any) => request<any>(`/app/api/pacientes/${patientId}/exames`, {method:'POST', body:JSON.stringify(payload)}),
  phytotherapy: (patientId:string) => request<any[]>(`/app/api/pacientes/${patientId}/fitoterapia`),
  createPhytotherapy: (patientId:string,payload:any) => request<any>(`/app/api/pacientes/${patientId}/fitoterapia`, {method:'POST', body:JSON.stringify(payload)}),
  workoutConfig: () => request<any>('/app/api/treinos/config'),
  workouts: (patientId?:string) => request<any[]>(`/app/api/treinos${patientId?`?patient_id=${encodeURIComponent(patientId)}`:''}`),
  createWorkout: (patientId:string,payload:any) => request<any>(`/app/api/pacientes/${patientId}/treinos`, {method:'POST', body:JSON.stringify(payload)}),
  publishWorkout: (planId:string) => request<any>(`/app/api/treinos/${planId}/publicar`, {method:'PATCH'}),
  copilot: (patientId:string,question:string) => request<any>(`/app/api/pacientes/${patientId}/copiloto`, {method:'POST', body:JSON.stringify({question})}),
  adminDashboard: () => request<any>('/admin/api/dashboard'),
  adminAudit: () => request<any[]>('/admin/api/audit'),
  patientPlan: () => request<any>('/paciente/api/plano'),
  patientWorkout: () => request<any>('/paciente/api/treino'),
  patientDocs: () => request<any[]>('/paciente/api/documentos'),
  patientCheckins: () => request<any[]>('/paciente/api/checkins'),
  patientExams: () => request<any[]>('/paciente/api/exames'),
  patientSupplements: () => request<any[]>('/paciente/api/suplementos'),
  patientPhyto: () => request<any[]>('/paciente/api/fitoterapia'),
};

const today = () => new Date().toISOString().slice(0,10);
export function mapAuthUser(raw:any): AuthUser {
  return {id:String(raw.id||''),name:raw.name||'Usuário',email:raw.identifier||raw.email||'',role:raw.role==='admin'?'super_admin':raw.role==='patient'?'patient':'nutritionist',avatar:raw.avatar||'',plan:raw.plan||undefined,clinicName:raw.clinic_name||raw.name,crn:raw.crn};
}
export function mapPatient(raw:any): Patient {
  return {id:String(raw.id),name:raw.name||'Paciente',email:raw.identifier||'',phone:raw.phone||'',avatar:'',age:Number(raw.age||0),gender:raw.sex==='male'?'masculino':raw.sex==='female'?'feminino':'outro',height:Number(raw.height_cm||0),weight:Number(raw.weight_kg||0),currentBf:Number(raw.body_fat_percent||0),goal:(raw.energy_goal||'Reeducação Alimentar') as any,status:raw.active?'ativo':'pendente',occupation:raw.occupation||'',birthDate:raw.birth_date||'',lastConsultation:raw.last_access_at||raw.updated_at||raw.created_at||today(),nextConsultation:undefined,notes:raw.diet_context||'',tags:[]};
}
export function mapMealPlan(raw:any, patientId:string): MealPlan {
  const content = Array.isArray(raw?.content)?raw.content:[];
  const meals = content.map((m:any,mi:number)=>({id:String(m.id||`meal-${mi}`),name:m.name||'Refeição',time:m.time||'',items:(m.items||[]).map((i:any,ii:number)=>({id:String(i.food_id||i.id||ii),name:i.name||'Alimento',portion:i.portion||`${i.grams||0} g`,grams:Number(i.grams||0),calories:Number(i.kcal||i.calories||0),protein:Number(i.proteina_g||i.protein||0),carbs:Number(i.carboidrato_g||i.carbs||0),fats:Number(i.lipideos_g||i.fats||0),fiber:Number(i.fibra_g||i.fiber||0),category:'Carboidratos' as any,substitutes:Array.isArray(i.substitutions)?i.substitutions.join(', '):i.substitutes}))}));
  const t=raw?.totals||{};
  return {id:String(raw?.id||`draft-${patientId}`),patientId,title:raw?.title||'Plano alimentar',status:raw?.status==='approved'?'ativo':'rascunho',dailyCalories:Number(t.kcal||raw?.dailyCalories||0),targetMacros:{protein:Number(t.proteina_g||0),carbs:Number(t.carboidrato_g||0),fats:Number(t.lipideos_g||0),fiber:Number(t.fibra_g||0)},meals,clinicalNotes:raw?.professional_notes||'',hydrationTargetMl:raw?.hydration_target_ml,createdAt:(raw?.created_at||today()).slice(0,10),updatedAt:(raw?.updated_at||raw?.created_at||today()).slice(0,10)};
}
export function mealPlanPayload(plan:MealPlan){return {title:plan.title,objective:'Plano nutricional individualizado',content:plan.meals.map(m=>({name:m.name,time:m.time,items:m.items.map(i=>({food_id:i.id,grams:i.grams,substitutions:i.substitutes?[i.substitutes]:[]}))})),professional_notes:plan.clinicalNotes,patient_notes:''};}
export function mapAppointment(raw:any): Appointment { const d=new Date(raw.starts_at||raw.date||Date.now()); return {id:String(raw.id),patientId:String(raw.patient_id||''),patientName:raw.patient_name||'Paciente',patientAvatar:'',patientPhone:raw.patient_phone||'',date:d.toISOString().slice(0,10),time:d.toTimeString().slice(0,5),type:'Presencial',status:raw.status==='completed'?'Concluída':raw.status==='cancelled'?'Cancelada':'Confirmada',reason:raw.notes||'Consulta'}; }
export function mapAnthropometry(raw:any): AnthropometryRecord {return {id:String(raw.id||raw.assessment_id),patientId:String(raw.patient_id),date:(raw.assessed_at||raw.created_at||today()).slice(0,10),weight:Number(raw.weight_kg||0),height:Number(raw.height_cm||0),bmi:Number(raw.bmi||0),protocol:'Bioimpedância',skinfolds:{},circumferences:{waist:Number(raw.waist_cm||0),hip:Number(raw.hip_cm||0)},bodyFatPercent:Number(raw.body_fat_percent||raw.calculated_body_fat_percent||0),fatMassKg:Number(raw.calculated_fat_mass_kg||0),leanMassKg:Number(raw.calculated_lean_mass_kg||0),boneResidualKg:0,bmrCalculated:0,tdeeCalculated:0,notes:raw.notes};}
export function mapLabRows(rows:any[],patientId:string): LabExamRecord[]{const byDate=new Map<string,any[]>();for(const r of rows){const d=r.collected_at||today();byDate.set(d,[...(byDate.get(d)||[]),r]);}return [...byDate].map(([date,items],idx)=>({id:`labs-${patientId}-${date}-${idx}`,patientId,date,title:'Exames laboratoriais',laboratory:'Registro clínico',biomarkers:items.map((x:any)=>({id:String(x.id),name:x.exam_name,value:Number(x.value_numeric||0),unit:x.unit||'',referenceMin:Number(x.reference_min||0),referenceMax:Number(x.reference_max||0),status:x.status==='low'?'low':x.status==='high'?'high':'normal',category:'Inflamação & Outros' as any}))}));}
export function mapPhyto(raw:any): PhytotherapyPrescription {return {id:String(raw.id),patientId:String(raw.patient_id),date:(raw.created_at||today()).slice(0,10),title:raw.title||'Fitoterapia',objective:raw.patient_notes||'',formulas:[{id:`f-${raw.id}`,name:raw.title||'Fórmula',form:(raw.pharmaceutical_form||'Cápsulas') as any,actives:(raw.items||[]).map((i:any)=>({substance:i.active_name,dosage:[i.concentration,i.dose].filter(Boolean).join(' • '),mechanism:i.notes||''})),posology:raw.usage_instructions||'',treatmentDuration:raw.duration_text||'',warnings:raw.professional_notes}],prescriberName:raw.signature_text||'Nutricionista'};}
