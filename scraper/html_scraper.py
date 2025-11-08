from typing import Dict, List, Optional
import json
import re
from urllib.parse import urljoin, urlparse
import os

from bs4 import BeautifulSoup

from .http_client import PoliteSession


def parse_product_html(html: str, selectors: Dict[str, str]) -> Dict:
	soup = BeautifulSoup(html, "lxml")
	def sel_text(css: str) -> str:
		n = soup.select_one(css)
		return (n.get_text(strip=True) if n else "")
	def sel_attr(css: str, attr: str) -> str:
		n = soup.select_one(css)
		return (n.get(attr, "") if n else "")
	return {
		"title": sel_text(selectors.get("title", "")),
		"description": sel_text(selectors.get("description", "")),
		"price": sel_text(selectors.get("price", "")),
		"image_url": sel_attr(selectors.get("image", ""), "src"),
	}


def _fetch_html(session: PoliteSession, url: str, headers: Optional[Dict[str, str]], use_browser: bool) -> str:
	"""Fetch page HTML via requests or Playwright if requested."""
	if not use_browser:
		try:
			resp = session.get(url, headers=headers)
			# If forbidden or unauthorized, try browser fallback
			if getattr(resp, "status_code", 200) in (401, 403):
				raise Exception("Forbidden, try browser")
			resp.raise_for_status()
			return resp.text
		except Exception:
			# fall through to browser path
			pass
	# Browser path
	try:
		from playwright.sync_api import sync_playwright
		with sync_playwright() as pw:
			# Configure proxy for Playwright from env if present
			pw_proxy = None
			proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
			if proxy_url:
				u = urlparse(proxy_url)
				server = f"{u.scheme}://{u.hostname}:{u.port}"
				pw_proxy = {"server": server}
				if u.username:
					pw_proxy["username"] = u.username
				if u.password:
					pw_proxy["password"] = u.password
			browser = pw.chromium.launch(headless=True, proxy=pw_proxy)
			ua = (headers or {}).get("User-Agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
			context = browser.new_context(
				extra_http_headers=headers or {},
				user_agent=ua,
				viewport={"width": 1280, "height": 1800},
				ignore_https_errors=True,
			)
			# Basic stealth: mask webdriver, set languages/plugins
			context.add_init_script(
				"""
				Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
				Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
				Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
				try { Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] }); } catch (e) {}
				"""
			)
			page = context.new_page()
			page.goto(url, wait_until="domcontentloaded", timeout=60000)
			# Handle potential consent banner
			try:
				for sel in (
					"button:has-text('Accept all')",
					"button:has-text('Accept')",
					"button:has-text('Souhlasím')",
					"button[data-qa-anchor='consentAccept']",
				):
					if page.locator(sel).first.is_visible(timeout=1000):
						page.locator(sel).first.click(timeout=1000)
						break
			except Exception:
				pass
			# Wait for product links to appear if possible
			try:
				page.wait_for_selector("a.grid-card-link, a[data-qa-anchor='productItemHref'], a[href*='c0p']", timeout=8000)
			except Exception:
				pass
			# Best-effort: scroll to load lazy content
			try:
				for _ in range(6):
					page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
					page.wait_for_timeout(900)
			except Exception:
				pass
			html = page.content()
			context.close()
			browser.close()
			return html
	except Exception:
		# Fallback to requests if browser path fails
		resp = session.get(url, headers=headers)
		resp.raise_for_status()
		return resp.text


def scrape_product_page(session: PoliteSession, url: str, selectors: Dict[str, str], headers: Optional[Dict[str, str]] = None, use_browser: bool = False) -> Dict:
	html = _fetch_html(session, url, headers, use_browser)
	data = parse_product_html(html, selectors)
	# Attach minimal metadata for downstream storage
	try:
		data["_meta"] = {"source": "html", "page_url": url, "selectors": selectors}
		data["_raw_html_len"] = len(html or "")
	except Exception:
		pass
	data["product_url"] = url
	return data


def scrape_category_for_links(session: PoliteSession, url: str, product_link_selector: str, headers: Optional[Dict[str, str]] = None, use_browser: bool = False) -> List[str]:
    # If using a browser, query anchors directly via Playwright (helps with shadow DOM/SPA)
    if use_browser:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                ua = (headers or {}).get("User-Agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
                # Configure proxy for Playwright from env if present
                pw_proxy = None
                proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
                if proxy_url:
                    u = urlparse(proxy_url)
                    server = f"{u.scheme}://{u.hostname}:{u.port}"
                    pw_proxy = {"server": server}
                    if u.username:
                        pw_proxy["username"] = u.username
                    if u.password:
                        pw_proxy["password"] = u.password
                browser = pw.chromium.launch(headless=True, proxy=pw_proxy)
                context = browser.new_context(
                    extra_http_headers=headers or {},
                    user_agent=ua,
                    viewport={"width": 1280, "height": 1800},
                    ignore_https_errors=True,
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    page.wait_for_selector(product_link_selector, timeout=8000)
                except Exception:
                    pass
                # Scroll to load more
                try:
                    for _ in range(6):
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(900)
                except Exception:
                    pass
                # Collect hrefs
                hrefs = page.eval_on_selector_all(product_link_selector, "els => els.map(e => e.href || e.getAttribute('href') || e.getAttribute('data-href') || e.getAttribute('data-url')).filter(Boolean)")
                # If none found in main, enumerate frames
                if not hrefs:
                    all_hrefs = []
                    for fr in page.frames:
                        try:
                            got = fr.eval_on_selector_all(product_link_selector, "els => els.map(e => e.href || e.getAttribute('href') || e.getAttribute('data-href') || e.getAttribute('data-url')).filter(Boolean)")
                            if got:
                                all_hrefs.extend(got)
                        except Exception:
                            pass
                    hrefs = all_hrefs
                # If still none, regex-scan the rendered HTML
                if not hrefs:
                    try:
                        html2 = page.content()
                        for m in re.finditer(r"https?://[^\s\"']*c0p\d+[^\s\"']*", html2):
                            hrefs.append(m.group(0))
                        for m in re.finditer(r"href=\"([^\"]*c0p\d+[^\"]*)\"", html2):
                            hrefs.append(urljoin(url, m.group(1)))
                        # Debug dump if still empty
                        if not hrefs:
                            try:
                                with open("debug_last_category.html", "w", encoding="utf-8") as f:
                                    f.write(html2)
                            except Exception:
                                pass
                    except Exception:
                        pass
                context.close()
                browser.close()
                # Normalize to absolute
                links = []
                for href in hrefs or []:
                    abs_url = href if isinstance(href, str) and href.startswith("http") else urljoin(url, href or "")
                    if abs_url.startswith("http"):
                        links.append(abs_url)
                return list(dict.fromkeys(links))
        except Exception:
            # fall back to static HTML parsing below
            pass

    html = _fetch_html(session, url, headers, use_browser=False)
    soup = BeautifulSoup(html, "lxml")
    links: List[str] = []
    for a in soup.select(product_link_selector):
        href = a.get("href") or a.get("data-href") or a.get("data-url")
        if not href:
            continue
        abs_url = href if href.startswith("http") else urljoin(url, href)
        if abs_url.startswith("http"):
            links.append(abs_url)
    # Also parse embedded JSON-LD for product URLs if present
    try:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(script.string or "")
            except Exception:
                continue
            def collect_urls(node):
                if isinstance(node, dict):
                    # Common list pages have itemListElement → item → url
                    if node.get("url") and isinstance(node.get("url"), str):
                        links.append(urljoin(url, node["url"]))
                    for v in node.values():
                        collect_urls(v)
                elif isinstance(node, list):
                    for v in node:
                        collect_urls(v)
            collect_urls(data)
    except Exception:
        pass
    # As a last resort, regex-scan raw HTML for Bershka-style product URLs containing 'c0p'
    try:
        base = url
        # href/data-* attributes
        for m in re.finditer(r"(?:href|data-href|data-url)=[\"']([^\"']*c0p\d+[^\"']*)", html):
            links.append(urljoin(base, m.group(1)))
        # absolute URLs in text
        for m in re.finditer(r"https?://[^\s\"']*c0p\d+[^\s\"']*", html):
            links.append(m.group(0))
    except Exception:
        pass
    return list(dict.fromkeys(links))


def scrape_category_for_products(session: PoliteSession, url: str, product_selector: str, product_selectors: Dict[str, str], headers: Optional[Dict[str, str]] = None, use_browser: bool = False) -> List[Dict]:
    """
    Extract products directly from category page without visiting individual product pages.
    This is useful for sites that block product detail pages but allow category scraping.
    """
    html = _fetch_html(session, url, headers, use_browser)
    if not html:
        print(f"[ERROR] Failed to fetch HTML for {url}")
        return []

    soup = BeautifulSoup(html, "lxml")
    products = []

    # Find all product containers
    product_elements = soup.select(product_selector)
    print(f"Found {len(product_elements)} product elements with selector: {product_selector}")

    for i, product_elem in enumerate(product_elements):
        try:
            product_data = {}

            # Debug: show product element structure for first few products
            if i < 2:
                print(f"Product {i+1} element attrs: {list(product_elem.attrs.keys())[:10]}")
                print(f"Product {i+1} href: {product_elem.get('href', 'N/A')}")
                print(f"Product {i+1} classes: {product_elem.get('class', [])}")
                print(f"Product {i+1} tag: {product_elem.name}")
                print(f"Product {i+1} children tags: {[child.name for child in product_elem.find_all() if child.name][:5]}")
                # Look for any img tags in the document near this product
                all_imgs = product_elem.find_all('img')
                print(f"Product {i+1} has {len(all_imgs)} img tags")

                # Look for JSON data in script tags that might contain product info
                if hasattr(soup, 'find_all'):
                    scripts = soup.find_all('script', type='application/json') or soup.find_all('script', string=lambda x: x and ('product' in x.lower() or 'item' in x.lower()))
                    json_scripts = [s for s in scripts if s.string and len(s.string.strip()) > 100]
                    print(f"Found {len(json_scripts)} potential JSON scripts with product data")

                    # Try to extract product data from JSON scripts
                    if json_scripts and not product_data.get('title'):  # Only if we haven't found title yet
                        for script in json_scripts[:5]:  # Check more scripts
                            try:
                                import json
                                script_content = script.string.strip()
                                if i < 1 and len(script_content) < 500:  # Debug: show short scripts
                                    print(f"Script content preview: {script_content[:200]}...")

                                # Try to clean the script content - sometimes there's extra content
                                original_content = script_content
                                if script_content.startswith('window.') or '=' in script_content[:50]:
                                    # Extract JSON part after assignment like "variable = {...}"
                                    equals_pos = script_content.find('=')
                                    if equals_pos >= 0:
                                        script_content = script_content[equals_pos + 1:].strip()
                                        # Remove trailing semicolon if present
                                        if script_content.endswith(';'):
                                            script_content = script_content[:-1].strip()

                                # Try to find JSON object bounds
                                json_start = script_content.find('{')
                                if json_start >= 0:
                                    script_content = script_content[json_start:]
                                    # Find matching closing brace
                                    brace_count = 0
                                    end_pos = json_start
                                    for j, char in enumerate(script_content):
                                        if char == '{':
                                            brace_count += 1
                                        elif char == '}':
                                            brace_count -= 1
                                            if brace_count == 0:
                                                end_pos = j + 1
                                                break
                                    script_content = script_content[:end_pos]

                                if i < 1:
                                    print(f"Attempting to parse cleaned content: {script_content[:100]}...")
                                    if script_content != original_content[:len(script_content)]:
                                        print(f"Content was modified from: {original_content[:100]}...")

                                data = json.loads(script_content)

                                # Debug: print JSON structure for first product
                                if i < 1:
                                    print(f"JSON structure keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                                    if isinstance(data, dict):
                                        for key, value in data.items():
                                            if isinstance(value, list) and len(value) > 0:
                                                print(f"  {key}: list with {len(value)} items")
                                                if len(value) > 0 and isinstance(value[0], dict):
                                                    print(f"    First item keys: {list(value[0].keys())[:5]}")

                                # Look for product data structures - try multiple patterns including Pull&Bear specific
                                products_data = None
                                if isinstance(data, dict):
                                    # Try various common patterns
                                    for key in ['products', 'items', 'productList', 'data', 'results', 'productGroups', 'bundleProductSummaries']:
                                        if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                                            products_data = data[key]
                                            if i < 1:
                                                print(f"Found products in '{key}' with {len(products_data)} items")
                                            break

                                if products_data and isinstance(products_data, list):
                                    # Find product by ID
                                    product_id = product_elem.get('data-product-id')
                                    if i < 1:
                                        print(f"Looking for product ID: {product_id}")

                                    for prod in products_data:
                                        if isinstance(prod, dict):
                                            # Try multiple ID field patterns
                                            prod_id = prod.get('id') or prod.get('productId') or prod.get('product_id') or prod.get('sku')
                                            if str(prod_id) == str(product_id):
                                                if i < 1:
                                                    print(f"Found matching product! Keys: {list(prod.keys())}")

                                                # Extract title - Pull&Bear specific patterns
                                                title = (prod.get('name') or prod.get('title') or prod.get('productName') or
                                                        prod.get('nameEn'))
                                                if title and not product_data.get('title'):
                                                    product_data['title'] = title

                                                # Extract description - Pull&Bear specific patterns
                                                desc = None
                                                if prod.get('detail') and isinstance(prod['detail'], dict):
                                                    desc = (prod['detail'].get('longDescription') or
                                                           prod['detail'].get('description') or
                                                           prod['detail'].get('shortDescription'))
                                                if not desc:
                                                    desc = (prod.get('description') or prod.get('shortDescription') or
                                                           prod.get('longDescription'))
                                                if desc and not product_data.get('description'):
                                                    product_data['description'] = desc

                                                # Extract price - Pull&Bear specific patterns (prices in cents)
                                                if not product_data.get('price'):
                                                    price_val = None

                                                    # Try getting price from sizes array (Pull&Bear structure)
                                                    if prod.get('sizes') and isinstance(prod['sizes'], list) and prod['sizes']:
                                                        first_size = prod['sizes'][0]
                                                        if isinstance(first_size, dict) and 'price' in first_size:
                                                            price_str = str(first_size['price'])
                                                            try:
                                                                # Convert from cents to actual price
                                                                price_val = float(price_str) / 100
                                                            except (ValueError, TypeError):
                                                                pass

                                                    # Fallback to other price patterns
                                                    if price_val is None:
                                                        price = prod.get('price')
                                                        if isinstance(price, dict):
                                                            # Handle nested price structures
                                                            price_val = (price.get('salePrice') or price.get('currentPrice') or
                                                                       price.get('price') or price.get('value'))
                                                        elif isinstance(price, (int, float)):
                                                            price_val = price
                                                        elif isinstance(price, str):
                                                            # Try to extract numeric price
                                                            match = re.search(r'(\d+(?:\.\d{2})?)', price)
                                                            price_val = float(match.group(1)) if match else None

                                                    if price_val and isinstance(price_val, (int, float)):
                                                        product_data['price'] = float(price_val)

                                                # Extract image URL - Pull&Bear specific patterns
                                                if not product_data.get('image_url'):
                                                    img_candidates = []

                                                    # Pull&Bear specific: check detail.colors[].image
                                                    if (prod.get('detail') and isinstance(prod['detail'], dict) and
                                                        prod['detail'].get('colors') and isinstance(prod['detail']['colors'], list)):
                                                        for color in prod['detail']['colors']:
                                                            if isinstance(color, dict) and color.get('image'):
                                                                img_data = color['image']
                                                                if isinstance(img_data, dict) and img_data.get('url'):
                                                                    img_candidates.append(img_data['url'])

                                                    # Also try xmedia structure (Pull&Bear)
                                                    if prod.get('detail') and isinstance(prod['detail'], dict):
                                                        xmedia = prod['detail'].get('xmedia')
                                                        if xmedia and isinstance(xmedia, list) and xmedia:
                                                            for media_set in xmedia:
                                                                if isinstance(media_set, dict) and media_set.get('xmediaItems'):
                                                                    items = media_set['xmediaItems']
                                                                    if isinstance(items, list) and items:
                                                                        for item in items:
                                                                            if isinstance(item, dict) and item.get('medias'):
                                                                                medias = item['medias']
                                                                                if isinstance(medias, list) and medias:
                                                                                    for media in medias:
                                                                                        if isinstance(media, dict) and media.get('url'):
                                                                                            img_candidates.append(media['url'])
                                                                                        break
                                                                            break
                                                                break

                                                    # Fallback to other patterns
                                                    img_candidates.extend([
                                                        prod.get('image'), prod.get('imageUrl'), prod.get('img'),
                                                        prod.get('mainImage'), prod.get('primaryImage'),
                                                        prod.get('picture'), prod.get('photo')
                                                    ])

                                                    # Also check nested image structures
                                                    if prod.get('images') and isinstance(prod['images'], list) and prod['images']:
                                                        img_candidates.append(prod['images'][0])
                                                    if prod.get('media') and isinstance(prod['media'], list) and prod['media']:
                                                        img_candidates.append(prod['media'][0])

                                                    for img_candidate in img_candidates:
                                                        if img_candidate:
                                                            if isinstance(img_candidate, dict):
                                                                # Handle nested image objects
                                                                img_url = (img_candidate.get('url') or img_candidate.get('src') or
                                                                         img_candidate.get('large') or img_candidate.get('medium'))
                                                            else:
                                                                img_url = img_candidate

                                                            if isinstance(img_url, str):
                                                                if img_url.startswith('http'):
                                                                    product_data['image_url'] = img_url
                                                                elif img_url.startswith('//'):
                                                                    product_data['image_url'] = f"https:{img_url}"
                                                                elif img_url.startswith('/'):
                                                                    # Construct full URL
                                                                    if '/cz/en/' in url:
                                                                        base_url = url.split('/cz/en/')[0]
                                                                    else:
                                                                        base_url = url.rsplit('/', 1)[0]
                                                                    product_data['image_url'] = base_url + img_url
                                                                break

                                                if i < 1:
                                                    print(f"Extracted: title='{product_data.get('title', 'N/A')}', price={product_data.get('price', 'N/A')}, image='{product_data.get('image_url', 'N/A')[:50] if product_data.get('image_url') else 'N/A'}'")
                                                break
                            except Exception as e:
                                if i < 1:
                                    print(f"JSON parsing error: {e}")
                                pass  # Continue to next script

            # Extract each field using the selectors
            for field, selector in product_selectors.items():
                # Check for dynamic URL construction first (before literal check)
                if field == "product_url" and isinstance(selector, str) and " + " in selector and "[data-" in selector:
                    # Handle URL construction like "'https://example.com/' + [data-articlecode] + '.html'"
                    try:
                        parts = selector.split(" + ")
                        url_parts = []
                        for part in parts:
                            part = part.strip()
                            if part.startswith("'") and part.endswith("'"):
                                url_parts.append(part[1:-1])  # Remove quotes
                            elif part.startswith("[data-") and part.endswith("]"):
                                attr_name = part[1:-1]  # Remove brackets
                                if attr_name in product_elem.attrs:
                                    url_parts.append(product_elem.attrs[attr_name])
                                else:
                                    url_parts.append("")  # Empty if attribute not found
                        product_data[field] = "".join(url_parts)
                    except Exception as e:
                        print(f"Error constructing {field}: {e}")
                elif field == "product_url" and isinstance(selector, str):
                    # Handle href extraction from current element or its descendants
                    if selector == "href" or selector.startswith("[href"):
                        # Extract href directly from current element (common for <a> tags)
                        href = product_elem.get("href") or product_elem.get(":href")  # Support Alpine.js :href
                        if href:
                            if href.startswith('http'):
                                product_data[field] = href
                            else:
                                product_data[field] = urljoin(url, href)
                    else:
                        # Use select_one to find element with href
                        elem = product_elem.select_one(selector)
                        if elem:
                            href = elem.get("href") or elem.get(":href")  # Support Alpine.js :href
                            if href:
                                if href.startswith('http'):
                                    product_data[field] = href
                                else:
                                    product_data[field] = urljoin(url, href)

                    # If we got a product URL, try to extract product ID from it
                    product_url = product_data.get("product_url")
                    if product_url and '/products/' in product_url:
                        # Extract product handle from URL like /products/product-handle
                        product_handle = product_url.split('/products/')[-1].split('?')[0].split('/')[0]
                        if product_handle and not product_data.get("external_id"):
                            product_data["external_id"] = product_handle
                        if product_handle and not product_data.get("product_id"):
                            product_data["product_id"] = product_handle
                # Check if this is a literal value (starts and ends with quotes)
                elif isinstance(selector, str) and selector.startswith("'") and selector.endswith("'"):
                    # Literal value - remove quotes
                    product_data[field] = selector[1:-1]
                elif field == "image":
                    # Handle image URLs specially
                    img_elem = product_elem.select_one(selector)
                    if img_elem:
                        img_src = img_elem.get("src") or img_elem.get("data-src") or ""
                        # Debug: show what we found
                        if i < 2:
                            print(f"Product {i+1} image src: '{img_src}'")
                        # Make relative URLs absolute
                        if img_src.startswith('//'):
                            img_src = f"https:{img_src}"
                        elif img_src.startswith('assets/') or img_src.startswith('/'):
                            # Try to construct full URL from base (handle different URL patterns)
                            if '/cz/en/' in url:
                                base_url = url.split('/cz/en/')[0]
                            elif '/en_us/' in url:
                                base_url = url.split('/en_us/')[0]
                            else:
                                base_url = url.rsplit('/', 1)[0]
                            img_src = urljoin(base_url + '/', img_src)
                        product_data["image_url"] = img_src
                    else:
                        if i < 2:
                            print(f"Product {i+1} image selector '{selector}' found no elements")
                elif field == "price":
                    # Handle price extraction
                    price_elem = product_elem.select_one(selector)
                    if price_elem:
                        price_text = price_elem.get_text(strip=True)
                        # Extract numeric price from text like "$39.99"
                        price_match = re.search(r'(\d+(?:\.\d{2})?)', price_text)
                        if price_match:
                            product_data["price"] = float(price_match.group(1))
                elif selector.startswith("[data-") and selector.endswith("]"):
                    # Handle data attributes on current element
                    # Parse selector like [data-testid*='productCard'] to extract attribute name
                    bracket_content = selector[1:-1]  # Remove brackets
                    if '=' in bracket_content:
                        # Handle selectors like [data-testid*='productCard']
                        attr_part = bracket_content.split('=')[0]
                        attr_name = attr_part.split('*')[0]  # Remove * if present
                    else:
                        attr_name = bracket_content
                    if attr_name in product_elem.attrs:
                        attr_value = product_elem.attrs[attr_name]
                        # Special handling for Gymshark product IDs in data-testid
                        if field in ["external_id", "product_id"] and attr_name == "data-testid" and "productCard" in str(attr_value) and "Wishlist" not in str(attr_value):
                            # Extract product ID from data-testid like "plp-productCard-6806189605066-select"
                            match = re.search(r'productCard-(\d+)', str(attr_value))
                            if match:
                                product_data[field] = match.group(1)
                            else:
                                product_data[field] = attr_value
                        else:
                            product_data[field] = attr_value
                else:
                    # Handle other text fields
                    elem = product_elem.select_one(selector)
                    if elem:
                        product_data[field] = elem.get_text(strip=True)

            # Ensure we have required fields
            if not product_data.get("external_id") and not product_data.get("product_id"):
                if i < 5:  # Debug first 5 failed extractions
                    try:
                        print(f"Product {i+1} failed - no external_id. Element attrs: {list(product_elem.attrs.keys())[:5]}")
                        if product_elem.get('data-testid'):
                            print(f"  data-testid: {product_elem.get('data-testid')}")
                        if product_elem.get('href'):
                            print(f"  href: {product_elem.get('href')[:50]}...")
                        print(f"  Available data: {product_data}")
                    except UnicodeEncodeError:
                        print(f"Product {i+1} failed - no external_id. Available data: [Unicode encoding error]")
                continue

            # Provide defaults for required fields
            if not product_data.get("title"):
                product_data["title"] = f"Pull&Bear Product {product_data.get('external_id', 'Unknown')}"
            if not product_data.get("image_url"):
                # Provide a data URL placeholder image since database requires it
                product_data["image_url"] = "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAwIiBoZWlnaHQ9IjYwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZGRkIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCwgc2Fucy1zZXJpZiIgZm9udC1zaXplPSIyNCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPk5vIEltYWdlPC90ZXh0Pjwvc3ZnPg=="

            products.append(product_data)
            if i < 3:  # Debug first 3 products
                try:
                    print(f"Product {i+1} data: title='{product_data.get('title', 'N/A')}', price={product_data.get('price', 'N/A')}, has_image={bool(product_data.get('image_url'))}")
                except UnicodeEncodeError:
                    print(f"Product {i+1} data: [Unicode encoding error in product data]")

        except Exception as e:
            print(f"Error extracting product {i+1}: {e}")
            continue

    print(f"Successfully extracted {len(products)} products from {len(product_elements)} elements")
    return products


