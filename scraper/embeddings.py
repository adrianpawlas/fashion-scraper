import os
from typing import Optional

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
        # Prefer a 768-d model to match common DB vector sizes
        _model_name = os.getenv("EMBEDDINGS_MODEL", "sentence-transformers/clip-ViT-L-14")
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
    # Replace Zara-style width placeholder with a practical width
    url = str(image_url).replace("{width}", os.getenv("ZARA_IMAGE_WIDTH", "800"))
    # Normalize protocol-relative URLs like //static.zara.net/... to https
    if url.startswith("//"):
        url = "https:" + url
    try:
        mdl = _get_model() if model is None else SentenceTransformer(model)
        headers = get_default_headers()
        # Some CDNs require a Referer; set for common domains we scrape
        if "zara" in url:
            headers = {**headers, "Referer": "https://www.zara.com/"}
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        vec = mdl.encode([img], normalize_embeddings=True)
        return vec[0].tolist()
    except Exception:
        # One simple retry with a larger width if applicable
        try:
            url2 = url.replace("800", "1200", 1) if "800" in url else url
            if url2 != url:
                headers = get_default_headers()
                if "zara" in url2:
                    headers = {**headers, "Referer": "https://www.zara.com/"}
                resp = requests.get(url2, headers=headers, timeout=30)
                resp.raise_for_status()
                img = Image.open(BytesIO(resp.content)).convert("RGB")
                vec = mdl.encode([img], normalize_embeddings=True)
                return vec[0].tolist()
        except Exception:
            pass
        return None


