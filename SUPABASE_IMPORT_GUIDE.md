# How We Import to Supabase (PostgREST)

This scraper imports products into Supabase using the **PostgREST REST API** directly (no Supabase JS client). Use this as a reference if your scraper’s Supabase import isn’t working.

---

## 1. Environment variables

Set these (e.g. in `.env` or the environment):

- **`SUPABASE_URL`** – Project URL, no trailing slash (e.g. `https://xxxx.supabase.co`)
- **`SUPABASE_KEY`** – Project API key (anon/service key with access to the `products` table)

Load `.env` if you use it (e.g. with `python-dotenv`):

```python
from dotenv import load_dotenv
load_dotenv(override=False)
```

---

## 2. How we call Supabase (HTTP, not SDK)

We use **plain HTTP** to the PostgREST endpoint:

- **Base URL:** `{SUPABASE_URL}/rest/v1`
- **Products table:** `POST {SUPABASE_URL}/rest/v1/products`

**Headers on every request:**

```python
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}
```

Use a session so headers are set once:

```python
import requests
session = requests.Session()
session.headers.update({
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
})
```

---

## 3. Upsert = POST + Prefer header

We **upsert** (insert or update on conflict) with a single header:

```python
POST {base_url}/rest/v1/products
Prefer: resolution=merge-duplicates,return=minimal
Body: JSON array of product objects
```

- **`resolution=merge-duplicates`** – on unique constraint conflict, merge/update the row.
- **`return=minimal`** – no response body (smaller and faster).

Your table must have a **unique constraint** that PostgREST can use (e.g. on `(source, product_url)` or on `id`). We use primary key `id` and unique on `(source, product_url)`.

---

## 4. Critical: same keys in every object

PostgREST expects **all objects in one request to have the same set of keys**. If one product has `description` and another doesn’t, the request can fail.

**Fix: normalize each row to the same keys**, using `None` for missing values:

```python
# Collect all keys that appear in any product
all_keys = set()
for p in products:
    all_keys.update(p.keys())

# Each row must have every key (use None if missing)
normalized = []
for p in products:
    normalized.append({key: p.get(key) for key in all_keys})
# Then POST normalized, not products
```

---

## 5. Stable `id` (primary key)

We use a **deterministic id** so the same product always gets the same row:

```python
import hashlib
id_string = f"{source}:{product_url}"
product_id = hashlib.sha256(id_string.encode("utf-8")).hexdigest()
# Use product_id as the "id" field for each product
```

Your schema may use a different unique key; the important part is that the key is stable per product.

---

## 6. Batching and retries

- Send products in **chunks** (e.g. 50–100 per request) to avoid timeouts and huge payloads.
- If a batch fails (e.g. 409, 500, or trigger/function errors), **retry that batch one row at a time** so one bad row doesn’t block the rest.

Example flow:

```python
chunk_size = 100
for i in range(0, len(normalized_products), chunk_size):
    chunk = normalized_products[i : i + chunk_size]
    resp = session.post(
        f"{base_url}/rest/v1/products",
        headers={**session.headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
        data=json.dumps(chunk),
        timeout=60,
    )
    if resp.status_code not in (200, 201, 204):
        # Optionally retry each item in chunk individually
        ...
```

---

## 7. Minimal working example

```python
import os
import json
import hashlib
import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY")

session = requests.Session()
session.headers.update({
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
})

def upsert_products(products: list[dict]) -> bool:
    if not products:
        return True
    # 1) Same keys everywhere
    all_keys = set()
    for p in products:
        all_keys.update(p.keys())
    normalized = [{k: p.get(k) for k in all_keys} for p in products]
    # 2) Upsert in chunks
    endpoint = f"{SUPABASE_URL}/rest/v1/products"
    prefer = "resolution=merge-duplicates,return=minimal"
    for i in range(0, len(normalized), 100):
        chunk = normalized[i : i + 100]
        r = session.post(endpoint, headers={"Prefer": prefer}, data=json.dumps(chunk), timeout=60)
        if r.status_code not in (200, 201, 204):
            print(f"Failed: {r.status_code} {r.text}")
            return False
    return True

# Example: one product with required fields
source = "my_scraper"
product_url = "https://example.com/product/123"
product = {
    "id": hashlib.sha256(f"{source}:{product_url}".encode()).hexdigest(),
    "source": source,
    "product_url": product_url,
    "title": "Example product",
    "image_url": "https://example.com/image.jpg",
    "price": "29.99USD",
    "brand": None,
    "description": None,
    # ... all other columns your table has, use None if missing
}
upsert_products([product])
```

---

## 8. Common issues

| Problem | What to do |
|--------|------------|
| 401 Unauthorized | Wrong or missing `SUPABASE_KEY`; check `apikey` and `Authorization: Bearer` |
| 404 | Wrong URL or table name; use `{SUPABASE_URL}/rest/v1/products` (table name in path) |
| 409 / unique violation | Ensure `Prefer: resolution=merge-duplicates` and your unique constraint matches the keys you send (e.g. `id` or `(source, product_url)`) |
| “All object keys must match” / schema error | Normalize so every object in the same request has exactly the same keys (use `None` for missing) |
| Timeouts / large payloads | Send smaller chunks (e.g. 50–100 rows per POST) |
| Triggers/functions failing on insert | Retry failed batches row-by-row and skip or log rows that still fail |

---

## 9. Where this is implemented here

- **Connection and upsert logic:** `scraper/db.py` (`SupabaseREST` class, `upsert_products`, `_format_product_for_db`)
- **Env loading:** `scraper/config.py` (`load_env`, `get_supabase_env`)
- **Usage:** `scraper/cli.py` (builds product rows, then calls `db.upsert_products(collected)`)

You can copy or adapt `db.py` and the normalization + batching pattern for your scraper.
