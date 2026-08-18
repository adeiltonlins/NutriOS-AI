begin;

-- Fluxo completo de consulta: agendamento -> pré-consulta -> consulta online -> plano.
alter table public.appointments add column if not exists consultation_mode text not null default 'presencial' check (consultation_mode in ('presencial','online'));
alter table public.appointments add column if not exists meeting_url text;
alter table public.appointments add column if not exists preconsultation_status text not null default 'not_sent' check (preconsultation_status in ('not_sent','sent','completed','reviewed'));
alter table public.appointments add column if not exists consultation_status text not null default 'scheduled' check (consultation_status in ('scheduled','confirmed','in_progress','completed','cancelled','no_show'));
alter table public.appointments add column if not exists preconsultation_sent_at timestamptz;
alter table public.appointments add column if not exists preconsultation_completed_at timestamptz;
alter table public.appointments add column if not exists consultation_started_at timestamptz;
alter table public.appointments add column if not exists consultation_completed_at timestamptz;

create table if not exists public.preconsultation_forms (
  id uuid primary key default gen_random_uuid(),
  appointment_id uuid not null references public.appointments(id) on delete cascade,
  patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  client_id uuid not null references public.saas_users(id) on delete cascade,
  status text not null default 'draft' check (status in ('draft','sent','completed','reviewed')),
  schema_snapshot jsonb not null default '[]'::jsonb,
  answers jsonb not null default '{}'::jsonb,
  summary jsonb not null default '{}'::jsonb,
  token_hash text,
  sent_at timestamptz,
  completed_at timestamptz,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.consultation_notes (
  id uuid primary key default gen_random_uuid(),
  appointment_id uuid not null references public.appointments(id) on delete cascade,
  patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  client_id uuid not null references public.saas_users(id) on delete cascade,
  subjective text,
  objective text,
  assessment text,
  plan text,
  ai_summary jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists preconsultation_client_idx on public.preconsultation_forms(client_id, created_at desc);
create index if not exists preconsultation_patient_idx on public.preconsultation_forms(patient_id, created_at desc);
create index if not exists preconsultation_appointment_idx on public.preconsultation_forms(appointment_id);
create index if not exists consultation_notes_client_idx on public.consultation_notes(client_id, created_at desc);
create index if not exists consultation_notes_patient_idx on public.consultation_notes(patient_id, created_at desc);
create index if not exists appointments_consultation_status_idx on public.appointments(client_id, consultation_status, starts_at);

alter table public.preconsultation_forms enable row level security;
alter table public.consultation_notes enable row level security;

commit;
