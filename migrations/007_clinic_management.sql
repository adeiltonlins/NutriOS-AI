begin;

create table if not exists public.client_services (
  id uuid primary key default gen_random_uuid(), client_id uuid not null references public.saas_users(id) on delete cascade,
  name text not null, description text, price numeric(12,2) not null default 0,
  payment_url text, active boolean not null default true, created_at timestamptz not null default now()
);

create table if not exists public.anamneses (
  id uuid primary key default gen_random_uuid(), client_id uuid not null references public.saas_users(id) on delete cascade,
  session_id text not null, answers jsonb not null default '{}'::jsonb, submitted_at timestamptz not null default now(),
  unique(client_id, session_id)
);

create table if not exists public.availability (
  id uuid primary key default gen_random_uuid(), client_id uuid not null references public.saas_users(id) on delete cascade,
  weekday integer not null check(weekday between 0 and 6), start_time time not null, end_time time not null,
  slot_minutes integer not null default 60 check(slot_minutes between 15 and 240), active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.appointments (
  id uuid primary key default gen_random_uuid(), client_id uuid not null references public.saas_users(id) on delete cascade,
  session_id text not null, service_id uuid references public.client_services(id) on delete set null,
  patient_name text not null, patient_phone text not null, starts_at timestamptz not null,
  status text not null default 'scheduled', notes text, created_at timestamptz not null default now(),
  unique(client_id, starts_at)
);

alter table public.client_services enable row level security;
alter table public.anamneses enable row level security;
alter table public.availability enable row level security;
alter table public.appointments enable row level security;

create index if not exists services_client_idx on public.client_services(client_id, active);
create index if not exists anamneses_client_idx on public.anamneses(client_id, submitted_at desc);
create index if not exists availability_client_idx on public.availability(client_id, weekday);
create index if not exists appointments_client_date_idx on public.appointments(client_id, starts_at);

commit;
