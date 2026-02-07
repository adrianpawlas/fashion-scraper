import os
from typing import Optional
from time import sleep, time
from io import BytesIO

import requests
import torch
from PIL import Image
from transformers import SiglipProcessor, SiglipModel

_processor: Optional[SiglipProcessor] = None
_model: Optional[SiglipModel] = None
_model_error: bool = False


def _get_model():
    global _processor, _model, _model_error
    if _model is None and not _model_error:
        model_name = os.getenv("EMBEDDINGS_MODEL", "google/siglip-base-patch16-384")
        try:
            print(f"[MODEL] Loading {model_name}...")
            start_time = time()
            _processor = SiglipProcessor.from_pretrained(model_name)
            _model = SiglipModel.from_pretrained(model_name)
            load_time = time() - start_time
            print(f"[MODEL] Loaded {model_name} in {load_time:.1f}s")
        except Exception as e:
            print(f"[ERROR] Failed to load model {model_name}: {e}")
            _model_error = True
            return None, None
    return _processor, _model


def get_image_embedding(image_url: str, max_retries: int = 3) -> Optional[list]:
    """Get embedding using Google SigLIP model (768-dim, vision-language model)."""
    if not image_url or not str(image_url).strip():
        return None

    processor, model = _get_model()
    if model is None or processor is None:
        return None

    raw_url = str(image_url).strip()

    # Skip data URLs (base64 embedded images) - these are placeholders
    if raw_url.startswith("data:"):
        print(f"[SKIP] Data URL placeholder - no embedding needed")
        return None

    # Skip video files and non-image content
    # Check for video extensions anywhere in the URL
    video_patterns = ['.m3u8', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '/video.mp4', '/video.', 'video.mp4']
    if any(pattern in raw_url.lower() for pattern in video_patterns):
        print(f"[SKIP] Video file detected - not an image")
        return None

    # Skip other non-image file types (check for extensions in the URL)
    non_image_extensions = ['.html', '.htm', '.json', '.xml', '.txt', '.css', '.js', '.pdf', '.zip', '.rar']
    if any(ext in raw_url.lower() for ext in non_image_extensions):
        print(f"[SKIP] Non-image file type - not an image")
        return None

    # Skip obviously incomplete URLs (Zara images should have longer paths)
    if "zara" in raw_url.lower():
        # Zara image URLs should be much longer than this
        if len(raw_url) < 80:
            print(f"[SKIP] Incomplete Zara URL (too short: {len(raw_url)} chars)")
            return None
        # Should contain multiple path segments
        if raw_url.count('/') < 6:
            print(f"[SKIP] Incomplete Zara URL (too few path segments: {raw_url.count('/')}")

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

            # Process image with SigLIP (requires both image and text inputs)
            inputs = processor(images=img, text=[""], return_tensors="pt")

            with torch.no_grad():
                outputs = model(**inputs)
                # Use image embeddings (768-dim for SigLIP base)
                embedding = outputs.image_embeds.squeeze().tolist()

            # Verify dimensions (should be exactly 768)
            if len(embedding) != 768:
                print(f"[ERROR] Embedding dimension mismatch: got {len(embedding)}, expected 768")
                return None

            return embedding
        except Exception as e:
            print(f"[ERROR] Local embedding failed: {str(e)[:80]}")
            print(f"        URL: {raw_url}")
    print(f"[FAILED] All local embedding attempts failed for: {image_url[:60]}")
    return None


def get_text_embedding(text: str) -> Optional[list]:
    """Get text embedding using the same SigLIP model (768-dim), for product info (title, description, category, etc.)."""
    if not text or not str(text).strip():
        return None

    processor, model = _get_model()
    if model is None or processor is None:
        return None

    try:
        # SigLIP expects padding="max_length" as in training
        inputs = processor(
            text=[str(text).strip()],
            padding="max_length",
            return_tensors="pt",
        )
        try:
            device = next(model.parameters()).device
            inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}
        except Exception:
            pass

        with torch.no_grad():
            # Pass only text inputs; model returns text_embeds in same space as image_embeds
            outputs = model(**inputs)
            text_embeds = getattr(outputs, "text_embeds", None)
            if text_embeds is None:
                # Fallback: use get_text_features (pooler_output)
                text_embeds = model.get_text_features(**inputs)
                if hasattr(text_embeds, "pooler_output"):
                    text_embeds = text_embeds.pooler_output
            embedding = text_embeds.squeeze(0).tolist()

        if len(embedding) != 768:
            print(f"[ERROR] Text embedding dimension mismatch: got {len(embedding)}, expected 768")
            return None
        return embedding
    except Exception as e:
        print(f"[ERROR] Text embedding failed: {str(e)[:80]}")
        return None
