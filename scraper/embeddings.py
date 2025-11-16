import os
from typing import Optional
from time import sleep
from io import BytesIO

import requests


def get_image_embedding(image_url: str, max_retries: int = 3) -> Optional[list]:
    """Get embedding using Hugging Face endpoint for Marqo Fashion SigLIP model."""
    if not image_url or not str(image_url).strip():
        return None

    raw_url = str(image_url).strip()

    # Skip data URLs (base64 embedded images) - these are placeholders
    if raw_url.startswith("data:"):
        print(f"[SKIP] Data URL placeholder - no embedding needed")
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

    # Get Hugging Face endpoint URL from environment
    hf_endpoint = os.getenv("HF_EMBEDDINGS_ENDPOINT", "https://c2cs1z671bk7k5uf.us-east-1.aws.endpoints.huggingface.cloud")
    hf_token = os.getenv("HF_TOKEN")  # Required: for authenticated endpoints

    if not hf_token:
        print("[ERROR] HF_TOKEN environment variable is required for Hugging Face endpoint authentication")
        return None

    for attempt in range(max_retries):
        if attempt > 0:
            # Exponential backoff: 1s, 2s, 4s
            sleep_time = 2 ** (attempt - 1)
            print(f"[RETRY] Hugging Face embedding attempt {attempt + 1}/{max_retries} after {sleep_time}s...")
            sleep(sleep_time)

        try:
            # Prepare request to Hugging Face endpoint
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {hf_token}"
            }

            # First try: send image URL directly (some HF endpoints support this)
            payload = {
                "inputs": raw_url
            }

            print(f"[EMBED] Requesting embedding from HF endpoint for: {raw_url[:60]}...")
            resp = requests.post(hf_endpoint, headers=headers, json=payload, timeout=30)

            # If URL approach fails with 422 (Unprocessable Entity), try base64 approach
            if resp.status_code == 422:
                print("[EMBED] URL approach failed, trying base64 encoded image...")

                # Download image and convert to base64
                img_headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }

                # Special handling for Zara images
                if "zara" in raw_url.lower():
                    img_headers["Referer"] = "https://www.zara.com/"
                    img_headers["Accept"] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
                    img_headers["Sec-Fetch-Dest"] = "image"
                    img_headers["Sec-Fetch-Mode"] = "no-cors"
                    img_headers["Sec-Fetch-Site"] = "same-site"

                img_resp = requests.get(raw_url, headers=img_headers, timeout=15)
                img_resp.raise_for_status()

                import base64
                img_base64 = base64.b64encode(img_resp.content).decode('utf-8')

                # Try with base64 encoded image
                payload = {
                    "inputs": f"data:image/jpeg;base64,{img_base64}"
                }

                resp = requests.post(hf_endpoint, headers=headers, json=payload, timeout=30)

            resp.raise_for_status()
            result = resp.json()

            # Handle different possible response formats from HF endpoints
            if isinstance(result, list) and len(result) > 0:
                # If it's a list, take the first item
                embedding = result[0]
            elif isinstance(result, dict):
                # If it's a dict, try common keys
                embedding = result.get("embeddings") or result.get("embedding") or result.get("vectors")
                if isinstance(embedding, list) and len(embedding) > 0:
                    embedding = embedding[0]
            else:
                embedding = result

            # Ensure we have a list of floats
            if isinstance(embedding, list) and all(isinstance(x, (int, float)) for x in embedding):
                print(f"[EMBED] Successfully got {len(embedding)}-dim embedding")
                return embedding
            else:
                print(f"[ERROR] Unexpected embedding format: {type(embedding)}")
                return None

        except Exception as e:
            print(f"[ERROR] Hugging Face embedding failed: {str(e)[:80]}")
            print(f"        URL: {raw_url}")

    print(f"[FAILED] All Hugging Face embedding attempts failed for: {image_url[:60]}")
    return None
