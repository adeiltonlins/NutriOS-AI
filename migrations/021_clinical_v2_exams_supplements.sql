begin;

create extension if not exists pgcrypto;

create table if not exists public.patient_lab_exams (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.saas_users(id) on delete cascade,
  patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  exam_name text not null,
  category text not null default 'laboratory',
  collected_at date,
  value_numeric numeric,
  value_text text,
  unit text,
  reference_min numeric,
  reference_max numeric,
  reference_text text,
  status text not null default 'normal' check (status in ('low','normal','high','attention')),
  notes text,
  source text not null default 'manual' check (source in ('manual','document')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists patient_lab_exams_patient_idx on public.patient_lab_exams(client_id,patient_id,collected_at desc);

create table if not exists public.patient_supplements (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.saas_users(id) on delete cascade,
  patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  name text not null,
  dose text,
  frequency text,
  schedule text,
  route text not null default 'oral',
  objective text,
  instructions text,
  starts_at date,
  ends_at date,
  status text not null default 'active' check (status in ('active','paused','completed','cancelled')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists patient_supplements_patient_idx on public.patient_supplements(client_id,patient_id,status,created_at desc);

alter table public.patient_lab_exams enable row level security;
alter table public.patient_supplements enable row level security;

commit;
