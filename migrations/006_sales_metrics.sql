begin;

alter table public.leads add column if not exists sale_amount numeric(12,2) not null default 0;
alter table public.leads add column if not exists lead_source text not null default 'direto';

create index if not exists leads_client_paid_date_idx on public.leads(client_id, pago_em);
create index if not exists leads_client_source_idx on public.leads(client_id, lead_source);

commit;
