-- Update embedding column to 1024-dim SigLIP model
-- This migration handles the change from 512-dim CLIP to 1024-dim SigLIP embeddings

do $$
begin
    -- Check if embedding column exists and get its current type
    if exists (select 1 from information_schema.columns where table_name = 'products' and column_name = 'embedding') then
        -- Get current column type definition
        declare
            current_type text;
        begin
            select data_type || coalesce('(' || character_maximum_length || ')', '') into current_type
            from information_schema.columns
            where table_name = 'products' and column_name = 'embedding';

            -- If it's not already vector(1024), update it
            if current_type != 'vector' or current_type is null then
                -- Rename old column and create new one (safer than dropping)
                alter table products rename column embedding to embedding_old_512dim;
                alter table products add column embedding vector(1024);

                -- Copy data if possible (this will fail for dimension mismatch, which is expected)
                begin
                    update products set embedding = embedding_old_512dim::vector(1024) where embedding_old_512dim is not null;
                exception
                    when others then
                        -- If conversion fails (dimension mismatch), leave embedding as null
                        -- This will trigger re-computation of embeddings on next scrape
                        raise notice 'Cannot convert 512-dim to 1024-dim embeddings - embeddings will be recomputed on next scrape';
                end;

                -- Drop old column after successful migration
                alter table products drop column if exists embedding_old_512dim;
            end if;
        end;
    else
        -- Column doesn't exist, create it
        alter table products add column embedding vector(1024);
    end if;

    -- Create or recreate vector index for efficient similarity search
    drop index if exists products_embedding_idx;
    create index products_embedding_idx on products using ivfflat (embedding vector_cosine_ops) with (lists = 100);

exception
    when others then
        raise notice 'Embedding column migration failed - manual intervention may be required';
        raise;
end $$;
