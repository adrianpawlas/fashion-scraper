from typing import Any, Dict, List
import re


def _normalize_availability(raw_availability: Any) -> str:
	"""Normalize availability to one of: 'in_stock', 'out_of_stock', 'unknown'."""
	if isinstance(raw_availability, bool):
		return "in_stock" if raw_availability else "out_of_stock"
	if raw_availability is None:
		return "unknown"
	text = str(raw_availability).strip().lower()
	mapping = {
		"in_stock": "in_stock",
		"instock": "in_stock",
		"in stock": "in_stock",
		"available": "in_stock",
		"out_of_stock": "out_of_stock",
		"out-of-stock": "out_of_stock",
		"outofstock": "out_of_stock",
		"sold_out": "out_of_stock",
		"sold-out": "out_of_stock",
		"sold out": "out_of_stock",
		"unavailable": "out_of_stock",
		"coming_soon": "unknown",
		"coming-soon": "unknown",
		"preorder": "unknown",
		"pre-order": "unknown",
	}
	return mapping.get(text, "unknown")


def to_supabase_row(raw: Dict[str, Any]) -> Dict[str, Any]:
	"""Map a generic scraped product to your Supabase products schema.

	Expected minimal input keys (from API/HTML):
	- source: str (e.g., 'manual', 'api', 'awin')
	- external_id: str (stable per merchant)
	- merchant_name: str
	- merchant_id: str|int (optional)
	- title: str
	- description: str (optional)
	- brand: str (optional)
	- price: float|str (optional)
	- currency: str (e.g., 'GBP')
	- image_url: str
	- product_url: str
	- affiliate_url: str (optional)
	- availability: str|bool (optional)

	All other columns are left null unless provided.
	"""
	row: Dict[str, Any] = {}
	row["source"] = raw.get("source") or "manual"
	row["external_id"] = str(raw.get("external_id") or raw.get("product_id") or raw.get("product_url"))
	row["merchant_name"] = raw.get("merchant") or raw.get("merchant_name")
	if raw.get("merchant_id") is not None:
		row["merchant_id"] = raw.get("merchant_id")
	row["title"] = raw.get("title") or "Unknown title"
	row["description"] = raw.get("description")
	row["brand"] = raw.get("brand")
	row["price"] = raw.get("price")
	row["currency"] = raw.get("currency")
	row["image_url"] = raw.get("image_url")
	row["product_url"] = raw.get("product_url")
	row["affiliate_url"] = raw.get("affiliate_url")
	avail = raw.get("in_stock") if "in_stock" in raw else raw.get("availability")
	row["availability"] = _normalize_availability(avail)
	# passthroughs if provided
	for key in ("sku", "gtin_upc_ean", "category", "subcategory", "gender", "tags", "color_names"):
		if raw.get(key) is not None:
			row[key] = raw.get(key)

	# Normalize color_names to a flat list of strings
	colors_val = row.get("color_names")
	if isinstance(colors_val, str):
		val = colors_val.strip()
		row["color_names"] = ([val] if val else [])
	elif isinstance(colors_val, list):
		flat: List[str] = []
		for c in colors_val:
			if isinstance(c, list):
				for s in c:
					if isinstance(s, str) and s.strip():
						flat.append(s.strip())
			elif isinstance(c, str) and c.strip():
				flat.append(c.strip())
		# de-dupe preserving order
		seen: Dict[str, bool] = {}
		unique: List[str] = []
		for s in flat:
			key = s.lower()
			if not seen.get(key):
				seen[key] = True
				unique.append(s)
		row["color_names"] = unique
	else:
		row["color_names"] = []

	# Normalize sizes: accept str, list[str], or nested lists → text (comma-separated)
	size_val = raw.get("size") or raw.get("sizes") or raw.get("available_sizes")
	try:
		if isinstance(size_val, list):
			flat_sizes: List[str] = []
			for s in size_val:
				if isinstance(s, list):
					for t in s:
						if isinstance(t, str) and t.strip():
							flat_sizes.append(t.strip())
				elif isinstance(s, str) and s.strip():
					flat_sizes.append(s.strip())
			row["size"] = ", ".join(dict.fromkeys(flat_sizes)) if flat_sizes else None
		elif isinstance(size_val, str):
			row["size"] = size_val.strip() or None
	except Exception:
		pass

	# Build product_url from template if missing
	if not row.get("product_url") and raw.get("product_url_template") and raw.get("seo_keyword"):
		# Support extended templates: {keyword}, {id}, {discern_id}
		kw = raw.get("seo_keyword")
		pid = raw.get("seo_product_id") or raw.get("id")
		discern = str(raw.get("external_id") or raw.get("product_id") or "")
		tmpl = str(raw.get("product_url_template"))
		# Try full format first, then degrade
		formatted = None
		try:
			formatted = tmpl.format(keyword=kw, id=pid, discern_id=discern)
		except Exception:
			try:
				formatted = tmpl.format(keyword=kw)
			except Exception:
				formatted = None
		if formatted:
			row["product_url"] = formatted

	# Normalize price from minor units (cents) to decimal if needed
	try:
		price_val = row.get("price")
		if price_val is not None:
			# Handle common price formats: integers in minor units, "49.90", "CZK849", "$49.90"
			if isinstance(price_val, (int, float)):
				# If it's a large integer, assume minor units (e.g., 4990 -> 49.90)
				if isinstance(price_val, int) and price_val >= 1000:
					row["price"] = price_val / 100.0
				else:
					row["price"] = float(price_val)
			elif isinstance(price_val, str):
				s = price_val.strip()
				# Remove currency symbols and letters
				s_clean = re.sub(r"[^0-9.,]", "", s)
				# Replace comma as decimal if needed
				if s_clean.count(",") == 1 and s_clean.count(".") == 0:
					s_clean = s_clean.replace(",", ".")
				# Remove thousand separators
				if s_clean.count(".") > 1:
					parts = s_clean.split(".")
					s_clean = "".join(parts[:-1]) + "." + parts[-1]
				if s_clean:
					num = float(s_clean)
					# If looks like minor units (>= 1000 and no decimal), scale down
					if num >= 1000 and abs(num - int(num)) < 1e-9:
						row["price"] = num / 100.0
					else:
						row["price"] = num
	except Exception:
		pass
	# If no color_names present, try extracting a trailing color token from description
	try:
		if not row.get("color_names") and isinstance(row.get("description"), str):
			desc_text = row.get("description") or ""
			m = re.search(r"(?:\s[-|]\s|\s*[\[(])([A-Za-z][A-Za-z\-/ ]{1,24})[)\]]?\s*$", desc_text)
			if m:
				candidate = m.group(1).strip()
				if candidate:
					row["color_names"] = [candidate]
	except Exception:
		pass

	# Clean description by removing color tokens if present
	try:
		desc = row.get("description")
		colors: List[str] = row.get("color_names") or []
		if isinstance(desc, str) and isinstance(colors, list) and colors:
			for c in [str(c).strip() for c in colors if isinstance(c, str) and str(c).strip()]:
				# Remove the color word with word boundaries (case-insensitive)
				pattern = re.compile(rf"\b{re.escape(c)}\b", re.IGNORECASE)
				desc = pattern.sub("", desc)
			# Remove common leftover separators at ends or doubled
			desc = re.sub(r"\s*[-|]\s*$", "", desc)
			desc = re.sub(r"^[\-|]\s*", "", desc)
			desc = re.sub(r"\s{2,}", " ", desc)
			desc = desc.strip("- |,;:()[] ")
			if desc:
				row["description"] = desc
			else:
				# if emptied, fallback to title
				row["description"] = row.get("title")
	except Exception:
		pass

	# Build metadata json: include raw fields that are not in main columns, plus _meta
	try:
		meta: Dict[str, Any] = {}
		if isinstance(raw.get("_meta"), dict):
			meta.update(raw["_meta"])  # type: ignore[arg-type]
		# include helpful raw context when present
		for k in ("_raw_item", "_raw_html_len", "seo", "detail", "xmedia"):
			if raw.get(k) is not None:
				meta[k] = raw.get(k)
		# attach original price/currency fields pre-normalization when available
		if raw.get("price") is not None and "original_price" not in meta:
			meta["original_price"] = raw.get("price")
		if raw.get("currency") is not None and "original_currency" not in meta:
			meta["original_currency"] = raw.get("currency")
		row["metadata"] = meta or None
	except Exception:
		pass
	return row


