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
        model_name = os.getenv("EMBEDDINGS_MODEL", "sentence-transformers/clip-ViT-B-32")
        try:
            _model = SentenceTransformer(model_name)
        except Exception as e:
            print(f"[ERROR] Failed to load model {model_name}: {e}")
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
    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url
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
    Get 512-dim embedding from Railway service.
    WARNING: Very slow (~40-50s per request) - only use for single products or testing.
    """
    if not image_url or not str(image_url).strip():
        return None

    raw_url = str(image_url).strip()
    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url
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

        if len(embedding) != 512:
            raise ValueError(f"Expected 512-dim, got {len(embedding)}")

        print(f"[RAILWAY_OK] {elapsed:.1f}s - {raw_url[:60]}")
        return embedding

    except requests.exceptions.Timeout:
        print(f"[RAILWAY_TIMEOUT] {timeout_seconds}s - {raw_url[:60]}")
        return None
    except Exception as e:
        print(f"[RAILWAY_ERROR] {str(e)[:80]} - {raw_url[:60]}")
        return None


def get_image_embedding(image_url: str) -> Optional[list]:
    """
    Get image embedding.
    - Default: Local model (fast, ~0.5s per image, good enough for visual search)
    - If USE_RAILWAY_EMBEDDINGS=true: Railway API (slow, ~45s per image, exact match with mobile)
    """
    if USE_RAILWAY:
        return get_image_embedding_railway(image_url)
    else:
        return get_image_embedding_local(image_url)
