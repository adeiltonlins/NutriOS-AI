begin;

create table if not exists public.patient_anthropometry_advanced (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.saas_users(id) on delete cascade,
  patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  assessment_id uuid not null references public.anthropometric_assessments(id) on delete cascade,
  protocol text not null default 'manual' check (protocol in ('manual','pollock3','pollock7')),
  age integer check (age between 12 and 120),
  sex text check (sex in ('female','male')),
  skinfolds jsonb not null default '{}'::jsonb,
  circumferences jsonb not null default '{}'::jsonb,
  posture jsonb not null default '{}'::jsonb,
  body_density numeric,
  calculated_body_fat_percent numeric,
  calculated_fat_mass_kg numeric,
  calculated_lean_mass_kg numeric,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (assessment_id)
);

create index if not exists patient_anthropometry_advanced_patient_idx
  on public.patient_anthropometry_advanced(client_id, patient_id, created_at desc);

alter table public.patient_anthropometry_advanced enable row level security;

commit;
