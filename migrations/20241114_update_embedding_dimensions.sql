-- Update embedding dimensions from 1024 to 768 for Marqo Fashion SigLIP model
-- This migration changes the vector dimension and clears existing embeddings

-- First, drop the existing index that depends on the embedding column
DROP INDEX IF EXISTS products_embedding_idx;

-- Update the embedding column to 768 dimensions
ALTER TABLE products ALTER COLUMN embedding TYPE vector(768);

-- Clear all existing embeddings since they're incompatible with the new model
UPDATE products SET embedding = NULL WHERE embedding IS NOT NULL;

-- Recreate the index with the new dimensions
CREATE INDEX IF NOT EXISTS products_embedding_idx ON products USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Add a comment to document the change
COMMENT ON COLUMN products.embedding IS '768-dimensional embeddings from Marqo Fashion SigLIP model (changed from 1024-dim SigLIP on 2024-11-14)';
