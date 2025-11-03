import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Missing SUPABASE_URL or SUPABASE_KEY environment variables")
    exit(1)

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Read the migration file
with open("migrations/20251103_update_embedding_1024dim.sql", "r") as f:
    migration_sql = f.read()

print("Running migration to update embedding column to 1024 dimensions...")
print("Migration SQL:")
print("=" * 50)
print(migration_sql)
print("=" * 50)

try:
    # Execute the migration
    result = supabase.rpc("exec_sql", {"sql": migration_sql}).execute()
    print("Migration completed successfully!")
    print(result)
except Exception as e:
    print(f"Migration failed: {e}")
    print("You may need to run this migration manually in your Supabase dashboard.")
