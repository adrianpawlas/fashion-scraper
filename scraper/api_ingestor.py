from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup

import jmespath

from .http_client import PoliteSession


def _is_allowed_image_url(image_url: str) -> bool:
    """
    Check if an image URL contains allowed image types.
    Only allows images with -e1, -ult21, or -s suffixes.
    """
    if not image_url:
        return False

    # Check for allowed suffixes before file extension
    allowed_patterns = ['-e1', '-ult21', '-s']
    for pattern in allowed_patterns:
        if pattern in image_url:
            return True
    return False


def flatten_product(item: Dict[str, Any], mapping: Dict[str, Any]) -> Dict[str, Any]:
	"""Map arbitrary JSON fields to our product schema using JMESPath expressions."""
	out: Dict[str, Any] = {}
	for dest, expr in mapping.items():
		# Allow null/empty expressions in config to yield None without raising
		if expr is None or (isinstance(expr, str) and expr.strip() == ""):
			out[dest] = None
			continue
		# Support a list of fallback expressions: first non-null wins
		if isinstance(expr, list):
			value = None
			for candidate in expr:
				if candidate is None or (isinstance(candidate, str) and candidate.strip() == ""):
					continue
				value = jmespath.search(candidate, item)
				if value is not None:
					# For image_url field, skip data URLs (base64 placeholders) and non-allowed image types
					if dest == "image_url" and isinstance(value, str):
						if value.startswith("data:"):
							continue
						if not _is_allowed_image_url(value):
							continue
					break
			out[dest] = value
		else:
			value = jmespath.search(expr, item)
			# For image_url field, skip data URLs (base64 placeholders) and non-allowed image types
			if dest == "image_url" and isinstance(value, str):
				if value.startswith("data:"):
					value = None
				elif not _is_allowed_image_url(value):
					value = None
			out[dest] = value
	return out


def ingest_api(session: PoliteSession, endpoint: str, jmes_items: Any, field_map: Dict[str, Any], request_kwargs: Optional[Dict[str, Any]] = None, debug: bool = False) -> List[Dict[str, Any]]:
	data = session.fetch_json(endpoint, **(request_kwargs or {}))
	if debug:
		print(f"Debug: API response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
	# Support list of fallback items paths: first that yields items wins
	items_paths: List[str] = [jmes_items] if isinstance(jmes_items, str) else list(jmes_items or [])
	items = []
	for ip in items_paths or [""]:
		try:
			items = jmespath.search(ip, data) or []
			if debug:
				print(f"Debug: Tried items_path '{ip}', found {len(items)} items")
			if items:
				break
		except Exception as e:
			if debug:
				print(f"Debug: Failed items_path '{ip}': {e}")
			continue
	products: List[Dict[str, Any]] = []
	with_id = 0
	with_image = 0
	for item in items:
		prod = flatten_product(item, field_map)
		# Preserve full original item for downstream metadata storage
		try:
			prod["_raw_item"] = item
			prod["_meta"] = {"source": "api", "endpoint": endpoint}
		except Exception:
			pass
		# Ensure at least an identifier exists
		if not (prod.get("external_id") or prod.get("product_id")):
			continue
		with_id += 1
		# Skip if required fields (like image_url) are missing
		if "image_url" in field_map and not prod.get("image_url"):
			continue
		with_image += 1
		products.append(prod)
	if debug:
		try:
			pg = data.get("productGroups") if isinstance(data, dict) else None
			print(f"Debug: matched {len(items)} items; with_id={with_id}; with_image={with_image}; productGroups={len(pg) if isinstance(pg, list) else 'n/a'}")
			if items:
				# print available keys from first item to refine mapping
				first = items[0]
				if isinstance(first, dict):
					print(f"Debug: first item keys: {list(first.keys())[:15]}")
		except Exception:
			pass
	return products


def discover_category_urls(session: PoliteSession, categories_conf: Dict[str, Any], request_kwargs: Optional[Dict[str, Any]] = None) -> List[str]:
	"""Discover category product endpoints from a configured categories JSON.

	Config supports either direct URLs or IDs with a template:
	- endpoint: str (JSON URL to fetch)
	- items_path: str (JMESPath to list of category objects or URLs)
	- url_path: str (JMESPath relative to each item that yields a URL)
	- id_path: str (JMESPath relative to each item that yields an ID)
	- url_template: str (format string with {id})
	"""
	endpoints: List[str] = []
	data = session.fetch_json(categories_conf["endpoint"], **(request_kwargs or {}))
	items: List[Any] = jmespath.search(categories_conf["items_path"], data) or []
	url_path = categories_conf.get("url_path")
	id_path = categories_conf.get("id_path")
	url_template = categories_conf.get("url_template")
	for item in items:
		# Direct URL strings
		if isinstance(item, str) and item.startswith("http"):
			endpoints.append(item)
			continue
		# URL from path
		if url_path:
			url_val = jmespath.search(url_path, item)
			if isinstance(url_val, str) and url_val.startswith("http"):
				endpoints.append(url_val)
				continue
		# ID + template
		if id_path and url_template:
			cid = jmespath.search(id_path, item)
			if cid is not None:
				endpoints.append(url_template.format(id=cid))
	# Fallback: recursively extract category ids if above produced no endpoints
	if not endpoints and categories_conf.get("url_template"):
		def _extract_ids(node: Any, acc: List[str]) -> None:
			# collect any numeric-like id fields
			try:
				if isinstance(node, dict):
					# prefer ids on nodes that look like categories
					if "id" in node and isinstance(node["id"], (int, str)):
						val = str(node["id"]).strip()
						if val.isdigit():
							acc.append(val)
					for v in node.values():
						_extract_ids(v, acc)
				elif isinstance(node, list):
					for v in node:
						_extract_ids(v, acc)
			except Exception:
				pass
		collected: List[str] = []
		_extract_ids(data, collected)
		seen_ids: Dict[str, bool] = {}
		for cid in collected:
			if not seen_ids.get(cid):
				seen_ids[cid] = True
				endpoints.append(categories_conf["url_template"].format(id=cid))

	# de-duplicate while preserving order
	seen: Dict[str, bool] = {}
	unique: List[str] = []
	for u in endpoints:
		if not seen.get(u):
			seen[u] = True
			unique.append(u)
	return unique


def discover_from_html(session: PoliteSession, html_conf: Dict[str, Any]) -> List[str]:
	"""Discover product endpoints starting from category HTML pages.

	Config keys:
	- category_pages: list[str] starting HTML URLs
	- category_link_selector: CSS selector to find category links on those pages
	- link_href_filter: optional substring to keep only relevant links
	- product_api_from_category: format string taking {category_id} or {path}
	- extract_category_id_regex: optional regex with one capture group to extract an ID from URL/path
	- extract_category_query_param: optional query string param name (e.g., 'v1') to use as {category_id}
	"""
	endpoints: List[str] = []
	pages: List[str] = html_conf.get("category_pages") or []
	selector: str = html_conf.get("category_link_selector") or "a"
	filter_sub: Optional[str] = html_conf.get("link_href_filter")
	api_template: str = html_conf.get("product_api_from_category") or ""
	regex: Optional[str] = html_conf.get("extract_category_id_regex")
	query_param: Optional[str] = html_conf.get("extract_category_query_param")
	for page in pages:
		try:
			resp = session.get(page)
			resp.raise_for_status()
			soup = BeautifulSoup(resp.text, "lxml")
			# Attempt to extract category ids directly from page HTML (robust fallback)
			try:
				import re
				candidates: List[str] = []
				for pat in [r"/category/(\d+)/products", r"categoryId[\"']?\s*[:=]\s*[\"']?(\d+)", r"[?&]v2=(\d+)"]:
					for m in re.finditer(pat, resp.text):
						candidates.append(m.group(1))
				# de-duplicate while preserving order
				seen_ids: Dict[str, bool] = {}
				for cid_p in candidates:
					if seen_ids.get(cid_p):
						continue
					seen_ids[cid_p] = True
					if "{category_id}" in api_template:
						endpoint_p = api_template.format(category_id=cid_p, path=page)
						if "ajax=true" not in endpoint_p:
							endpoint_p = f"{endpoint_p}{'&' if '?' in endpoint_p else '?'}ajax=true"
						if endpoint_p.startswith("http"):
							endpoints.append(endpoint_p)
			except Exception:
				pass
			# Also derive endpoint from the category page URL itself
			try:
				path_page = page
				cid_page = None
				if query_param:
					from urllib.parse import urlparse, parse_qs
					parsed_p = urlparse(path_page)
					qs_p = parse_qs(parsed_p.query)
					vals_p = qs_p.get(query_param)
					if vals_p and vals_p[0]:
						cid_page = vals_p[0]
				if regex and cid_page is None:
					import re
					m_p = re.search(regex, path_page)
					if m_p:
						cid_page = m_p.group(1)
				if "{category_id}" in api_template and cid_page:
					endpoint_p = api_template.format(category_id=cid_page, path=path_page)
					if endpoint_p.startswith("http"):
						endpoints.append(endpoint_p)
			except Exception:
				pass
			for a in soup.select(selector):
				href = a.get("href") or ""
				if not href or (filter_sub and filter_sub not in href):
					continue
				path = href if href.startswith("http") else href
				cid = None
				# Try query parameter first if requested
				if query_param:
					try:
						from urllib.parse import urlparse, parse_qs
						parsed = urlparse(path)
						qs = parse_qs(parsed.query)
						vals = qs.get(query_param)
						if vals and vals[0]:
							cid = vals[0]
					except Exception:
						pass
				if regex:
					import re
					m = re.search(regex, path)
					if m and not cid:
						cid = m.group(1)
				if "{category_id}" in api_template and cid is None:
					continue
				endpoint = api_template.format(category_id=cid or "", path=path)
				# Ensure ajax=true is present if the site expects JSON via this flag
				if "ajax=true" not in endpoint:
					endpoint = f"{endpoint}{'&' if '?' in endpoint else '?'}ajax=true"
				if endpoint.startswith("http"):
					endpoints.append(endpoint)
		except Exception:
			continue
	# de-dupe preserving order
	seen: Dict[str, bool] = {}
	unique: List[str] = []
	for u in endpoints:
		if not seen.get(u):
			seen[u] = True
			unique.append(u)
	return unique

