begin;

alter table public.patient_accounts
  add column if not exists login_identifier text,
  add column if not exists password_hash text,
  add column if not exists password_created_at timestamptz;

create unique index if not exists patient_accounts_login_identifier_unique
  on public.patient_accounts (lower(login_identifier))
  where login_identifier is not null and archived_at is null;

commit;
