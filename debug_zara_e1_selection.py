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

print("Testing Zara API endpoint for e1 image selection...")
resp = requests.get(url, headers=headers, timeout=30)
data = resp.json()

# Try the items_path from sites.yaml
items_path = 'productGroups[].elements[].commercialComponents[]'
items = jmespath.search(items_path, data)
print(f'Items found with path "{items_path}": {len(items) if items else 0}')

if items:
    # Test different JMESPath approaches for first 3 items
    test_paths = [
        # Current approach - by originalName
        "detail.colors[].xmedia[?extraInfo.originalName=='e1'] | [0].extraInfo.deliveryUrl",
        # Alternative - by name ending with -e1
        "detail.colors[].xmedia[?name =~ '.*-e1$'] | [0].extraInfo.deliveryUrl",
        # Alternative - just take first xmedia item (which seems to always be e1)
        "detail.colors[].xmedia[] | [0].extraInfo.deliveryUrl",
        # Alternative - take first xmedia item's url
        "detail.colors[].xmedia[] | [0].url"
    ]

    for i, item in enumerate(items[:3]):
        print(f"\n=== Item {i+1}: {item.get('name', 'Unknown')} ===")

        for path_name, path in zip(['originalName==e1', 'name=~.*-e1$', 'first xmedia deliveryUrl', 'first xmedia url'], test_paths):
            try:
                result = jmespath.search(path, item)
                if result:
                    print(f"  {path_name}: OK - {result}")
                else:
                    print(f"  {path_name}: NONE")
            except Exception as e:
                print(f"  {path_name}: ERROR - {e}")
