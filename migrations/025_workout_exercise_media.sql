alter table public.workout_exercises add column if not exists image_url text;
alter table public.workout_exercises add column if not exists image_storage_path text;
alter table public.workout_exercises add column if not exists image_mime_type text;

comment on column public.workout_exercises.image_url is 'URL da imagem/capa do exercício quando fornecida externamente';
comment on column public.workout_exercises.image_storage_path is 'Caminho privado da imagem enviada pelo profissional';
