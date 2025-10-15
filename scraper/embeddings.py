import os
from typing import Optional
from time import sleep, time

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
        raw_url = raw_url.replace("{width}", "800", 1)

    # Configuration
    timeout_seconds = int(os.getenv("EMBEDDINGS_TIMEOUT", "30"))
    
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

        # Validate dimension (must be 512 to match mobile app & database)
        if len(embedding) != 512:
            raise ValueError(f"Expected 512-dim, got {len(embedding)}")

        print(f"[EMBED_OK] {elapsed:.1f}s - {raw_url[:60]}")
        return embedding

    except requests.exceptions.Timeout:
        print(f"[TIMEOUT] {timeout_seconds}s - {raw_url[:60]}")
        return None

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if hasattr(e, 'response') else '?'
        print(f"[HTTP_{status}] {time() - start_time:.1f}s - {raw_url[:60]}")
        return None

    except Exception as e:
        print(f"[ERROR] {str(e)[:80]} - {raw_url[:60]}")
        return None
