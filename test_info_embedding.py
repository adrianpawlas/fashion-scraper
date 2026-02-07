"""Local test: ensure get_text_embedding and build_product_info_text produce valid info_embedding."""
import os
import sys

# Load env so SUPABASE etc. are not required for this test
if os.path.exists(".env"):
    from dotenv import load_dotenv
    load_dotenv(override=False)

from scraper.embeddings import get_text_embedding
from scraper.transform import build_product_info_text

def main():
    # 1) Test get_text_embedding with a short string
    print("Test 1: get_text_embedding with short text...")
    short = "Relaxed fit hoodie made of cotton. Price: 29.99USD. Category: sweatshirts."
    emb = get_text_embedding(short)
    if emb is None:
        print("FAIL: get_text_embedding returned None")
        sys.exit(1)
    if len(emb) != 768:
        print(f"FAIL: expected 768-dim, got {len(emb)}")
        sys.exit(1)
    print(f"OK: got 768-dim embedding (first 3 values: {emb[:3]})")

    # 2) Test build_product_info_text + get_text_embedding (one product row)
    print("\nTest 2: build_product_info_text + get_text_embedding (full row)...")
    row = {
        "title": "Relaxed fit hoodie",
        "description": "Hoodie made of cotton fabric with a brushed interior. Hooded collar and long sleeves.",
        "category": "sweatshirts, sweatpants",
        "brand": "Zara",
        "gender": "women",
        "price": "29.99USD",
        "sale": None,
        "size": "S, M, L",
        "metadata": '{"country": "us", "merchant_name": "Zara"}',
    }
    info_text = build_product_info_text(row)
    print(f"  Info text length: {len(info_text)} chars")
    emb2 = get_text_embedding(info_text)
    if emb2 is None:
        print("FAIL: get_text_embedding(info_text) returned None")
        sys.exit(1)
    if len(emb2) != 768:
        print(f"FAIL: expected 768-dim, got {len(emb2)}")
        sys.exit(1)
    print(f"OK: info_embedding is 768-dim (first 3: {emb2[:3]})")

    print("\nAll tests passed. info_embedding is working locally.")

if __name__ == "__main__":
    main()
