begin;

alter table public.saas_users
    add column if not exists archived_at timestamptz;

create index if not exists saas_users_archived_at_idx
    on public.saas_users (archived_at);

commit;
