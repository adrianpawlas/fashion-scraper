# Migration Guide: Secure Your Supabase Scrapers

## 🎯 Overview

This guide helps you secure your Supabase scrapers. You have two options:

1. **Quick & Easy**: Enable RLS (Row Level Security) - **Recommended** ✅
2. **Advanced**: Create limited database user - Maximum isolation

---

## ⚡ Quick Start: Enable RLS Only (Recommended)

**This is the simplest and most practical approach for Supabase.**

### Why This Works:
- ✅ Service role key is already secure (encrypted in GitHub Secrets)
- ✅ RLS adds an additional protection layer
- ✅ Zero code changes needed
- ✅ Mobile app gets proper security
- ✅ Scrapers continue working (service role bypasses RLS)

### Steps:

1. **Run this SQL in Supabase SQL Editor:**
```sql
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
```

2. **Test your scraper:**
```bash
python -m scraper.cli --limit 5
```

3. **Done!** Your scrapers are now more secure.

**That's it!** No code changes, no GitHub Secrets updates, no complexity.

---

## 🔒 Advanced: Limited Database User (Optional)

If you want maximum isolation (database user can only access products table), follow the steps below.

---

## 📋 Prerequisites

- Access to Supabase SQL Editor
- Admin access to Supabase project
- GitHub repository with scraper code
- GitHub Actions secrets configured

---

## 🎯 Recommended Approach for Supabase

**For Supabase, the best security approach is:**
1. ✅ **Keep service role key** (already secure in GitHub Secrets)
2. ✅ **Enable RLS** (adds protection layer)  
3. ✅ **Service role bypasses RLS** (needed for scrapers)
4. ✅ **Mobile app protected by RLS** (authenticated users)

**This provides excellent security with zero code changes!**

If you still want a limited database user (for maximum isolation), follow Step 1 below. Otherwise, you can skip to "Enable RLS Only" section.

---

## 🔧 Step 1: Create Limited Database User in Supabase (Optional)

### 1.1 Open Supabase SQL Editor

1. Go to your Supabase project dashboard
2. Navigate to **SQL Editor**
3. Click **New Query**

### 1.2 Run This SQL Script

```sql
-- ============================================
-- STEP 1: Create Limited Database User
-- ============================================

-- Generate a secure random password (replace with your own strong password)
-- You can use: openssl rand -base64 32
-- Or any password generator

-- Create the user
CREATE USER scraper_user WITH PASSWORD 'YOUR_SECURE_PASSWORD_HERE';

-- Grant minimal schema access
GRANT USAGE ON SCHEMA public TO scraper_user;

-- Grant only necessary permissions on products table
GRANT INSERT, UPDATE, SELECT, DELETE ON public.products TO scraper_user;

-- Grant sequence access (needed for auto-increment if you use it)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO scraper_user;

-- ============================================
-- STEP 2: Enable RLS (if not already enabled)
-- ============================================

ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;

-- ============================================
-- STEP 3: Create RLS Policy for Scraper User
-- ============================================

-- This policy allows the scraper_user to bypass RLS for all operations
-- This is safe because the user already has limited permissions
CREATE POLICY "Scraper user full access to products" 
ON public.products
FOR ALL 
TO scraper_user
USING (true) 
WITH CHECK (true);

-- ============================================
-- STEP 4: Get the Connection String
-- ============================================

-- After creating the user, you'll need to construct the connection string
-- Format: postgresql://scraper_user:YOUR_PASSWORD@db.xxxxx.supabase.co:5432/postgres
-- Or use the Supabase REST API with the user's JWT token
```

### 1.3 Important Notes

- **Replace `YOUR_SECURE_PASSWORD_HERE`** with a strong password (at least 32 characters)
- **Save the password securely** - you'll need it for GitHub Secrets
- The user can **only** access the `products` table - no other tables or functions

---

## 🔑 Step 2: Create Custom API Key (Supabase-Specific)

Since Supabase uses JWT tokens (not Basic Auth), we'll create a **custom API key** with limited scope. This is simpler than managing database users.

### Option A: Use Service Role with RLS Enabled (Simplest - Recommended)

**This is actually the best approach for Supabase:**
1. Service role key is already secure (encrypted in GitHub Secrets)
2. Enable RLS (adds protection layer)
3. Service role bypasses RLS (needed for scrapers)
4. Mobile app uses authenticated users (protected by RLS)

**No code changes needed** - just enable RLS as shown in Step 1!

### Option B: Create Custom Database User (Advanced)

If you want true user-level isolation, you'll need to:

1. **Create a custom JWT issuer** (complex, requires custom auth)
2. **Or use Supabase's custom API keys** (if available in your plan)
3. **Or use the anon key with permissive RLS** (less secure)

**For most cases, Option A is recommended** - service role + RLS provides good security with minimal complexity.

---

## 🔄 Step 3: Update Your Scraper Code

### 3.1 Update Database Connection

**File: `scraper/db.py` (or equivalent)**

**Before (Service Role):**
```python
class SupabaseREST:
    def __init__(self, url: str = None, key: str = None) -> None:
        self.base_url = (url or os.getenv('SUPABASE_URL', '')).rstrip("/")
        self.key = key or os.getenv('SUPABASE_KEY', '')
        self.session.headers.update({
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        })
```

**After (Limited User with Basic Auth):**
```python
import base64
import os

class SupabaseREST:
    def __init__(self, url: str = None, key: str = None, db_user: str = None, db_password: str = None) -> None:
        self.base_url = (url or os.getenv('SUPABASE_URL', '')).rstrip("/")
        # Use anon key for apikey header
        self.anon_key = key or os.getenv('SUPABASE_ANON_KEY', '')
        
        # Get database user credentials
        db_user = db_user or os.getenv('SUPABASE_DB_USER', 'scraper_user')
        db_password = db_password or os.getenv('SUPABASE_DB_PASSWORD', '')
        
        # Create Basic Auth header
        credentials = f"{db_user}:{db_password}"
        basic_auth = base64.b64encode(credentials.encode()).decode()
        
        self.session.headers.update({
            "apikey": self.anon_key,  # Anon key, not service role
            "Authorization": f"Basic {basic_auth}",  # Basic auth instead of Bearer
            "Content-Type": "application/json",
        })
```

### 3.2 Alternative: Use Service Role with Limited Scope

If Basic Auth doesn't work well with your setup, you can keep using service role but add additional security:

1. **Enable RLS** (already done in Step 1)
2. **Create a service role policy** that's more restrictive
3. **Monitor access** via Supabase logs

This is less secure than limited user but better than current setup.

---

## 🔐 Step 4: Update GitHub Secrets

### 4.1 Add New Secrets

Go to your GitHub repository → **Settings** → **Secrets and variables** → **Actions**

**Add these secrets:**

| Secret Name | Value | Description |
|------------|-------|-------------|
| `SUPABASE_ANON_KEY` | Your Supabase anon key | Public anon key (safe to expose) |
| `SUPABASE_DB_USER` | `scraper_user` | Database username |
| `SUPABASE_DB_PASSWORD` | The password you set in Step 1 | Database password |

### 4.2 Update Existing Secrets (Optional)

You can keep `SUPABASE_KEY` for backward compatibility, but update your code to use the new secrets.

---

## 📝 Step 5: Update Environment Variables

### 5.1 Local Development (`.env` file)

```env
# Supabase Configuration
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
SUPABASE_DB_USER=scraper_user
SUPABASE_DB_PASSWORD=your_secure_password_here

# Legacy (can remove after migration)
# SUPABASE_KEY=your_service_role_key_here  # No longer needed
```

### 5.2 GitHub Actions Workflow

**File: `.github/workflows/scrape.yml`**

```yaml
env:
  SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
  SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_ANON_KEY }}
  SUPABASE_DB_USER: ${{ secrets.SUPABASE_DB_USER }}
  SUPABASE_DB_PASSWORD: ${{ secrets.SUPABASE_DB_PASSWORD }}
  # Remove or comment out:
  # SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
```

---

## ✅ Step 6: Test the Migration

### 6.1 Test Locally

```bash
# Test with limited user
python -m scraper.cli --limit 5

# Verify products were inserted
python debug_db.py  # or your verification script
```

### 6.2 Test in GitHub Actions

1. Push your changes
2. Manually trigger the workflow
3. Check logs for successful inserts
4. Verify products in Supabase dashboard

### 6.3 Verify Security

```sql
-- Check user permissions
SELECT 
    grantee, 
    privilege_type 
FROM information_schema.role_table_grants 
WHERE table_name = 'products' 
AND grantee = 'scraper_user';

-- Should show: INSERT, UPDATE, SELECT, DELETE only
```

---

## 🚨 Troubleshooting

### Error: "permission denied for table products"

**Solution:** Make sure you ran the `GRANT` statements in Step 1.2

### Error: "role scraper_user does not exist"

**Solution:** The user wasn't created. Re-run Step 1.2

### Error: "authentication failed"

**Solution:** 
- Check password in GitHub Secrets matches the one you set
- Verify username is correct (`scraper_user`)
- Ensure Basic Auth encoding is correct

### Error: "RLS policy violation"

**Solution:** Make sure you created the RLS policy in Step 1.2 (Step 3)

### Products not inserting

**Solution:**
- Check Supabase logs for detailed error messages
- Verify RLS is enabled and policy exists
- Test with a single product first: `--limit 1`

---

## 📊 Security Comparison

| Aspect | Service Role | Limited User |
|--------|-------------|--------------|
| **Database Access** | Full (all tables, functions) | Products table only |
| **Security Risk** | High (nuclear option) | Low (limited scope) |
| **RLS Bypass** | Yes (bypasses all RLS) | Only for products table |
| **Audit Trail** | Limited | Better (user-specific) |
| **If Compromised** | Can delete entire database | Can only affect products |

---

## 🔄 Rollback Plan

If something goes wrong, you can rollback:

1. **Revert code changes** (git revert)
2. **Restore old GitHub Secrets** (use service role key)
3. **Disable limited user** (optional):
   ```sql
   REVOKE ALL ON public.products FROM scraper_user;
   DROP USER scraper_user;
   ```

---

## 📚 Additional Resources

- [Supabase RLS Documentation](https://supabase.com/docs/guides/auth/row-level-security)
- [PostgreSQL User Management](https://www.postgresql.org/docs/current/user-manag.html)
- [PostgREST Authentication](https://postgrest.org/en/stable/auth.html)

---

## ✅ Migration Checklist

- [ ] Created `scraper_user` in Supabase
- [ ] Set secure password and saved it
- [ ] Enabled RLS on products table
- [ ] Created RLS policy for scraper_user
- [ ] Updated scraper code to use Basic Auth
- [ ] Updated GitHub Secrets
- [ ] Updated `.env` file
- [ ] Updated GitHub Actions workflow
- [ ] Tested locally with `--limit 5`
- [ ] Tested in GitHub Actions
- [ ] Verified products are inserting correctly
- [ ] Verified security (user can't access other tables)
- [ ] Documented changes in your project

---

## 🎉 Success!

Once all steps are complete, your scraper will:
- ✅ Work exactly as before
- ✅ Be significantly more secure
- ✅ Follow principle of least privilege
- ✅ Have better audit trails

**Questions?** Check the troubleshooting section or review Supabase logs for detailed error messages.

