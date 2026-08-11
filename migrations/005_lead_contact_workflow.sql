begin;

alter table public.leads add column if not exists lead_name text;
alter table public.leads add column if not exists lead_phone text;
alter table public.leads add column if not exists contact_consent_at timestamptz;
alter table public.leads add column if not exists workflow_status text not null default 'new';
alter table public.leads add column if not exists claimed_paid_at timestamptz;
alter table public.leads add column if not exists manual_payment_confirmed_at timestamptz;
alter table public.leads add column if not exists contacted_at timestamptz;
alter table public.leads add column if not exists anamnesis_sent_at timestamptz;
alter table public.leads add column if not exists scheduled_at timestamptz;

create index if not exists leads_client_workflow_idx on public.leads(client_id, workflow_status);

commit;
