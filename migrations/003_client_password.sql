begin;
alter table public.saas_users add column if not exists password_hash text;
alter table public.saas_users add column if not exists password_created_at timestamptz;
commit;
