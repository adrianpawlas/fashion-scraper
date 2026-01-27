import os
import requests

url = 'https://yqawmzggcgpeyaaynrjk.supabase.co'
key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlxYXdtemdnY2dwZXlhYXlucmprIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTAxMDkyNiwiZXhwIjoyMDcwNTg2OTI2fQ.XtLpxausFriraFJeX27ZzsdQsFv3uQKXBBggoz6P4D4'

headers = {
    'apikey': key,
    'Authorization': f'Bearer {key}'
}

print(f'Connecting to: {url}')
print(f'Using API key: {key[:20]}...')

try:
    # Get total count
    print('\nChecking products count...')
    response = requests.get(f'{url}/rest/v1/products?select=count', headers=headers)
    print(f'Status: {response.status_code}')

    if response.status_code == 200:
        data = response.json()
        print(f'Raw count response: {data}')
        # For Supabase count query, get the actual count value
        count = data[0].get('count', 0) if isinstance(data, list) and data else 0
        print(f'SUCCESS: Products in database: {count}')

        # Alternative count method
        response_alt = requests.get(f'{url}/rest/v1/products?select=id', headers=headers)
        if response_alt.status_code == 200:
            alt_data = response_alt.json()
            alt_count = len(alt_data) if isinstance(alt_data, list) else 0
            print(f'Alternative count (select=id): {alt_count}')

        if count > 0 or alt_count > 0:
            print('\nGetting sample product...')
            # Get a sample product with all columns
            response2 = requests.get(f'{url}/rest/v1/products?limit=1', headers=headers)
            if response2.status_code == 200:
                sample = response2.json()
                if sample:
                    product = sample[0]
                    print(f'Sample product:')
                    print(f'   ID: {product.get("id", "N/A")}')
                    print(f'   Title: {product.get("title", "N/A")}')
                    print(f'   Brand: {product.get("brand", "N/A")}')
                    print(f'   Source: {product.get("source", "N/A")}')
                    print(f'   Category: {product.get("category", "N/A")}')
                    print(f'   Gender: {product.get("gender", "N/A")}')
                    print(f'   Price: {product.get("price", "N/A")}')
                    print(f'   Sale: {product.get("sale", "N/A")}')
                    print(f'   Has embedding: {"Yes" if product.get("embedding") else "No"}')
                    print(f'   Second hand: {product.get("second_hand", False)}')
                    if product.get("created_at"):
                        print(f'   Created: {product.get("created_at")[:19]}')
                else:
                    print('WARNING: No products found in sample query')
            else:
                print(f'ERROR fetching sample: {response2.status_code} - {response2.text}')
        else:
            print('WARNING: No products found in database')
    else:
        print(f'DATABASE ERROR: {response.status_code} - {response.text}')

except Exception as e:
    print(f'CONNECTION ERROR: {e}')
