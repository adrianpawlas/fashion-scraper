-- Update embedding column to 1024-dim SigLIP model
-- This migration handles the change from 512-dim CLIP to 1024-dim SigLIP embeddings
-- Safe to run even if old columns were manually deleted

do $$
begin
    -- Clean up any leftover temporary columns from previous migrations
    alter table products drop column if exists embedding_old_512dim;
    alter table products drop column if exists embeddings_old;

    -- Check if embedding column exists
    if exists (select 1 from information_schema.columns where table_name = 'products' and column_name = 'embedding') then
        -- Get current column type definition
        declare
            current_type text;
            current_udt text;
        begin
            select
                c.data_type,
                c.udt_name
            into current_type, current_udt
            from information_schema.columns c
            where c.table_name = 'products' and c.column_name = 'embedding';

            -- Check if it's already vector(1024) - if so, we're done
            if current_udt = 'vector' and exists (
                select 1 from pg_attribute a
                join pg_class c on c.oid = a.attrelid
                join pg_type t on t.oid = a.atttypid
                where c.relname = 'products'
                and a.attname = 'embedding'
                and t.typname = 'vector'
                and a.attdimensions = '[1024]'
            ) then
                raise notice 'Embedding column is already 1024-dim - no changes needed';
                return;
            end if;

            -- Column exists but is wrong type - recreate it
            raise notice 'Recreating embedding column as vector(1024) - old embeddings will be recomputed on next scrape';
            alter table products drop column embedding;
        end;
    end if;

    -- Create the 1024-dim embedding column
    alter table products add column embedding vector(1024);

    -- Create or recreate vector index for efficient similarity search
    drop index if exists products_embedding_idx;
    create index products_embedding_idx on products using ivfflat (embedding vector_cosine_ops) with (lists = 100);

    raise notice 'Embedding column migration completed successfully - ready for 1024-dim SigLIP embeddings';

exception
    when others then
        raise notice 'Embedding column migration failed - manual intervention may be required. Error: %', sqlerrm;
        raise;
end $$;
