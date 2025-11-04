import os
from typing import Optional
from time import sleep, time
from io import BytesIO

import requests
from PIL import Image
from sentence_transformers import SentenceTransformer


RAILWAY_EMBED_URL = 'https://finds-user-embedding-production.up.railway.app/embed'

# Use local embeddings by default for bulk scraping (much faster)
# Set USE_RAILWAY_EMBEDDINGS=true to use Railway API (slower but matches mobile app exactly)
USE_RAILWAY = os.getenv("USE_RAILWAY_EMBEDDINGS", "false").lower() in ("true", "1", "yes")

_model: Optional[SentenceTransformer] = None
_model_error: bool = False


def _get_model() -> Optional[SentenceTransformer]:
    global _model, _model_error
    if _model is None and not _model_error:
        model_name = os.getenv("EMBEDDINGS_MODEL", "BAAI/bge-large-en-v1.5")
        try:
            print(f"[MODEL] Loading {model_name}...")
            start_time = time()
            _model = SentenceTransformer(model_name)
            load_time = time() - start_time
            print(f"[MODEL] Loaded {model_name} in {load_time:.1f}s")
        except Exception as e:
            print(f"[ERROR] Failed to load model {model_name}: {e}")
            print(f"        Make sure sentencepiece and protobuf are installed")
            _model_error = True
            return None
    return _model


def get_image_embedding_local(image_url: str) -> Optional[list]:
    """Get embedding using local sentence-transformers model (fast for bulk)."""
    if not image_url or not str(image_url).strip():
        return None

    model = _get_model()
    if model is None:
        return None

    raw_url = str(image_url).strip()

    # Skip data URLs (base64 embedded images) - these are placeholders
    if raw_url.startswith("data:"):
        print(f"[SKIP] Data URL placeholder: {raw_url[:50]}...")
        return None

    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url

    # Clean up malformed URLs (remove extra slashes)
    if "//" in raw_url and not raw_url.startswith("http"):
        # Fix URLs like "https://domain.com//path" -> "https://domain.com/path"
        parts = raw_url.split("//", 1)
        if len(parts) == 2:
            protocol = parts[0]
            rest = parts[1]
            # Remove consecutive slashes in the path part
            rest = "/".join(filter(None, rest.split("/")))
            raw_url = protocol + "//" + rest

    if "{width}" in raw_url:
        raw_url = raw_url.replace("{width}", "800", 1)
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        # Special handling for Zara images
        if "zara" in raw_url.lower():
            headers["Referer"] = "https://www.zara.com/"
            headers["Accept"] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
            headers["Sec-Fetch-Dest"] = "image"
            headers["Sec-Fetch-Mode"] = "no-cors"
            headers["Sec-Fetch-Site"] = "same-site"
        
        resp = requests.get(raw_url, headers=headers, timeout=15)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        vec = model.encode([img], normalize_embeddings=True)
        return vec[0].tolist()
    except Exception as e:
        print(f"[ERROR] Local embedding failed: {str(e)[:80]}")
        print(f"        URL: {raw_url}")
        return None


def get_image_embedding_railway(image_url: str) -> Optional[list]:
    """
    Get 1024-dim embedding from Railway service.
    WARNING: Very slow (~40-50s per request) - only use for single products or testing.
    """
    if not image_url or not str(image_url).strip():
        return None

    raw_url = str(image_url).strip()

    # Skip data URLs (base64 embedded images) - these are placeholders
    if raw_url.startswith("data:"):
        print(f"[SKIP] Data URL placeholder: {raw_url[:50]}...")
        return None

    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url

    # Clean up malformed URLs (remove extra slashes)
    if "//" in raw_url and not raw_url.startswith("http"):
        # Fix URLs like "https://domain.com//path" -> "https://domain.com/path"
        parts = raw_url.split("//", 1)
        if len(parts) == 2:
            protocol = parts[0]
            rest = parts[1]
            # Remove consecutive slashes in the path part
            rest = "/".join(filter(None, rest.split("/")))
            raw_url = protocol + "//" + rest

    if "{width}" in raw_url:
        raw_url = raw_url.replace("{width}", "800", 1)

    timeout_seconds = int(os.getenv("EMBEDDINGS_TIMEOUT", "60"))
    start_time = time()
    
    try:
        response = requests.post(
            RAILWAY_EMBED_URL,
            json={
                'image': raw_url,
                'type': 'url'
            },
            timeout=timeout_seconds
        )
        
        elapsed = time() - start_time
        response.raise_for_status()
        data = response.json()

        embedding = data.get('embedding')
        if not embedding:
            raise ValueError("No embedding in response")

        print(f"[RAILWAY_DEBUG] Received embedding of type {type(embedding)}, length {len(embedding) if hasattr(embedding, '__len__') else 'N/A'}")

        # Accept both 512 and 1024 dimensions (transition period)
        if len(embedding) not in [512, 1024]:
            raise ValueError(f"Expected 512 or 1024-dim, got {len(embedding)}")

        # Pad 512-dim embeddings to 1024-dim for database compatibility
        if len(embedding) == 512:
            print(f"[RAILWAY_PAD] Padding 512-dim to 1024-dim - {raw_url[:60]}")
            # Ensure it's a list that can be extended
            if not isinstance(embedding, list):
                embedding = list(embedding)
            # Pad with zeros to reach 1024 dimensions
            embedding.extend([0.0] * 512)
            print(f"[RAILWAY_PAD] After padding: {len(embedding)} dimensions")
        else:
            print(f"[RAILWAY_OK] Already {len(embedding)}-dim - {raw_url[:60]}")

        print(f"[RAILWAY_OK] {elapsed:.1f}s - {raw_url[:60]}")
        return embedding

    except requests.exceptions.Timeout:
        print(f"[RAILWAY_TIMEOUT] {timeout_seconds}s - {raw_url[:60]}")
        return None
    except Exception as e:
        print(f"[RAILWAY_ERROR] {str(e)[:80]} - {raw_url[:60]}")
        return None


def get_image_embedding(image_url: str, max_retries: int = 3) -> Optional[list]:
    """
    Get image embedding with automatic fallback and retry logic.
    - If USE_RAILWAY_EMBEDDINGS=true: Use Railway API directly (1024-dim, slow but reliable)
    - Otherwise: Try local model first (fast), fallback to Railway API if local fails
    - Railway API returns 512-dim embeddings that get padded to 1024-dim for database compatibility
    - Implements exponential backoff retry for reliability
    """
    if USE_RAILWAY:
        # If explicitly set to use Railway, skip local attempt
        return get_image_embedding_railway(image_url)

    # Try local first with retries (fast)
    for attempt in range(max_retries):
        if attempt > 0:
            # Exponential backoff: 1s, 2s, 4s
            sleep_time = 2 ** (attempt - 1)
            print(f"[RETRY] Local embedding attempt {attempt + 1}/{max_retries} after {sleep_time}s...")
            sleep(sleep_time)

        embedding = get_image_embedding_local(image_url)
        if embedding is not None:
            return embedding

    # If all local attempts failed, fallback to Railway with retries (slow but more reliable)
    print(f"[FALLBACK] All local attempts failed, trying Railway API...")
    for attempt in range(max_retries):
        if attempt > 0:
            # Longer exponential backoff for Railway: 2s, 4s, 8s
            sleep_time = 2 ** attempt
            print(f"[RETRY] Railway API attempt {attempt + 1}/{max_retries} after {sleep_time}s...")
            sleep(sleep_time)

        embedding = get_image_embedding_railway(image_url)
        if embedding is not None:
            return embedding

    print(f"[FAILED] All embedding attempts failed for: {image_url[:60]}")
    return None
