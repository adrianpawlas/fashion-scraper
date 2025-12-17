import requests
import json
import jmespath

# Test one Zara endpoint
url = 'https://www.zara.com/us/en/category/2443335/products?ajax=true'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.zara.com/us/en/'
}

print("Testing Zara API endpoint...")
resp = requests.get(url, headers=headers, timeout=30)
data = resp.json()

print('API response keys:', list(data.keys()))

# Try the items_path from sites.yaml
items_path = 'productGroups[].elements[].commercialComponents[]'
items = jmespath.search(items_path, data)
print(f'Items found with path "{items_path}": {len(items) if items else 0}')

if items:
    item = items[0]
    print('First item keys:', list(item.keys()))
    print('First item title (name):', item.get('name', 'N/A'))
    print('First item seo.discernProductId:', item.get('seo', {}).get('discernProductId', 'N/A'))
    print('First item seo.keyword:', item.get('seo', {}).get('keyword', 'N/A'))
    print('First item id:', item.get('id', 'N/A'))

    # Check if image_url extraction works
    image_paths = [
        "detail.colors[].xmedia[?extraInfo.originalName=='e1'] | [0].extraInfo.deliveryUrl",
        "detail.colors[].xmedia[] | [0].extraInfo.deliveryUrl",
        "detail.colors[].xmedia[] | [0].url",
        "xmedia[] | [0].url"
    ]

    print('\nTesting image_url extraction:')
    for path in image_paths:
        try:
            result = jmespath.search(path, item)
            print(f'  {path}: {result}')
        except Exception as e:
            print(f'  {path}: ERROR - {e}')

    # Test the transformation
    from scraper.transform import to_supabase_row

    raw_product = {
        'source': 'zara',
        'external_id': item.get('seo', {}).get('discernProductId'),
        'product_id': item.get('seo', {}).get('discernProductId'),
        'title': item.get('name'),
        'description': item.get('description'),
        'brand': 'Zara',
        'price': item.get('price'),
        'currency': 'USD',
        'gender': item.get('sectionName') or item.get('section'),
        'seo_keyword': item.get('seo', {}).get('keyword'),
        'seo_product_id': item.get('id'),
        'product_url_template': 'https://www.zara.com/us/en/{keyword}-p{id}.html?v1={discern_id}',
        '_meta': {'endpoint': url}
    }

    # Add image_url
    for path in image_paths:
        try:
            image_url = jmespath.search(path, item)
            if image_url:
                raw_product['image_url'] = image_url
                break
        except:
            pass

    print('\nRaw product data:')
    print(json.dumps(raw_product, indent=2, default=str))

    print('\nTransformed product:')
    transformed = to_supabase_row(raw_product)
    print(json.dumps(transformed, indent=2, default=str))
