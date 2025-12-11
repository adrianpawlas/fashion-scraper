# Migration Guide: Service Role → Anon Key

## 🎯 Overview

This guide shows you how to replace the **service role key** with the **anon public key** for your scrapers. This is more secure for public repositories, but requires proper RLS (Row Level Security) policies.

---

## ⚠️ Important Considerations

### Service Role vs Anon Key

| Aspect | Service Role Key | Anon Key |
|--------|-----------------|----------|
| **Visibility** | Must be secret | Safe to expose publicly |
| **RLS Bypass** | Yes (bypasses all RLS) | No (subject to RLS policies) |
| **Use Case** | Server-side operations | Client-side operations |
| **Security** | High risk if exposed | Lower risk (but needs RLS) |
| **Recommended For** | Backend services, scrapers | Frontend apps, public APIs |

### ⚠️ Key Point

**For server-side scrapers (like GitHub Actions), service role is actually the recommended approach** because:
- It's already secure (encrypted in GitHub Secrets)
- It bypasses RLS (needed for bulk operations)
- It's designed for server-side use

**However**, if you want to use anon key (for extra security in public repos), you can do it with proper RLS policies.

---

## 🔧 Step 1: Enable RLS and Create Policies

### 1.1 Enable RLS

Run this in Supabase SQL Editor:

```sql
-- Enable RLS on products table
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
```

### 1.2 Create Policy for Scraper Inserts

You have two options:

#### Option A: Allow Anonymous Inserts (Less Secure)

```sql
-- Allow anonymous users to insert products
-- WARNING: This allows ANYONE with anon key to insert products!
CREATE POLICY "Allow anonymous inserts" 
ON public.products
FOR INSERT 
TO anon
WITH CHECK (true);

-- Allow anonymous users to update products
CREATE POLICY "Allow anonymous updates" 
ON public.products
FOR UPDATE 
TO anon
USING (true)
WITH CHECK (true);

-- Allow anonymous users to read products (if needed)
CREATE POLICY "Allow anonymous reads" 
ON public.products
FOR SELECT 
TO anon
USING (true);
```

**⚠️ Security Risk**: Anyone with your anon key can insert products. Only use this if:
- Your anon key is in GitHub Secrets (not exposed)
- You're okay with the risk
- You have monitoring in place

#### Option B: Use Secret Header (More Secure) ✅ Recommended

This approach uses a custom header to verify the request is from your scraper:

```sql
-- Create a function to check for scraper secret header
CREATE OR REPLACE FUNCTION check_scraper_secret()
RETURNS boolean AS $$
BEGIN
  -- Check if the request has a custom header with scraper secret
  -- This requires PostgREST to pass headers, which Supabase does via current_setting
  -- Note: This is a simplified version - actual implementation may vary
  RETURN current_setting('request.headers', true)::json->>'x-scraper-secret' = 'YOUR_SECRET_HERE';
EXCEPTION
  WHEN OTHERS THEN
    RETURN false;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Policy that checks for scraper secret
CREATE POLICY "Scraper inserts with secret" 
ON public.products
FOR INSERT 
TO anon
WITH CHECK (
  current_setting('request.headers', true)::json->>'x-scraper-secret' = 'YOUR_SECRET_HERE'
);

CREATE POLICY "Scraper updates with secret" 
ON public.products
FOR UPDATE 
TO anon
USING (
  current_setting('request.headers', true)::json->>'x-scraper-secret' = 'YOUR_SECRET_HERE'
)
WITH CHECK (
  current_setting('request.headers', true)::json->>'x-scraper-secret' = 'YOUR_SECRET_HERE'
);
```

**Note**: Supabase's PostgREST may not expose headers this way. A simpler approach is Option C below.

#### Option C: Use Service Role with Anon Key (Hybrid) ✅ Best Balance

Keep using service role key (it's already secure in GitHub Secrets), but also enable RLS:

```sql
-- Enable RLS
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;

-- Service role bypasses RLS automatically (no policy needed)
-- Mobile app uses authenticated users (protected by existing policies)
-- Anon key can read products (if you want public access)
CREATE POLICY "Public read access" 
ON public.products
FOR SELECT 
TO anon
USING (true);
```

**This is the recommended approach** - service role for scrapers, RLS for everything else.

---

## 🔄 Step 2: Update Scraper Code (If Using Anon Key)

### 2.1 Update Database Connection

**File: `scraper/db.py`**

**Before (Service Role):**
```python
def __init__(self, url: str = None, key: str = None):
    self.base_url = (url or os.getenv('SUPABASE_URL', '')).rstrip("/")
    self.key = key or os.getenv('SUPABASE_KEY', '')  # Service role key
    self.session.headers.update({
        "apikey": self.key,
        "Authorization": f"Bearer {self.key}",
        "Content-Type": "application/json",
    })
```

**After (Anon Key with Secret Header - Option B):**
```python
def __init__(self, url: str = None, key: str = None, scraper_secret: str = None):
    self.base_url = (url or os.getenv('SUPABASE_URL', '')).rstrip("/")
    self.key = key or os.getenv('SUPABASE_ANON_KEY', '')  # Anon key instead
    scraper_secret = scraper_secret or os.getenv('SCRAPER_SECRET', '')
    self.session.headers.update({
        "apikey": self.key,
        "Authorization": f"Bearer {self.key}",
        "Content-Type": "application/json",
        "X-Scraper-Secret": scraper_secret,  # Custom header for verification
    })
```

**After (Anon Key Only - Option A):**
```python
def __init__(self, url: str = None, key: str = None):
    self.base_url = (url or os.getenv('SUPABASE_URL', '')).rstrip("/")
    self.key = key or os.getenv('SUPABASE_ANON_KEY', '')  # Anon key instead
    self.session.headers.update({
        "apikey": self.key,
        "Authorization": f"Bearer {self.key}",
        "Content-Type": "application/json",
    })
```

### 2.2 Update Environment Variables

**File: `.env`**
```env
# Change from service role to anon key
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here  # Changed from SUPABASE_KEY

# Optional: If using secret header approach
SCRAPER_SECRET=your_secret_here
```

### 2.3 Update GitHub Secrets

Go to **GitHub Repository → Settings → Secrets → Actions**

**Update:**
- `SUPABASE_KEY` → `SUPABASE_ANON_KEY` (use your anon key)
- Add `SCRAPER_SECRET` (if using Option B)

**Or keep both:**
- `SUPABASE_KEY` (service role - for backward compatibility)
- `SUPABASE_ANON_KEY` (anon key - new)

---

## ✅ Step 3: Test the Migration

### 3.1 Test Locally

```bash
# Test with anon key
export SUPABASE_ANON_KEY=your_anon_key
python -m scraper.cli --limit 5

# Verify products were inserted
python debug_db.py
```

### 3.2 Test in GitHub Actions

1. Update GitHub Secrets
2. Push changes
3. Manually trigger workflow
4. Check logs for successful inserts

---

## 🚨 Troubleshooting

### Error: "new row violates row-level security policy"

**Solution**: 
- Make sure RLS is enabled
- Check that you created the INSERT policy
- Verify the policy allows anonymous inserts

### Error: "permission denied for table products"

**Solution**:
- Check RLS policies exist
- Verify policy is for `anon` role
- Ensure policy has `WITH CHECK (true)` for INSERT

### Products not inserting

**Solution**:
- Check Supabase logs for detailed errors
- Verify anon key is correct
- Test with a single product: `--limit 1`
- Check RLS policies are correct

---

## 📊 Security Comparison

| Approach | Security | Complexity | Recommended |
|----------|----------|------------|-------------|
| **Service Role + RLS** | High | Low | ✅ Yes |
| **Anon Key + RLS (Secret Header)** | Medium-High | Medium | ⚠️ If you need it |
| **Anon Key + RLS (Open)** | Low | Low | ❌ Not recommended |

---

## 💡 Recommendation

**For your use case (GitHub Actions scraper):**

1. **Keep service role key** (it's already secure in GitHub Secrets)
2. **Enable RLS** (adds protection layer)
3. **Service role bypasses RLS** (needed for bulk operations)
4. **Mobile app protected by RLS** (authenticated users)

**Why?**
- ✅ Service role is designed for server-side operations
- ✅ GitHub Secrets are encrypted (not exposed)
- ✅ RLS adds protection for mobile app
- ✅ Zero code changes needed
- ✅ Best security/complexity balance

**Only switch to anon key if:**
- You're exposing the key publicly (not recommended)
- You want extra security layers
- You're okay with managing RLS policies

---

## ✅ Migration Checklist

- [ ] Decided on approach (Service Role + RLS vs Anon Key)
- [ ] Enabled RLS on products table
- [ ] Created appropriate RLS policies
- [ ] Updated scraper code (if using anon key)
- [ ] Updated `.env` file
- [ ] Updated GitHub Secrets
- [ ] Tested locally with `--limit 5`
- [ ] Tested in GitHub Actions
- [ ] Verified products are inserting correctly
- [ ] Verified security (anon key can't access other tables)

---

## 🎉 Success!

Once complete, your scraper will:
- ✅ Use anon key (if you chose that path)
- ✅ Be protected by RLS policies
- ✅ Work exactly as before
- ✅ Be more secure for public repositories

**Questions?** Check Supabase logs for detailed error messages or review the RLS policies.

