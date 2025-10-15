"""
Test script specifically for Zara image embedding (403 issue).
"""

import os
os.environ["USE_RAILWAY_EMBEDDINGS"] = "false"  # Force local

from scraper.embeddings import get_image_embedding

def test_zara_image():
    """Test embedding generation with an actual Zara image URL."""
    
    # Real Zara image URL from their CDN
    zara_url = 'https://static.zara.net/assets/public/1b62/6d29/75804a8ca84d/1d5e7dc83f40/04087412800-p/04087412800-p.jpg?ts=1729012345968&w=563'
    
    print("[TEST] Testing Zara image embedding (local model)...")
    print(f"[IMAGE] {zara_url[:80]}...")
    
    print("\n[WAIT] Generating local embedding...\n")
    embedding = get_image_embedding(zara_url)
    
    if embedding is None:
        print("[FAIL] No embedding returned")
        print("       Zara is still blocking requests - this is expected")
        print("       The scraper will continue without embeddings for blocked images")
        return False
    
    print(f"[SUCCESS] Embedding generated!")
    print(f"          Dimension: {len(embedding)}")
    print(f"          First 5 values: {embedding[:5]}")
    
    if len(embedding) != 512:
        print(f"\n[ERROR] Expected 512 dimensions, got {len(embedding)}")
        return False
    
    print("\n[SUCCESS] Zara image embedding works!")
    return True


if __name__ == "__main__":
    success = test_zara_image()
    exit(0 if success else 1)

