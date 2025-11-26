import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
headers = {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}

print(f"Connecting to: {url}")

# Check for Zara products specifically
response = requests.get(f'{url}/rest/v1/products?source=eq.scraper&select=id,brand,title', headers=headers)
if response.status_code == 200:
    data = response.json()
    zara_count = len(data)
    print(f'Zara products (source=scraper): {zara_count}')
    if zara_count > 0:
        print('Sample Zara products:')
        for i, product in enumerate(data[:3]):
            title = product.get("title", "N/A")
            brand = product.get("brand", "N/A")
            print(f'  {i+1}. {title[:40]} - {brand}')
    else:
        print('No Zara products found')
else:
    print(f'Error checking Zara products: {response.status_code} - {response.text}')

# Get total count
response2 = requests.get(f'{url}/rest/v1/products?select=id,source,brand', headers=headers)
if response2.status_code == 200:
    all_data = response2.json()
    total_count = len(all_data)
    print(f'\nTotal products in database: {total_count}')

    # Count by source
    sources = {}
    for product in all_data:
        source = product.get('source', 'unknown')
        sources[source] = sources.get(source, 0) + 1

    print('\nBy source:')
    for source, count in sources.items():
        print(f'  {source}: {count}')
else:
    print(f'Error getting total count: {response2.status_code} - {response2.text}')
