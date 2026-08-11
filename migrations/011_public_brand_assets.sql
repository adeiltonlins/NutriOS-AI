begin;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('nutribot-assets', 'nutribot-assets', true, 1000000, array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do update set
    public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

commit;
