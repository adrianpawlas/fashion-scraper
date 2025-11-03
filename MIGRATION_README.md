# Database Migration Required

## 🚨 IMPORTANT: Run This Migration Before Next Scrape

The scraper was updated to use 1024-dimensional SigLIP embeddings instead of 512-dimensional CLIP embeddings. You need to update your Supabase database schema to accept the new embedding dimensions.

### Error You May See:
```
RuntimeError: Supabase upsert failed: 400 {"code":"22000","details":null,"hint":null,"message":"expected 1024 dimensions, not 512"}
```

### Solution: Run This SQL in Your Supabase SQL Editor

Go to your Supabase Dashboard → SQL Editor and run this migration:

```sql
-- Update embedding column to 1024-dim SigLIP model
-- This migration handles the change from 512-dim CLIP to 1024-dim SigLIP embeddings
-- Safe to run even if old columns were manually deleted

do $$
begin
    -- Clean up any leftover temporary columns from previous migrations
    alter table products drop column if exists embedding_old_512dim;
    alter table products drop column if exists embeddings_old;

    -- Drop existing embedding column (will be recreated as 1024-dim)
    -- This is safe because embeddings will be recomputed on next scrape
    alter table products drop column if exists embedding;

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
```

### What This Migration Does:
1. **Drops old temporary columns** (if any exist)
2. **Drops the existing embedding column** (safe - embeddings will be recomputed)
3. **Creates new `vector(1024)` column** for SigLIP embeddings
4. **Creates/updates the vector index** for efficient similarity search

### After Running the Migration:
- Your database will accept 1024-dimensional embeddings
- The GitHub Actions workflow will run successfully
- All products will get new SigLIP embeddings on the next scrape

### Alternative: Manual Schema Update
If you prefer to do it manually:
```sql
-- Drop existing column and index
ALTER TABLE products DROP COLUMN IF EXISTS embedding;
DROP INDEX IF EXISTS products_embedding_idx;

-- Create new 1024-dim column
ALTER TABLE products ADD COLUMN embedding vector(1024);

-- Create vector index
CREATE INDEX products_embedding_idx ON products USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```
