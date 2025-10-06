-- Ensure idempotent upserts based on (source, external_id)
alter table products add column if not exists source text;
alter table products add column if not exists external_id text;
create unique index if not exists products_source_external_id_uidx on products(source, external_id);

