begin;

alter table public.saas_users add column if not exists public_slug text;

update public.saas_users
set public_slug = trim(both '-' from lower(regexp_replace(name, '[^a-zA-Z0-9]+', '-', 'g'))) || '-' || substr(id::text, 1, 6)
where role = 'client' and public_slug is null;

create unique index if not exists saas_users_public_slug_idx
on public.saas_users(public_slug)
where public_slug is not null;

commit;
