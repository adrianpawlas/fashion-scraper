from typing import Dict, List, Optional
import re
import xml.etree.ElementTree as ET

from .http_client import PoliteSession


def _parse_xml_for_tags(xml_text: str, tag: str) -> List[str]:
	values: List[str] = []
	try:
		root = ET.fromstring(xml_text)
		# Namespaces are common in sitemaps; match by localname
		for elem in root.iter():
			if elem.tag.endswith(tag):
				if elem.text and elem.text.strip():
					values.append(elem.text.strip())
	except Exception:
		pass
	return values


def _fetch_text(session: PoliteSession, url: str, headers: Optional[Dict[str, str]]) -> str:
	resp = session.get(url, headers=headers)
	resp.raise_for_status()
	return resp.text


def fetch_sitemap_urls(session: PoliteSession, sitemap_urls: List[str], headers: Optional[Dict[str, str]] = None, url_contains: Optional[List[str]] = None, max_nested: int = 3) -> List[str]:
	"""Recursively fetch sitemap and sitemap-index URLs and return product/page URLs.

	- sitemap_urls: list of sitemap.xml or sitemap-index.xml URLs
	- url_contains: keep only URLs containing any of these substrings (optional)
	"""
	seen: Dict[str, bool] = {}
	results: List[str] = []
	queue: List[Dict[str, str]] = [{"url": u, "kind": "index"} for u in (sitemap_urls or [])]
	depth = 0
	while queue and depth < max_nested:
		next_queue: List[Dict[str, str]] = []
		for item in queue:
			u = item["url"]
			if seen.get(u):
				continue
			seen[u] = True
			try:
				txt = _fetch_text(session, u, headers)
				# Find nested sitemap locations and url locs
				nested = _parse_xml_for_tags(txt, "sitemap")
				locs = _parse_xml_for_tags(txt, "loc")
				# If we found nested <sitemap> tags, enqueue their <loc> values
				if nested:
					for loc in _parse_xml_for_tags(txt, "loc"):
						if loc and loc.endswith(".xml"):
							next_queue.append({"url": loc, "kind": "index"})
				# Also treat any .xml locs as nested sitemaps
				for loc in locs:
					if loc and loc.endswith(".xml"):
						next_queue.append({"url": loc, "kind": "index"})
				# Collect non-XML locs as page URLs
				for loc in locs:
					if loc and not loc.endswith(".xml"):
						results.append(loc)
			except Exception:
				continue
		queue = next_queue
		depth += 1
	# Filter by substrings if requested
	if url_contains:
		keep: List[str] = []
		for u in results:
			for sub in url_contains:
				if sub and (sub in u):
					keep.append(u)
					break
		results = keep
	# de-dup preserve order
	unique: List[str] = []
	seen2: Dict[str, bool] = {}
	for u in results:
		if not seen2.get(u):
			seen2[u] = True
			unique.append(u)
	return unique


