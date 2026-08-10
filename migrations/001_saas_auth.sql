begin;

create extension if not exists pgcrypto;

create table if not exists public.saas_users (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  identifier text not null unique,
  role text not null check (role in ('admin','client')),
  active boolean not null default true,
  plan text,
  expires_at timestamptz,
  ai_config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table if not exists public.access_codes (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references public.saas_users(id) on delete cascade,
  code_hash text not null, code_lookup text not null, expires_at timestamptz not null,
  used_at timestamptz, revoked_at timestamptz, attempts integer not null default 0,
  max_attempts integer not null default 5, created_by uuid references public.saas_users(id), created_at timestamptz not null default now()
);
create index if not exists access_codes_lookup_idx on public.access_codes(code_lookup);
create table if not exists public.user_sessions (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references public.saas_users(id) on delete cascade,
  session_token_hash text not null, token_lookup text not null unique, role text not null,
  expires_at timestamptz not null, created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(), revoked_at timestamptz
);
alter table public.leads add column if not exists client_id uuid references public.saas_users(id);
create index if not exists leads_client_id_idx on public.leads(client_id);

alter table public.saas_users enable row level security;
alter table public.access_codes enable row level security;
alter table public.user_sessions enable row level security;
-- O backend usa exclusivamente a service role; nenhuma destas tabelas é acessível ao navegador.

commit;
