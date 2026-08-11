begin;

create table if not exists public.patient_accounts (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.saas_users(id) on delete cascade,
  lead_id uuid,
  name text not null,
  identifier text,
  phone text,
  plan_name text,
  active boolean not null default true,
  access_expires_at timestamptz not null,
  diet_context text,
  message_limit integer not null default 200 check(message_limit between 1 and 5000),
  messages_used integer not null default 0,
  usage_started_at timestamptz not null default now(),
  last_access_at timestamptz,
  archived_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.patient_access_codes (
  id uuid primary key default gen_random_uuid(), patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  code_hash text not null, code_lookup text not null, expires_at timestamptz not null,
  used_at timestamptz, revoked_at timestamptz, created_at timestamptz not null default now()
);

create table if not exists public.patient_sessions (
  id uuid primary key default gen_random_uuid(), patient_id uuid not null references public.patient_accounts(id) on delete cascade,
  token_hash text not null, token_lookup text not null, expires_at timestamptz not null,
  created_at timestamptz not null default now(), last_seen_at timestamptz not null default now(), revoked_at timestamptz
);

alter table public.patient_accounts enable row level security;
alter table public.patient_access_codes enable row level security;
alter table public.patient_sessions enable row level security;
create index if not exists patient_accounts_client_idx on public.patient_accounts(client_id, archived_at, access_expires_at);
create index if not exists patient_codes_lookup_idx on public.patient_access_codes(code_lookup) where revoked_at is null;
create index if not exists patient_sessions_lookup_idx on public.patient_sessions(token_lookup) where revoked_at is null;

commit;
