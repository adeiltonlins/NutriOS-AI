begin;

create table if not exists public.patient_records (
  id uuid primary key default gen_random_uuid(), patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  client_id uuid not null references public.saas_users(id) on delete cascade, notes text not null default '',
  hunger_status text, energy_status text, sleep_status text, bowel_status text, adherence_status text,
  clinical_alerts text, created_at timestamptz not null default now()
);

create table if not exists public.patient_checkins (
  id uuid primary key default gen_random_uuid(), patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  client_id uuid not null references public.saas_users(id) on delete cascade,
  hunger integer not null check(hunger between 0 and 10), energy integer not null check(energy between 0 and 10),
  sleep integer not null check(sleep between 0 and 10), adherence integer not null check(adherence between 0 and 10),
  water_liters numeric(4,1), training_sessions integer, weight_kg numeric(6,2), bowel_status text,
  cravings boolean not null default false, symptoms text, difficulties text, notes text, created_at timestamptz not null default now()
);

create table if not exists public.patient_documents (
  id uuid primary key default gen_random_uuid(), patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  client_id uuid not null references public.saas_users(id) on delete cascade, title text not null, original_name text not null,
  storage_path text not null unique, version integer not null default 1, is_current boolean not null default true,
  created_at timestamptz not null default now()
);

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('patient-documents','patient-documents',false,10000000,array['application/pdf'])
on conflict (id) do update set public=false, file_size_limit=10000000, allowed_mime_types=array['application/pdf'];

alter table public.patient_records enable row level security;
alter table public.patient_checkins enable row level security;
alter table public.patient_documents enable row level security;
create index if not exists patient_records_patient_idx on public.patient_records(patient_id,created_at desc);
create index if not exists patient_checkins_patient_idx on public.patient_checkins(patient_id,created_at desc);
create index if not exists patient_documents_patient_idx on public.patient_documents(patient_id,created_at desc);

commit;
