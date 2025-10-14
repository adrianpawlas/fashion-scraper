#!/usr/bin/env python3
"""
Test script to verify Railway embedding service integration.
Run this BEFORE full scraping to ensure embeddings work correctly.
"""

from scraper.embeddings import get_image_embedding

def test_embedding_service():
    """Test embedding generation with a sample image."""
    
    # Test with a public image URL
    test_url = 'https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=400'
    
    print("🧪 Testing Railway embedding service...")
    print(f"📷 Test image: {test_url}")
    print("⏳ Generating embedding (first request may take ~60s due to cold start)...\n")
    
    embedding = get_image_embedding(test_url)
    
    if embedding is None:
        print("❌ FAILED: No embedding returned")
        print("   Check your Railway service status and network connection")
        return False
    
    print(f"✅ SUCCESS!")
    print(f"   Dimension: {len(embedding)}")
    print(f"   First 5 values: {embedding[:5]}")
    print(f"   Data type: {type(embedding)}")
    
    # Validate dimension
    if len(embedding) != 512:
        print(f"\n❌ ERROR: Expected 512 dimensions, got {len(embedding)}")
        print("   Your database expects 512-dim vectors!")
        return False
    
    print("\n✅ All checks passed!")
    print("   Ready to scrape with Railway embeddings 🚀")
    return True


if __name__ == "__main__":
    success = test_embedding_service()
    exit(0 if success else 1)

