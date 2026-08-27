begin;

create table if not exists public.patient_phytotherapy_prescriptions (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.saas_users(id) on delete cascade,
  patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  title text not null,
  prescription_type text not null default 'phytotherapy' check (prescription_type in ('phytotherapy','formula')),
  pharmaceutical_form text,
  quantity text,
  usage_instructions text,
  duration_text text,
  professional_notes text,
  patient_notes text,
  signature_text text,
  status text not null default 'draft' check (status in ('draft','active','completed','cancelled')),
  starts_at date,
  ends_at date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.patient_phytotherapy_items (
  id uuid primary key default gen_random_uuid(),
  prescription_id uuid not null references public.patient_phytotherapy_prescriptions(id) on delete cascade,
  client_id uuid not null references public.saas_users(id) on delete cascade,
  patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  active_name text not null,
  concentration text,
  dose text,
  notes text,
  sort_order integer not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists patient_phytotherapy_prescriptions_patient_idx on public.patient_phytotherapy_prescriptions(client_id,patient_id,created_at desc);
create index if not exists patient_phytotherapy_items_prescription_idx on public.patient_phytotherapy_items(client_id,patient_id,prescription_id,sort_order);
alter table public.patient_phytotherapy_prescriptions enable row level security;
alter table public.patient_phytotherapy_items enable row level security;

commit;
