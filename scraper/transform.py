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
	- external_id: str (stable per merchant) - will be used as the 'id' field
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

	All other columns are left null unless provided.
	"""
	import hashlib

	row: Dict[str, Any] = {}

	# Generate deterministic ID using source + product_url (matching your working database.py)
	source = raw.get("source") or "zara"
	product_url = raw.get("product_url")
	if source and product_url:
		id_string = f"{source}:{product_url}"
		row["id"] = hashlib.sha256(id_string.encode('utf-8')).hexdigest()
	else:
		row["id"] = str(raw.get("external_id") or raw.get("product_id") or raw.get("product_url"))

	row["source"] = source
	row["title"] = raw.get("title") or "Unknown title"
	row["description"] = raw.get("description")
	row["brand"] = raw.get("brand")
	row["price"] = raw.get("price")
	row["currency"] = raw.get("currency", "USD")
	row["image_url"] = raw.get("image_url")
	row["product_url"] = product_url
	row["affiliate_url"] = raw.get("affiliate_url")
	# Set second_hand to FALSE for all current brands (they are not second-hand marketplaces)
	row["second_hand"] = False

	# Normalize gender to "men" or "women"
	raw_gender = raw.get("gender")
	if raw_gender:
		gender_str = str(raw_gender).strip().lower()
		# Check for women first (since "woman" contains "man")
		if any(word in gender_str for word in ["women", "female", "woman", "lady", "girl"]):
			row["gender"] = "women"
		elif any(word in gender_str for word in ["men", "male", "man", "guy", "boy"]):
			row["gender"] = "men"
		else:
			row["gender"] = raw_gender  # Keep original if doesn't match

	# Category detection based on Zara category IDs
	category_id = None
	endpoint = raw.get("_meta", {}).get("endpoint")
	if endpoint:
		# Extract category ID from endpoint URL like "https://www.zara.com/us/en/category/2417728/products?ajax=true"
		import re
		match = re.search(r'/category/(\d+)/', str(endpoint))
		if match:
			category_id = match.group(1)

	# Accessory categories (bags, jewelry, lingerie, perfumes, beauty)
	accessory_category_ids = {
		"2417728",  # women's bags
		"2418989",  # women's accessories & jewelry
		"2419807",  # women's lingerie
		"2419833",  # women's perfumes
		"2418919",  # women's beauty
		"2419160",  # women's shoes (footwear)
	}

	if category_id in accessory_category_ids:
		if category_id == "2419160":
			row["category"] = "footwear"
		else:
			row["category"] = "accessory"
	else:
		row["category"] = None  # Clothing items get null category


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

	# Build metadata json: include base info, plus site/source-specific _meta and useful raw fields
	try:
		meta: Dict[str, Any] = {}
		if raw.get("merchant_name"):
			meta["merchant_name"] = raw.get("merchant_name")
		if raw.get("country"):
			meta["country"] = raw.get("country")
		if raw.get("original_currency"):
			meta["original_currency"] = raw.get("original_currency")
		if meta:
			import json
			row["metadata"] = json.dumps(meta)
	except Exception:
		pass

	return row


