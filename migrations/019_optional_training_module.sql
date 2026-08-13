begin;
create table if not exists public.workout_plans (
  id uuid primary key default gen_random_uuid(), client_id uuid not null references public.saas_users(id) on delete cascade,
  patient_id uuid not null references public.patient_accounts(id) on delete cascade, title text not null, goal text,
  status text not null default 'draft' check (status in ('draft','published','archived')),
  exercises jsonb not null default '[]'::jsonb, professional_notes text, patient_notes text,
  published_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.workout_logs (
  id uuid primary key default gen_random_uuid(), client_id uuid not null references public.saas_users(id) on delete cascade,
  patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  workout_plan_id uuid not null references public.workout_plans(id) on delete cascade,
  readiness jsonb not null default '{}'::jsonb, exercise_results jsonb not null default '[]'::jsonb,
  perceived_exertion integer check (perceived_exertion between 1 and 10), notes text,
  completed_at timestamptz not null default now(), created_at timestamptz not null default now()
);
alter table public.workout_plans enable row level security;
alter table public.workout_logs enable row level security;
create index if not exists workout_plans_patient_idx on public.workout_plans(client_id, patient_id, created_at desc);
create index if not exists workout_logs_patient_idx on public.workout_logs(client_id, patient_id, completed_at desc);
commit;
