begin;

alter table public.leads add column if not exists lead_status text not null default 'duvida';
alter table public.leads add column if not exists lead_score integer not null default 0;
alter table public.leads add column if not exists lead_summary text;
alter table public.leads add column if not exists message_count integer not null default 0;

create index if not exists leads_client_status_idx on public.leads(client_id, lead_status);

commit;
