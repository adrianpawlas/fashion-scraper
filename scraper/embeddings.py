import os
from typing import Optional
from time import sleep

from io import BytesIO
import requests
from PIL import Image
from sentence_transformers import SentenceTransformer
from .config import get_default_headers


_model: Optional[SentenceTransformer] = None
_model_error: bool = False


def _get_model() -> SentenceTransformer:
    global _model, _model_error
    if _model is None and not _model_error:
    	# Use a widely available public model by default; allow override via env
    	# Prefer a 512-d model (CLIP ViT-B/32) for smaller vectors and speed
    	_model_name = os.getenv("EMBEDDINGS_MODEL") or "sentence-transformers/clip-ViT-B-32"
        try:
            _model = SentenceTransformer(_model_name)
        except Exception:
            # Mark failure so we don't retry repeatedly
            _model_error = True
            raise
    return _model


def get_image_embedding(image_url: str, model: Optional[str] = None) -> Optional[list]:
    if not image_url or not str(image_url).strip():
        return None

    # Prepare candidate image URLs (handle protocol-relative and width placeholders)
    raw_url = str(image_url).strip()
    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url

    # Width candidates to try for sites like Zara that use {width}
    default_widths = os.getenv("ZARA_IMAGE_WIDTHS", "800,1200,2000").split(",")
    default_widths = [w.strip() for w in default_widths if w.strip()]
    if "{width}" in raw_url:
        candidate_urls = [raw_url.replace("{width}", w, 1) for w in default_widths]
    else:
        candidate_urls = [raw_url]

    retries = max(1, int(os.getenv("EMBEDDINGS_RETRIES", "3")))
    backoff_seconds = float(os.getenv("EMBEDDINGS_RETRY_BACKOFF", "0.6"))

    try:
        mdl = _get_model() if model is None else SentenceTransformer(model)
    except Exception:
        return None

    # Build base headers and add referer for Zara
    def _headers_for(u: str) -> dict:
        h = get_default_headers()
        if "zara" in u:
            h = {**h, "Referer": "https://www.zara.com/"}
        return h

    # Try multiple URLs and retries with small backoff to reduce transient failures
    for attempt in range(retries):
        for url in candidate_urls:
            try:
                resp = requests.get(url, headers=_headers_for(url), timeout=45)
                resp.raise_for_status()
                img = Image.open(BytesIO(resp.content)).convert("RGB")
                vec = mdl.encode([img], normalize_embeddings=True)
                return vec[0].tolist()
            except Exception:
                # transient failure; try next candidate or retry loop
                pass
        # backoff before the next round of attempts
        if attempt < retries - 1:
            try:
                sleep(backoff_seconds * (attempt + 1))
            except Exception:
                pass
    return None


