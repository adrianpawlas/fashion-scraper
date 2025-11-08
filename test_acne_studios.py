import asyncio
from playwright.async_api import async_playwright

async def test_acne_studios():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        try:
            print('Testing Acne Studios category page...')
            await page.goto('https://www.acnestudios.com/eu/cz/en/man/clothing/', timeout=30000)
            print(f'Final URL: {page.url}')

            # Wait for content
            await page.wait_for_timeout(5000)

            # Check page content
            title = await page.title()
            print(f'Page title: {title}')

            # Look for products with various selectors
            selectors = [
                '[data-product-id]',
                '.product',
                '.product-item',
                '.grid-item',
                '[data-testid*="product"]',
                '.product-card',
                '.collection-item',
                'article',
                '.item',
                '[class*="product"]',
                '[class*="item"]'
            ]

            best_selector = None
            best_count = 0
            products = []

            for selector in selectors:
                found = await page.query_selector_all(selector)
                count = len(found)
                print(f'Selector "{selector}": {count} elements')

                if count > best_count and count > 5:
                    best_count = count
                    best_selector = selector
                    products = found

            print(f'\nBest selector: {best_selector} with {best_count} elements')

            # Try the [data-product-id] selector specifically since it found 28 items
            data_product_elements = await page.query_selector_all('[data-product-id]')
            print(f'\nTesting [data-product-id] selector: {len(data_product_elements)} elements')

            if data_product_elements:
                # Get first few product details
                for i in range(min(5, len(data_product_elements))):
                    product = data_product_elements[i]

                    product_id = await product.get_attribute('data-product-id')
                    print(f'Product {i+1} ID: {product_id}')

                    # Try to get product title
                    title_elem = await product.query_selector('h3, h4, .title, .product-title, a[title]')
                    if title_elem:
                        product_title = await title_elem.inner_text()
                        try:
                            print(f'Product {i+1} title: {product_title[:50]}...')
                        except UnicodeEncodeError:
                            print(f'Product {i+1} title: [Unicode title]')

                    # Try to get price
                    price_elem = await product.query_selector('[class*="price"], .price')
                    if price_elem:
                        price_text = await price_elem.inner_text()
                        try:
                            print(f'Product {i+1} price: {price_text}')
                        except UnicodeEncodeError:
                            print(f'Product {i+1} price: [Unicode price]')

                    # Look for links to product pages
                    links = await product.query_selector_all('a')
                    for link in links[:2]:
                        href = await link.get_attribute('href')
                        if href and 'acnestudios.com' in href and ('B' in href or '/product' in href):
                            print(f'Product {i+1} link: {href}')
                            break

                    print(f'---')

            # Now test a product page
            print('\n--- Testing product page ---')
            await page.goto('https://www.acnestudios.com/eu/cz/en/leather-shirt-jacket-red-black/B70160-BBI.html?g=man', timeout=30000)
            await page.wait_for_timeout(5000)

            product_title = await page.title()
            print(f'Product page title: {product_title}')

            # Look for product data
            title_selectors = ['h1', '.product-title', '[class*="title"]']
            for selector in title_selectors:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    print(f'Title with {selector}: {text}')
                    break

            # Look for price
            price_selectors = ['[class*="price"]', '.price']
            for selector in price_selectors:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    try:
                        print(f'Price with {selector}: {text}')
                    except UnicodeEncodeError:
                        print(f'Price with {selector}: [Unicode price found]')
                    break

            # Check for images
            images = await page.query_selector_all('img[src*="acnestudios"]')
            print(f'Found {len(images)} images')

            # Check for JSON-LD
            json_scripts = await page.query_selector_all('script[type="application/ld+json"]')
            print(f'Found {len(json_scripts)} JSON-LD scripts')

            if json_scripts:
                for i, script in enumerate(json_scripts[:2]):
                    json_text = await script.inner_text()
                    print(f'JSON-LD {i+1} length: {len(json_text)} chars')
                    # Print first 300 chars to see structure
                    print(f'JSON-LD {i+1} preview: {json_text[:300]}...')

        except Exception as e:
            print(f'Error: {e}')
        finally:
            await browser.close()

asyncio.run(test_acne_studios())
