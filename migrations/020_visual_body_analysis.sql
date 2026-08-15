begin;

alter table public.anthropometric_assessments
  add column if not exists evaluation_method text,
  add column if not exists body_water_percent numeric(5,2),
  add column if not exists front_photo_id uuid,
  add column if not exists side_photo_id uuid,
  add column if not exists analysis_data jsonb not null default '{}'::jsonb;

create index if not exists anthropometry_visual_photos_idx
  on public.anthropometric_assessments(client_id, patient_id, front_photo_id, side_photo_id);

comment on column public.anthropometric_assessments.analysis_data is
  'Indicadores derivados da Análise Corporal Visual NutriBot. Não representa escaneamento ou reconstrução 3D.';

commit;
