-- Update embedding column to 768-dim SigLIP model
-- This migration handles the change to 768-dim SigLIP base model
-- Safe to run even if old columns were manually deleted

do $$
begin
    -- Clean up any leftover temporary columns from previous migrations
    alter table products drop column if exists embedding_old_512dim;
    alter table products drop column if exists embedding_old_1024dim;
    alter table products drop column if exists embeddings_old;

    -- Drop existing embedding column (will be recreated as 768-dim)
    -- This is safe because embeddings will be recomputed on next scrape
    alter table products drop column if exists embedding;

    -- Create the 768-dim embedding column
    alter table products add column embedding vector(768);

    -- Create or recreate vector index for efficient similarity search
    drop index if exists products_embedding_idx;
    create index products_embedding_idx on products using ivfflat (embedding vector_cosine_ops) with (lists = 100);

    raise notice 'Embedding column migration completed successfully - ready for 768-dim SigLIP embeddings';

exception
    when others then
        raise notice 'Embedding column migration failed - manual intervention may be required. Error: %', sqlerrm;
        raise;
end $$;
