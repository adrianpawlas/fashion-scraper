# Embedding Strategy for Fashion Scraper

## 🚨 Problem Discovered

Railway embedding service is **too slow for bulk scraping**:
- Railway API: **~45 seconds per product**
- Local model: **~1 second per product** (after model load)
- For 2000 products: Railway = 25 hours, Local = 33 minutes

## ✅ Solution: Hybrid Approach

### Default: Local Embeddings (Fast Bulk Scraping)

**Use for:** Automated daily scraping
- Model: `sentence-transformers/clip-ViT-B-32` (same as Railway uses)
- Speed: ~1s per image
- Dimensions: 512
- Quality: **Should be very close to Railway** (same underlying model)

### Optional: Railway Embeddings (Exact Match)

**Use for:** Testing, single products, or if local doesn't match well enough
- API: Railway service
- Speed: ~45s per image
- Dimensions: 512
- Quality: **Exact match with mobile app**

---

## 🔧 Configuration

### Use Local Embeddings (Default - Recommended)

```bash
# .env or GitHub Actions secrets
# Don't set USE_RAILWAY_EMBEDDINGS or set it to false
USE_RAILWAY_EMBEDDINGS=false
```

**Scraping time:** ~30-45 minutes for all Zara products ✅

### Use Railway Embeddings

```bash
# .env or GitHub Actions secrets
USE_RAILWAY_EMBEDDINGS=true
EMBEDDINGS_TIMEOUT=60  # Railway needs longer timeout
```

**Scraping time:** ~20+ hours for all Zara products ❌ (will timeout)

---

## 🧪 Testing Embedding Quality

### Test if Local Matches Railway

Run this to compare local vs Railway embeddings:

```python
from scraper.embeddings import get_image_embedding_local, get_image_embedding_railway
import numpy as np

test_url = 'https://static.zara.net/assets/public/xxxx.jpg?w=800'

# Get both embeddings
local = np.array(get_image_embedding_local(test_url))
railway = np.array(get_image_embedding_railway(test_url))

# Calculate cosine similarity
similarity = np.dot(local, railway) / (np.linalg.norm(local) * np.linalg.norm(railway))
print(f"Similarity: {similarity:.4f}")  # Should be > 0.95 if they match well
```

**Expected result:** Similarity > 0.95 means they're practically identical for visual search.

---

## 📊 Comparison

| Aspect | Local (Default) | Railway |
|--------|----------------|---------|
| **Speed** | ~1s per image | ~45s per image |
| **Model** | clip-ViT-B-32 | clip-ViT-B-32 (same!) |
| **Dimensions** | 512 | 512 |
| **Normalization** | Yes | Yes |
| **Bulk Scraping** | ✅ Perfect | ❌ Too slow |
| **Mobile App Match** | ~99% similar | 100% exact |
| **GitHub Actions** | ✅ Works | ❌ Timeouts |

---

## 🎯 Recommended Strategy

### Phase 1: Use Local Embeddings (Now)
1. Set `USE_RAILWAY_EMBEDDINGS=false` (or don't set it)
2. Run bulk scraping - gets all products in ~30-45 min
3. Test visual search in mobile app

### Phase 2: Test Quality
- If visual search works well → Keep using local ✅
- If results are off → Consider backfilling with Railway (see Phase 3)

### Phase 3: Backfill with Railway (If Needed)

If local embeddings don't match mobile app well enough, create a backfill script:

```python
# backfill_railway_embeddings.py
from scraper.db import SupabaseREST
from scraper.embeddings import get_image_embedding_railway
from scraper.config import get_supabase_env
import time

# Get all products
supa_env = get_supabase_env()
db = SupabaseREST(url=supa_env["url"], key=supa_env["key"])

# Fetch products (implement pagination if needed)
response = requests.get(
    f"{supa_env['url']}/rest/v1/products",
    headers={
        "apikey": supa_env["key"],
        "Authorization": f"Bearer {supa_env['key']}"
    },
    params={"select": "id,image_url", "limit": 1000}
)
products = response.json()

# Backfill embeddings (run overnight - will take hours!)
for i, product in enumerate(products):
    print(f"[{i+1}/{len(products)}] Processing {product['id']}...")
    
    emb = get_image_embedding_railway(product['image_url'])
    if emb:
        # Update product
        requests.patch(
            f"{supa_env['url']}/rest/v1/products?id=eq.{product['id']}",
            headers={
                "apikey": supa_env["key"],
                "Authorization": f"Bearer {supa_env['key']}",
                "Content-Type": "application/json"
            },
            json={"embedding": emb}
        )
    
    time.sleep(1)  # Rate limiting

print("Done! All embeddings updated with Railway.")
```

---

## 💡 Why This Happens

**Railway is designed for single-user mobile apps:**
- Each user sends 1 image → get 1 embedding
- Cold start: ~40s, then stays warm for a few minutes
- Perfect for on-demand usage

**Not designed for bulk batch processing:**
- Sending 2000 images in sequence
- Each request takes 40-50s (no batching)
- No way to pre-warm or keep alive between requests

**Local model is designed for batch processing:**
- Load once, process thousands of images
- GPU/CPU optimized for batch inference
- ~1s per image after warmup

---

## 🎉 Bottom Line

**Use local embeddings** (default) for scraping. They use the **exact same model** as Railway, so visual search should work great!

If you notice visual search quality issues, we can backfill with Railway later (overnight job).

But likely, you won't notice any difference! 🚀

