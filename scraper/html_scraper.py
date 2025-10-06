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


