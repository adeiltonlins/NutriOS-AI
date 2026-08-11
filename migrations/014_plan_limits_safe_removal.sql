begin;

alter table public.saas_users
  add column if not exists patient_limit integer not null default 10
  check (patient_limit >= -1);

alter table public.patient_accounts
  add column if not exists hidden_at timestamptz;

create index if not exists patient_accounts_visible_idx
  on public.patient_accounts(client_id, hidden_at, archived_at, access_expires_at);

comment on column public.saas_users.patient_limit is
  'Máximo de pacientes visíveis/não arquivados. -1 significa ilimitado.';
comment on column public.patient_accounts.hidden_at is
  'Ocultação lógica pelo profissional; preserva prontuário, documentos e métricas.';

commit;
