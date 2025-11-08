import sys
sys.path.append('.')
from scraper.html_scraper import scrape_category_for_products
from scraper.http_client import PoliteSession

# Test Represent Clothing
brand_config = {
    'html': {
        'category_urls': ['https://eu.representclo.com/collections/discover-all-products'],
        'product_selector': '[class*="product"], .product, .product-item, .grid-item',
        'product_selectors': {
            'external_id': '[data-product-id]',
            'product_id': '[data-product-id]',
            'title': 'h3, h4, .title, .product-title, a[title]',
            'description': '[class*="description"], .description',
            'price': '[class*="price"], .price, [data-testid*="price"]',
            'image': 'img[src*="representclo"], img[alt*="product"]',
            'brand': "'Represent Clothing'",
            'currency': "'EUR'",
            'product_url': 'href'
        },
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'max-age=0'
        },
        'use_browser': True,
        'prewarm': ['https://eu.representclo.com/', 'https://eu.representclo.com/collections/discover-all-products']
    }
}

session = PoliteSession()
url = brand_config['html']['category_urls'][0]
headers = brand_config['html'].get('headers')
use_browser = brand_config['html'].get('use_browser', False)

try:
    products = scrape_category_for_products(session, url, brand_config['html']['product_selector'], brand_config['html']['product_selectors'], headers, use_browser)
    print(f'Represent Clothing: Found {len(products)} products')
    if products and len(products) > 0:
        print(f'First product has external_id: {bool(products[0].get("external_id"))}')
        print(f'First product keys: {list(products[0].keys())}')
except Exception as e:
    print(f'Represent Clothing Error: {e}')
    import traceback
    traceback.print_exc()
