begin;

alter table public.saas_users add column if not exists custom_domain text;
alter table public.saas_users add column if not exists onboarding_completed_at timestamptz;
alter table public.saas_users add column if not exists last_weekly_report_at timestamptz;
alter table public.saas_users add column if not exists billing_provider text;
alter table public.saas_users add column if not exists external_subscription_id text;

create unique index if not exists saas_users_custom_domain_idx on public.saas_users(custom_domain) where custom_domain is not null;

create table if not exists public.audit_logs (
  id uuid primary key default gen_random_uuid(), actor_id uuid references public.saas_users(id) on delete set null,
  client_id uuid references public.saas_users(id) on delete cascade, action text not null,
  resource_type text, resource_id text, metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.data_requests (
  id uuid primary key default gen_random_uuid(), client_id uuid not null references public.saas_users(id) on delete cascade,
  session_id text not null, request_type text not null check(request_type in ('export','delete')),
  status text not null default 'pending', requested_at timestamptz not null default now(), completed_at timestamptz
);

alter table public.audit_logs enable row level security;
alter table public.data_requests enable row level security;
create index if not exists audit_client_date_idx on public.audit_logs(client_id, created_at desc);
create index if not exists data_requests_client_idx on public.data_requests(client_id, status);

commit;
