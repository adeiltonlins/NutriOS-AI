begin;

alter table public.saas_users add column if not exists monthly_price numeric(12,2) not null default 0;
alter table public.saas_users add column if not exists billing_status text not null default 'trial';
alter table public.saas_users add column if not exists next_billing_at timestamptz;
alter table public.saas_users add column if not exists billing_notes text;

create index if not exists saas_users_billing_idx on public.saas_users(billing_status, next_billing_at);

commit;
