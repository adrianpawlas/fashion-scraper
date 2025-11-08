#!/usr/bin/env python3
"""
Explore ASOS website structure to understand API/data loading
"""
import requests
import json
from bs4 import BeautifulSoup

def explore_asos_category():
    """Explore ASOS category page to understand data loading"""
    url = "https://www.asos.com/men/hoodies-sweatshirts/cat/?cid=5668"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'max-age=0',
        'Sec-Ch-Ua': '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1'
    }

    print(f"Exploring ASOS category: {url}")
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to fetch page: {response.status_code}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')

    # Look for script tags with JSON data
    scripts = soup.find_all('script', type='application/json') or soup.find_all('script', string=lambda x: x and ('product' in x.lower() or 'item' in x.lower() or 'asos' in x.lower()))

    print(f"Found {len(scripts)} script tags that might contain data")

    for i, script in enumerate(scripts[:3]):  # Check first 3 scripts
        if script.string:
            content = script.string.strip()
            print(f"\n--- Script {i+1} (first 500 chars) ---")
            print(content[:500])

            # Try to parse as JSON
            try:
                data = json.loads(content)
                print(f"Successfully parsed as JSON. Keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                if isinstance(data, dict) and 'products' in data:
                    print(f"Found products key with {len(data['products'])} items")
                elif isinstance(data, dict) and 'items' in data:
                    print(f"Found items key with {len(data['items'])} items")
            except json.JSONDecodeError as e:
                print(f"Failed to parse as JSON: {e}")

    # Look for API calls in the page
    api_patterns = [
        r'https://api\.asos\.com',
        r'/api/',
        r'window\.asos',
        r'ASOS\.',
        r'productData',
        r'categoryData'
    ]

    print("\n--- Looking for API patterns in page source ---")
    page_text = response.text.lower()
    for pattern in api_patterns:
        if pattern.lower() in page_text:
            print(f"Found pattern: {pattern}")

def explore_asos_product():
    """Explore ASOS product page"""
    url = "https://www.asos.com/allsaints/allsaints-underground-sweatshirt-in-beige/prd/209269738#colourWayId-209269746"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'max-age=0',
        'Sec-Ch-Ua': '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1'
    }

    print(f"\nExploring ASOS product: {url}")
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to fetch product page: {response.status_code}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')

    # Look for structured data
    structured_data = soup.find_all('script', type='application/ld+json')
    print(f"Found {len(structured_data)} structured data scripts")

    for i, script in enumerate(structured_data[:2]):
        if script.string:
            try:
                data = json.loads(script.string)
                print(f"\n--- Structured Data {i+1} ---")
                print(json.dumps(data, indent=2)[:1000])
            except json.JSONDecodeError as e:
                print(f"Failed to parse structured data: {e}")

if __name__ == "__main__":
    explore_asos_category()
    explore_asos_product()
