create table if not exists public.questionnaire_templates (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null,
  title text not null,
  category text not null default 'custom',
  description text,
  fields jsonb not null default '[]'::jsonb,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists questionnaire_templates_client_idx
  on public.questionnaire_templates (client_id, active, created_at desc);

alter table public.questionnaire_templates enable row level security;

-- NutriOS accesses tenant data through the authenticated backend/service layer.
-- Keep direct anonymous access blocked; ownership is additionally enforced by client_id in business_store.
revoke all on table public.questionnaire_templates from anon;
