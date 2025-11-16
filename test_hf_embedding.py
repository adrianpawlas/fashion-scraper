#!/usr/bin/env python3
"""Test Hugging Face endpoint embedding functionality."""

import os
import sys
sys.path.append('.')

from scraper.embeddings import get_image_embedding

def test_hf_embedding():
    """Test embedding with a sample Zara image URL."""

    # Test with a sample Zara image URL
    test_image_url = "https://static.zara.net/photos///2024/V/0/1/p/1078/404/615/2/w/800/1078404615_1_1_1.jpg?ts=1701096240000"

    print("Testing Hugging Face endpoint embedding...")
    print(f"Image URL: {test_image_url}")

    # Set the endpoint and token
    os.environ["HF_EMBEDDINGS_ENDPOINT"] = "https://c2cs1z671bk7k5uf.us-east-1.aws.endpoints.huggingface.cloud"

    # You need to set your HF_TOKEN environment variable
    if "HF_TOKEN" not in os.environ:
        print("❌ ERROR: Please set HF_TOKEN environment variable with your Hugging Face token")
        print("   Example: export HF_TOKEN='your_token_here'")
        return

    embedding = get_image_embedding(test_image_url, max_retries=1)

    if embedding:
        print("✅ SUCCESS: Got embedding!")
        print(f"   Dimensions: {len(embedding)}")
        print(f"   First 5 values: {embedding[:5]}")
        print(f"   Type: {type(embedding[0])}")
    else:
        print("❌ FAILED: No embedding returned")

if __name__ == "__main__":
    test_hf_embedding()
