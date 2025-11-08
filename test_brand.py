import sys
sys.path.append('.')
from scraper.html_scraper import scrape_category_for_products
from scraper.http_client import PoliteSession
import re

# Test Ffected brand
brand_config = {
    'html': {
        'category_urls': ['https://ffected.com/collections/all'],
        'product_selector': '[data-product-id], .product, .product-item, .grid-item',
        'product_selectors': {
            'external_id': '[data-product-id]',
            'product_id': '[data-product-id]',
            'title': 'h3, h4, .title, .product-title, a[title], .product__title',
            'description': '[class*="description"], .description',
            'price': '.price, .product-price, .product__price',
            'image': 'img[src*="ffected"], img[alt*="product"]',
            'brand': "'Ffected'",
            'currency': "'EUR'",
            'product_url': '[href*="/products/"], a[href*="/products/"]'
        },
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'max-age=0'
        },
        'use_browser': True,
        'prewarm': ['https://ffected.com/', 'https://ffected.com/collections/all']
    }
}

session = PoliteSession()
url = brand_config['html']['category_urls'][0]
headers = brand_config['html'].get('headers')
use_browser = brand_config['html'].get('use_browser', False)

try:
    products = scrape_category_for_products(session, url, brand_config['html']['product_selector'], brand_config['html']['product_selectors'], headers, use_browser)
    print(f'Found {len(products)} products')
    if products:
        for i, product in enumerate(products[:3]):  # Check first 3 products
            image_url = product.get('image_url', 'N/A')
            print(f'Product {i+1} image_url: {image_url[:100]}...')
        print(f'First product keys: {list(products[0].keys())}')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
