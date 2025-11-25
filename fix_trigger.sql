-- Fix the auto_generate_embedding trigger to work with your scraper
-- This makes the trigger conditional and fixes the service role key issue

-- Step 1: Drop the existing trigger and function
DROP TRIGGER IF EXISTS auto_generate_embedding_trigger ON products;
DROP FUNCTION IF EXISTS auto_generate_embedding();

-- Step 2: Create the fixed function
CREATE OR REPLACE FUNCTION auto_generate_embedding()
RETURNS TRIGGER AS $$
DECLARE
  service_role_key TEXT;
BEGIN
  -- Only generate embeddings when they're NULL (preserves mobile app functionality)
  IF NEW.embedding IS NULL THEN
    -- Get the service role key (replace 'YOUR_SERVICE_ROLE_KEY_HERE' with your actual key)
    service_role_key := 'YOUR_SERVICE_ROLE_KEY_HERE';

    -- Call your Edge Function
    PERFORM net.http_post(
      url := 'https://your-project.supabase.co/functions/v1/embedd_image',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' || service_role_key
      ),
      body := jsonb_build_object(
        'product_id', NEW.id,
        'image_url', NEW.image_url
      )
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Step 3: Recreate the trigger
CREATE TRIGGER auto_generate_embedding_trigger
  AFTER INSERT ON products
  FOR EACH ROW
  EXECUTE FUNCTION auto_generate_embedding();

-- How to get your service role key:
-- Go to Supabase Dashboard → Settings → API → service_role key
-- Copy the "service_role" key (not the "anon" key)
-- Replace 'YOUR_SERVICE_ROLE_KEY_HERE' with that key
