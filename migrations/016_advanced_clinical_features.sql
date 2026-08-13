begin;

alter table public.patient_accounts add column if not exists birth_date date;
alter table public.patient_accounts add column if not exists sex text check (sex in ('female','male','other'));
alter table public.patient_accounts add column if not exists activity_factor numeric(4,2) default 1.2;
alter table public.patient_accounts add column if not exists energy_goal text default 'maintenance' check (energy_goal in ('loss','maintenance','gain'));
alter table public.patient_accounts add column if not exists macro_targets jsonb not null default '{}'::jsonb;
alter table public.patient_accounts add column if not exists full_anamnesis jsonb not null default '{}'::jsonb;
alter table public.patient_accounts add column if not exists lgpd_consent_at timestamptz;
alter table public.patient_accounts add column if not exists lgpd_consent_version text;

alter table public.meal_plans add column if not exists template_name text;
alter table public.meal_plans add column if not exists is_template boolean not null default false;
alter table public.meal_plans add column if not exists signature_text text;

create table if not exists public.clinical_alerts (
  id uuid primary key default gen_random_uuid(), patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  client_id uuid not null references public.saas_users(id) on delete cascade, severity text not null default 'medium' check(severity in ('low','medium','high')),
  alert_type text not null, title text not null, details text, resolved_at timestamptz, created_at timestamptz not null default now()
);

alter table public.clinical_alerts enable row level security;
create index if not exists clinical_alerts_client_idx on public.clinical_alerts(client_id,resolved_at,created_at desc);
create index if not exists meal_plan_templates_idx on public.meal_plans(client_id,is_template,created_at desc);

commit;
