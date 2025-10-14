import os
from typing import Optional
from time import sleep
import random

import requests


RAILWAY_EMBED_URL = 'https://finds-user-embedding-production.up.railway.app/embed'


def get_image_embedding(image_url: str) -> Optional[list]:
    """
    Get 512-dim embedding from Railway service.
    This is the EXACT same service the mobile app uses for visual search!
    """
    if not image_url or not str(image_url).strip():
        return None

    # Prepare image URL (handle protocol-relative URLs)
    raw_url = str(image_url).strip()
    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url

    # Handle Zara's {width} placeholder
    if "{width}" in raw_url:
        # Try common widths; Railway service will handle the download
        raw_url = raw_url.replace("{width}", "800", 1)

    # Retry configuration
    max_retries = max(1, int(os.getenv("EMBEDDINGS_RETRIES", "2")))
    timeout_seconds = int(os.getenv("EMBEDDINGS_TIMEOUT", "120"))  # Cold start can take 60s

    for attempt in range(max_retries):
        try:
            response = requests.post(
                RAILWAY_EMBED_URL,
                json={
                    'image': raw_url,
                    'type': 'url'
                },
                timeout=timeout_seconds
            )
            response.raise_for_status()
            data = response.json()

            embedding = data.get('embedding')
            if not embedding:
                raise ValueError("No embedding in response")

            # Validate dimension (must be 512 to match mobile app & database)
            if len(embedding) != 512:
                raise ValueError(f"Expected 512-dim, got {len(embedding)}")

            return embedding

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                print(f"⚠️  Railway timeout (cold start?) for {raw_url} - retrying...")
                sleep(2)
                continue
            else:
                print(f"❌ Railway timeout after {max_retries} attempts: {raw_url}")
                return None

        except requests.exceptions.HTTPError as e:
            # 4xx/5xx errors from Railway service
            print(f"❌ Railway HTTP error for {raw_url}: {e}")
            if attempt < max_retries - 1:
                sleep(1)
                continue
            return None

        except Exception as e:
            print(f"❌ Railway embedding failed for {raw_url}: {e}")
            if attempt < max_retries - 1:
                sleep(1)
                continue
            return None

    return None
