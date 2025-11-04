import os
from typing import Optional
from time import sleep, time
from io import BytesIO

import requests
from PIL import Image
from sentence_transformers import SentenceTransformer

_model: Optional[SentenceTransformer] = None
_model_error: bool = False


def _get_model() -> Optional[SentenceTransformer]:
    global _model, _model_error
    if _model is None and not _model_error:
        model_name = os.getenv("EMBEDDINGS_MODEL", "google/siglip-large-patch16-384")
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


def get_image_embedding(image_url: str, max_retries: int = 3) -> Optional[list]:
    """Get embedding using local HuggingFace model only (1024-dim SigLIP)."""
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

    for attempt in range(max_retries):
        if attempt > 0:
            # Exponential backoff: 1s, 2s, 4s
            sleep_time = 2 ** (attempt - 1)
            print(f"[RETRY] Local embedding attempt {attempt + 1}/{max_retries} after {sleep_time}s...")
            sleep(sleep_time)

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
            vec = model.encode(img, normalize_embeddings=True)
            return vec.tolist()
        except Exception as e:
            print(f"[ERROR] Local embedding failed: {str(e)[:80]}")
            print(f"        URL: {raw_url}")
    print(f"[FAILED] All local embedding attempts failed for: {image_url[:60]}")
    return None
