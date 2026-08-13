begin;

create extension if not exists pgcrypto;

create table if not exists public.custom_foods (
  id uuid primary key default gen_random_uuid(), client_id uuid not null references public.saas_users(id) on delete cascade,
  source text not null default 'custom' check (source in ('custom','tbca','manufacturer')),
  external_code text, name text not null, brand text, household_measure text, household_grams numeric,
  nutrients jsonb not null default '{}'::jsonb, active boolean not null default true,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists custom_foods_client_name_idx on public.custom_foods(client_id,name);

create table if not exists public.food_equivalences (
  id uuid primary key default gen_random_uuid(), client_id uuid not null references public.saas_users(id) on delete cascade,
  source_food_ref text not null, target_food_ref text not null, source_grams numeric not null default 100,
  target_grams numeric not null default 100, notes text, created_at timestamptz not null default now()
);

create table if not exists public.patient_questionnaires (
  id uuid primary key default gen_random_uuid(), client_id uuid not null references public.saas_users(id) on delete cascade,
  patient_id uuid not null references public.patient_accounts(id) on delete cascade, template_key text,
  title text not null, category text not null default 'clinical', schema_snapshot jsonb not null default '[]'::jsonb,
  answers jsonb not null default '{}'::jsonb, score jsonb not null default '{}'::jsonb,
  status text not null default 'assigned' check (status in ('assigned','completed','reviewed')),
  due_at timestamptz, completed_at timestamptz, reviewed_at timestamptz,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists patient_questionnaires_patient_idx on public.patient_questionnaires(client_id,patient_id,status);

create table if not exists public.maternal_child_records (
  id uuid primary key default gen_random_uuid(), client_id uuid not null references public.saas_users(id) on delete cascade,
  patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  record_type text not null check (record_type in ('pregnancy','lactation','child','adolescent')),
  reference_date date not null default current_date, gestational_week numeric, pre_pregnancy_weight numeric,
  current_weight numeric, birth_date date, sex text, height_cm numeric, head_circumference_cm numeric,
  metrics jsonb not null default '{}'::jsonb, notes text, created_at timestamptz not null default now()
);
create index if not exists maternal_child_patient_idx on public.maternal_child_records(client_id,patient_id,reference_date desc);

create table if not exists public.patient_progress_photos (
  id uuid primary key default gen_random_uuid(), client_id uuid not null references public.saas_users(id) on delete cascade,
  patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  view_type text not null default 'front' check (view_type in ('front','side','back','other')),
  captured_at date not null default current_date, storage_path text not null, mime_type text not null,
  file_size integer not null, notes text, consent_at timestamptz not null default now(), created_at timestamptz not null default now()
);
create index if not exists progress_photos_patient_idx on public.patient_progress_photos(client_id,patient_id,captured_at desc);

create table if not exists public.calendar_integrations (
  id uuid primary key default gen_random_uuid(), client_id uuid not null unique references public.saas_users(id) on delete cascade,
  provider text not null default 'google', access_token_encrypted text, refresh_token_encrypted text,
  token_expires_at timestamptz, calendar_id text not null default 'primary', connected_at timestamptz,
  last_sync_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

alter table public.food_diary_entries add column if not exists photo_storage_path text;
alter table public.food_diary_entries add column if not exists photo_mime_type text;
alter table public.food_diary_entries add column if not exists photo_size integer;
alter table public.meal_plans add column if not exists schedule jsonb not null default '{}'::jsonb;
alter table public.meal_plans add column if not exists periodization_notes text;
alter table public.appointments add column if not exists google_event_id text;
alter table public.clinic_transactions add column if not exists payment_method text;
alter table public.clinic_transactions add column if not exists recurrence text not null default 'none';
alter table public.clinic_transactions add column if not exists competence_month text;
alter table public.clinic_transactions add column if not exists receipt_number text;
alter table public.clinic_transactions add column if not exists notes text;

alter table public.custom_foods enable row level security;
alter table public.food_equivalences enable row level security;
alter table public.patient_questionnaires enable row level security;
alter table public.maternal_child_records enable row level security;
alter table public.patient_progress_photos enable row level security;
alter table public.calendar_integrations enable row level security;

commit;
