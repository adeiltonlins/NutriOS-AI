begin;

create table if not exists public.anthropometric_assessments (
  id uuid primary key default gen_random_uuid(), patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  client_id uuid not null references public.saas_users(id) on delete cascade, assessed_at date not null default current_date,
  weight_kg numeric(6,2), height_cm numeric(6,2), waist_cm numeric(6,2), hip_cm numeric(6,2), body_fat_percent numeric(5,2),
  muscle_mass_kg numeric(6,2), bmi numeric(5,2), notes text, created_at timestamptz not null default now()
);

create table if not exists public.meal_plans (
  id uuid primary key default gen_random_uuid(), patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  client_id uuid not null references public.saas_users(id) on delete cascade, title text not null, objective text,
  status text not null default 'draft' check(status in ('draft','approved','archived')),
  content jsonb not null default '[]'::jsonb, totals jsonb not null default '{}'::jsonb,
  professional_notes text, patient_notes text, approved_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.food_diary_entries (
  id uuid primary key default gen_random_uuid(), patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  client_id uuid not null references public.saas_users(id) on delete cascade, meal_type text not null, consumed_at timestamptz not null default now(),
  description text not null, hunger_before integer check(hunger_before between 0 and 10), satiety_after integer check(satiety_after between 0 and 10),
  mood text, symptoms text, professional_feedback text, reviewed_at timestamptz, created_at timestamptz not null default now()
);

create table if not exists public.clinic_transactions (
  id uuid primary key default gen_random_uuid(), patient_id uuid references public.patient_accounts(id) on delete set null,
  client_id uuid not null references public.saas_users(id) on delete cascade, kind text not null check(kind in ('income','expense')),
  category text not null default 'consulta', description text not null, amount numeric(12,2) not null check(amount >= 0),
  status text not null default 'pending' check(status in ('pending','paid','cancelled')), due_date date, paid_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.clinic_reminders (
  id uuid primary key default gen_random_uuid(), patient_id uuid references public.patient_accounts(id) on delete cascade,
  client_id uuid not null references public.saas_users(id) on delete cascade, title text not null, reminder_at timestamptz not null,
  type text not null default 'followup', completed_at timestamptz, notes text, created_at timestamptz not null default now()
);

alter table public.patient_documents add column if not exists category text not null default 'diet';
alter table public.appointments add column if not exists patient_id uuid references public.patient_accounts(id) on delete set null;
alter table public.appointments add column if not exists end_at timestamptz;
alter table public.appointments add column if not exists confirmed_at timestamptz;

alter table public.anthropometric_assessments enable row level security;
alter table public.meal_plans enable row level security;
alter table public.food_diary_entries enable row level security;
alter table public.clinic_transactions enable row level security;
alter table public.clinic_reminders enable row level security;
create index if not exists anthropometry_patient_idx on public.anthropometric_assessments(patient_id,assessed_at desc);
create index if not exists meal_plans_patient_idx on public.meal_plans(patient_id,created_at desc);
create index if not exists food_diary_patient_idx on public.food_diary_entries(patient_id,consumed_at desc);
create index if not exists transactions_client_idx on public.clinic_transactions(client_id,created_at desc);
create index if not exists reminders_client_idx on public.clinic_reminders(client_id,reminder_at);

commit;
