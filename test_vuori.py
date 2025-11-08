import sys
sys.path.append('.')
from scraper.html_scraper import scrape_category_for_products
from scraper.http_client import PoliteSession

# Test Vuori
brand_config = {
    'html': {
        'category_urls': ['https://vuoriclothing.com/collections/mens'],
        'product_selector': '[data-testid*="product"], .product, .product-item, .grid-item',
        'product_selectors': {
            'external_id': '[data-product-id]',
            'product_id': '[data-product-id]',
            'title': 'h3, h4, .title, .product-title, a[title]',
            'description': '[class*="description"], .description',
            'price': '[class*="price"], .price, [data-testid*="price"]',
            'image': 'img[src*="vuoriclothing"], img[alt*="product"]',
            'brand': "'Vuori'",
            'currency': "'USD'",
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
        'prewarm': ['https://vuoriclothing.com/', 'https://vuoriclothing.com/collections/mens']
    }
}

session = PoliteSession()
url = brand_config['html']['category_urls'][0]
headers = brand_config['html'].get('headers')
use_browser = brand_config['html'].get('use_browser', False)

try:
    products = scrape_category_for_products(session, url, brand_config['html']['product_selector'], brand_config['html']['product_selectors'], headers, use_browser)
    print(f'Vuori: Found {len(products)} products')
    if products and len(products) > 0:
        print(f'First product has external_id: {bool(products[0].get("external_id"))}')
        print(f'First product keys: {list(products[0].keys())}')
except Exception as e:
    print(f'Vuori Error: {e}')
    import traceback
    traceback.print_exc()
