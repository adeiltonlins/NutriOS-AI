alter table public.clinical_form_templates
  add column if not exists category text not null default 'custom',
  add column if not exists template_key text,
  add column if not exists is_system boolean not null default false;

create unique index if not exists clinical_form_templates_org_template_key_uidx
  on public.clinical_form_templates (organization_id, template_key)
  where template_key is not null and is_active = true;
