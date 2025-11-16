#!/usr/bin/env python3
"""Test CLIP embedding functionality to ensure 512-dimensional output."""

import os
import sys
sys.path.append('.')

from scraper.embeddings import get_image_embedding

def test_clip_embedding():
    """Test CLIP embedding with a sample Zara image URL."""

    # Test with a sample Zara image URL
    test_image_url = "https://static.zara.net/photos///2024/V/0/1/p/1078/404/615/2/w/800/1078404615_1_1_1.jpg?ts=1701096240000"

    print("Testing CLIP embedding...")
    print(f"Image URL: {test_image_url}")

    # Set the model to CLIP
    os.environ["EMBEDDINGS_MODEL"] = "openai/clip-vit-base-patch32"

    embedding = get_image_embedding(test_image_url, max_retries=1)

    if embedding:
        print("✅ SUCCESS: Got embedding!")
        print(f"   Dimensions: {len(embedding)}")
        print(f"   First 5 values: {embedding[:5]}")
        print(f"   Type: {type(embedding[0])}")

        # Verify dimensions
        if len(embedding) == 512:
            print("✅ SUCCESS: Correct 512 dimensions!")
        else:
            print(f"❌ ERROR: Expected 512 dimensions, got {len(embedding)}")

        # Check value ranges (should be reasonable floats, approximately magnitude 1.0)
        import math
        magnitude = math.sqrt(sum(x*x for x in embedding))
        print(f"   Magnitude: {magnitude:.3f}")
        if 0.5 < magnitude < 2.0:
            print("✅ SUCCESS: Reasonable magnitude!")
        else:
            print(f"⚠️  WARNING: Unusual magnitude {magnitude:.3f}")

        # Check for extreme values
        max_val = max(abs(x) for x in embedding)
        if max_val < 100:  # CLIP embeddings are typically normalized
            print("✅ SUCCESS: Reasonable value range!")
        else:
            print(f"⚠️  WARNING: Extreme values detected (max: {max_val})")

    else:
        print("❌ FAILED: No embedding returned")

if __name__ == "__main__":
    test_clip_embedding()
