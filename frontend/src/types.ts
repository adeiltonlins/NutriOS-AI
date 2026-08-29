export type Gender = 'masculino' | 'feminino' | 'outro';
export type PatientGoal = 
  | 'Hipertrofia Muscular' 
  | 'Emagrecimento & Queima de Gordura' 
  | 'Reeducação Alimentar' 
  | 'Performance Esportiva' 
  | 'Manejo Clínico (Diabetes/Hipertensão/SOP)' 
  | 'Longevidade & Saúde Funcional';

export type PatientStatus = 'ativo' | 'em_acompanhamento' | 'alta' | 'pendente';

export interface Patient {
  id: string;
  name: string;
  email: string;
  phone: string;
  avatar: string;
  age: number;
  gender: Gender;
  height: number;
  weight: number;
  currentBf: number;
  goal: PatientGoal;
  status: PatientStatus;
  occupation: string;
  birthDate: string;
  lastConsultation: string;
  nextConsultation?: string;
  notes: string;
  tags: string[];
}

export interface Anamnesis {
  patientId: string;
  sleepHours: number;
  sleepQuality: 'Excelente' | 'Boa' | 'Regular' | 'Ruim';
  bowelHabits: 'Diário regular' | 'Obstipado' | 'Irregular' | 'Diarreico';
  hydrationLiters: number;
  alcoholConsumption: 'Nunca' | 'Ocasional (fim de semana)' | 'Moderado' | 'Frequente';
  smoking: boolean;
  allergiesAndIntolerances: string[];
  foodAversions: string[];
  favoriteFoods: string[];
  mealsPerDay: number;
  cookingHabit: 'Cozinha a própria comida' | 'Come fora/Restaurante' | 'Delivery frequente' | 'Marmitas congeladas';
  physicalActivity: { modality: string; frequencyPerWeek: number; durationMinutes: number; intensity: 'Leve' | 'Moderada' | 'Alta' | 'Muito Alta'; };
  clinicalHistory: string[];
  familyHistory: string[];
  currentMedications: string[];
  currentSupplements: string[];
  stressLevel: 'Baixo' | 'Moderado' | 'Alto' | 'Muito Alto';
}

export interface SkinfoldMeasurements { triceps?: number; subscapular?: number; suprailiac?: number; abdominal?: number; chest?: number; axillary?: number; thigh?: number; calf?: number; }
export interface CircumferenceMeasurements { neck?: number; chest?: number; waist?: number; abdomen?: number; hip?: number; rightArmRelaxed?: number; rightArmContracted?: number; leftArmRelaxed?: number; leftArmContracted?: number; rightThigh?: number; leftThigh?: number; rightCalf?: number; leftCalf?: number; }

export interface AnthropometryRecord {
  id: string; patientId: string; date: string; weight: number; height: number; bmi: number;
  protocol: 'Pollock 3 Dobras' | 'Pollock 7 Dobras' | 'Faulkner 4 Dobras' | 'Bioimpedância';
  skinfolds: SkinfoldMeasurements; circumferences: CircumferenceMeasurements; bodyFatPercent: number; fatMassKg: number; leanMassKg: number; boneResidualKg: number; visceralFatRating?: number; bmrCalculated: number; tdeeCalculated: number;
  photos?: { front?: string; back?: string; rightSide?: string; leftSide?: string; side?: string; date?: string; notes?: string; };
  postureAssessment?: { shoulderSymmetry: 'Simétrico' | 'Ombro D Elevado' | 'Ombro E Elevado'; pelvicTilt: 'Neutro' | 'Anteversão Pélvica' | 'Retroversão Pélvica'; headPosition: 'Alinhado' | 'Projeção Anterior'; spinalCurvature: 'Normal' | 'Hipercifose Torácica' | 'Hiperlordose Lombar' | 'Escoliose Leve'; evolutionScorePercent: number; };
  notes?: string;
}

export interface WorkoutExercise { id:string; name:string; muscleGroup:'Peitoral'|'Costas & Dorsal'|'Quadríceps'|'Posterior & Glúteo'|'Deltoides & Ombros'|'Bíceps'|'Tríceps'|'Abdômen & Core'|'Panturrilha'|'Cárdio'; sets:number; reps:string; loadKg?:number; restSeconds:number; rpe?:number; videoUrl?:string; notes?:string; }
export interface WorkoutDay { id:string; letter:string; dayName:string; focus:string; exercises:WorkoutExercise[]; cardioMinutes?:number; cardioType?:string; cardioIntensity?:'Leve (Z2)'|'Moderado (Z3)'|'Intenso / HIIT (Z4-Z5)'; notes?:string; }
export interface WorkoutPlan { id:string; patientId:string; isEnabled:boolean; title:string; objective:PatientGoal|string; level:'Iniciante'|'Intermediário'|'Avançado'|'Atleta'; frequencyDaysPerWeek:number; workoutDays:WorkoutDay[]; generalInstructions:string; videoTutorialUrl?:string; createdAt:string; updatedAt:string; }

export interface MealItem { id:string; name:string; portion:string; grams:number; calories:number; protein:number; carbs:number; fats:number; fiber:number; category:'Proteínas'|'Carboidratos'|'Gorduras Boas'|'Frutas'|'Vegetais & Saladas'|'Laticínios'|'Suplementos'|'Bebidas'; substitutes?:string; photoUrl?:string; }
export interface Meal { id:string; name:string; time:string; image?:string; items:MealItem[]; tips?:string; }
export interface MealPlan { id:string; patientId:string; title:string; status:'ativo'|'rascunho'|'arquivado'; dailyCalories:number; targetMacros:{protein:number;carbs:number;fats:number;fiber:number}; meals:Meal[]; clinicalNotes:string; hydrationPrescription?:number; hydrationTargetMl?:number; supplementationProtocol?:{name:string;dosage:string;timing:string;instructions?:string}[]; supplements?:{name:string;dosage:string;timing:string;instructions?:string}[]; createdAt:string; updatedAt:string; }

export interface Biomarker { id:string; name:string; value:number; unit:string; referenceMin:number; referenceMax:number; optimalMin?:number; optimalMax?:number; status:'normal'|'low'|'high'|'borderline'; category:'Glicemia & Insulina'|'Perfil Lipídico'|'Vitaminas & Minerais'|'Hormônios & Tireoide'|'Função Hepática'|'Inflamação & Outros'; interpretation?:string; }
export interface LabExamRecord { id:string; patientId:string; date:string; title:string; laboratory:string; biomarkers:Biomarker[]; aiAnalysis?:{overallAssessment:string;abnormalCount:number;highlights:string[];suggestedNutrients:string[]}; }
export interface Appointment { id:string; patientId:string; patientName:string; patientAvatar:string; patientPhone:string; date:string; time:string; type:'Presencial'|'Online (Teleconsulta)'|'presencial'|'online_video'; status:'Confirmada'|'Pendente'|'Concluída'|'Cancelada'|'confirmada'|'agendada'|'realizada'; reason?:'Primeira Consulta'|'Retorno / Reavaliação'|'Ajuste de Cardápio'|'Emergencial'|string; telehealthUrl?:string; notes?:string; }
export interface ChatMessage { id:string; role:'user'|'assistant'|'system'; content:string; timestamp:string; }
export interface FoodDatabaseItem { id:string; name:string; category:MealItem['category']; portionDescription:string; standardGrams:number; calories:number; protein:number; carbs:number; fats:number; fiber:number; sodiumMg:number; ironMg:number; calciumMg:number; photoUrl:string; }

export type UserRole='super_admin'|'nutritionist'|'patient';
export type SaaSPlanTier='starter'|'pro'|'enterprise';
export interface AuthUser { id:string; name:string; email:string; role:UserRole; avatar:string; plan?:SaaSPlanTier; clinicName?:string; crn?:string; }
export type SaaSUserStatus='active'|'trial'|'suspended'|'paused'|'blocked'|'canceled';
export interface SaaSUser { id:string; name:string; email:string; crn:string; clinicName:string; avatar:string; role:UserRole; plan:SaaSPlanTier; status:SaaSUserStatus; statusReason?:string; patientsCount:number; mrrValue:number; tokensUsedThisMonth:number; tokenQuotaMonthly:number; dailyTokenLimit:number; extraTokensPurchased:number; tokenOverdraftPolicy:'block'|'charge_extra'|'downgrade_to_flash'; isAiLocked:boolean; autoReplyEnabled?:boolean; autoReplyTokenQuota?:number; autoReplyTokensUsed?:number; autoReplyDailyLimit?:number; autoReplyMode?:'instant_247'|'substitutions_only'|'supervised_approval'; autoReplyTone?:'empático'|'técnico_científico'|'esportivo_motivacional'|'acolhedor'; customNotes?:string; createdAt:string; lastLogin:string; }
export interface PlanTokenConfig { plan:SaaSPlanTier; name:string; monthlyPrice:number; defaultMonthlyTokens:number; defaultDailyLimit:number; maxPatients:number; features:string[]; }
export interface SaaSMetrics { mrr:number; arr:number; activeNutritionists:number; totalPatientsInPlatform:number; activeSubscriptionsCount:number; churnRatePercent:number; growthRatePercent:number; totalAiTokensMonth:number; totalAiQuotaAllocated:number; apiSuccessRate:number; }
export interface SaaSAuditLog { id:string; timestamp:string; actor:string; action:string; category:'auth'|'billing'|'patient_data'|'ai_system'|'database'; status:'success'|'warning'|'error'; details:string; }

export interface PhytotherapyActive { substance:string; dosage:string; mechanism:string; }
export interface PhytotherapyFormula { id:string; name:string; form:'Cápsulas'|'Shot Líquido'|'Chá / Infusão'|'Pó / Sachê'|'Gotas Sublinguais'|'Tintura Mãe'; actives:PhytotherapyActive[]; posology:string; treatmentDuration:string; warnings?:string; }
export interface PhytotherapyPrescription { id:string; patientId:string; date:string; title:string; objective:string; formulas:PhytotherapyFormula[]; dietarySynergy?:string; expectedOutcomes?:string; prescriberName:string; prescriberCRN:string; }
export interface MSQCategoryScore { category:string; score:number; maxScore:number; symptomsCount:number; risk:'baixo'|'moderado'|'alto'; }
export interface MSQRecord { id:string; patientId:string; date:string; totalScore:number; classification:'Excelente / Baixo Risco'|'Sobrecarga Moderada'|'Hipersensibilidade Severa / Disbiose'; categories:MSQCategoryScore[]; aiInterpretation?:{summary:string;primaryOrgansAffected:string[];priorityInterventions:string[];recommendedNutritionalTactics:string[]}; }
export interface FoodEquivalence { name:string; portion:string; grams:number; calories:number; carbs:number; protein:number; fats:number; fiber?:number; }
export interface EquivalenceGroup { id:string; category:'Carboidratos'|'Proteínas Magras'|'Gorduras Boas'|'Frutas'|'Laticínios & Vegetais'; referenceItem:string; referencePortion:string; referenceGrams:number; referenceCalories:number; referenceCarbs:number; referenceProtein:number; referenceFats:number; equivalents:FoodEquivalence[]; }
export type PaymentMethod='pix'|'credit_card'|'debit_card'|'boleto'|'cash'|'transfer';
export type PaymentStatus='paid'|'pending'|'overdue'|'canceled';
export type ServiceType='Consulta Avulsa + Cardápio IA'|'Plano Trimestral Hipertrofia'|'Acompanhamento Semestral'|'Bioimpedância + Retorno'|'Protocolo Fitoterápico'|'Consultoria Esportiva'|'Mentoria Nutricional';
export interface FinancialTransaction { id:string; patientId:string; patientName:string; patientAvatar:string; serviceType:ServiceType|string; amount:number; date:string; dueDate?:string; paymentMethod:PaymentMethod; status:PaymentStatus; installments?:number; receiptNumber:string; notes?:string; }
export interface ClinicFinancialSummary { totalRevenueMonth:number; pendingReceivables:number; completedConsultationsCount:number; averageTicket:number; monthlyGrowthPercent:number; annualProjectedRevenue:number; }
