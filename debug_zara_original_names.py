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

print("Testing Zara API endpoint for originalName values...")
resp = requests.get(url, headers=headers, timeout=30)
data = resp.json()

# Try the items_path from sites.yaml
items_path = 'productGroups[].elements[].commercialComponents[]'
items = jmespath.search(items_path, data)
print(f'Items found with path "{items_path}": {len(items) if items else 0}')

if items:
    # Sample first 5 items to see what originalName values exist
    for i, item in enumerate(items[:5]):
        print(f"\n=== Item {i+1}: {item.get('name', 'Unknown')} ===")

        # Check xmedia structure
        xmedia = item.get('detail', {}).get('colors', [])
        if xmedia:
            print(f"Colors count: {len(xmedia)}")
            for color_idx, color in enumerate(xmedia[:2]):  # First 2 colors
                xmedia_items = color.get('xmedia', [])
                print(f"  Color {color_idx+1} xmedia count: {len(xmedia_items)}")
                for x_idx, x_item in enumerate(xmedia_items[:3]):  # First 3 xmedia per color
                    name = x_item.get('name', 'no-name')
                    original_name = x_item.get('extraInfo', {}).get('originalName', 'no-original')
                    print(f"    xmedia {x_idx+1}: name='{name}', originalName='{original_name}'")

        # Check top-level xmedia
        top_xmedia = item.get('xmedia', [])
        if top_xmedia:
            print(f"Top-level xmedia count: {len(top_xmedia)}")
            for x_idx, x_item in enumerate(top_xmedia[:2]):
                name = x_item.get('name', 'no-name')
                original_name = x_item.get('extraInfo', {}).get('originalName', 'no-original')
                print(f"    Top xmedia {x_idx+1}: name='{name}', originalName='{original_name}'")
