from typing import Any, Dict, List, Optional
import re


def _format_price_string(price_data: Any, currency: Optional[str] = None) -> Optional[str]:
	"""
	Format price data into comma-separated currency format (e.g., "20USD,450CZK,75PLN").
	
	Accepts:
	- String already in format "20USD,450CZK,75PLN" -> returns as-is
	- String like "20" or "20.99" with currency -> formats as "20USD"
	- Dict like {"USD": 20, "CZK": 450} -> formats as "20USD,450CZK"
	- List of dicts like [{"price": 20, "currency": "USD"}, ...] -> formats as "20USD,450CZK"
	- Single numeric value with currency -> formats as "20USD"
	"""
	if price_data is None:
		return None
	
	# If already a string in the expected format (contains currency codes), return as-is
	if isinstance(price_data, str):
		price_str = price_data.strip()
		# Check if it looks like already formatted (contains currency codes)
		if re.search(r'[A-Z]{3}', price_str):
			return price_str
		# Otherwise, try to format with provided currency
		if currency:
			try:
				# Try to extract numeric value
				num_str = re.sub(r'[^0-9.,]', '', price_str)
				if num_str:
					# Handle decimal separators
					if ',' in num_str and '.' in num_str:
						# Both present - assume comma is thousands, dot is decimal
						num_str = num_str.replace(',', '')
					elif ',' in num_str:
						# Only comma - could be decimal or thousands
						if num_str.count(',') == 1 and len(num_str.split(',')[1]) <= 2:
							num_str = num_str.replace(',', '.')
						else:
							num_str = num_str.replace(',', '')
					if num_str:
						return f"{num_str}{currency}"
			except Exception:
				pass
		return price_str if price_str else None
	
	# If dict with currency keys
	if isinstance(price_data, dict):
		price_parts = []
		for curr, val in price_data.items():
			if val is not None and isinstance(curr, str) and len(curr) == 3:
				try:
					# Convert value to string, removing unnecessary decimals
					val_str = str(float(val)) if isinstance(val, (int, float)) else str(val)
					# Remove trailing .0 if present
					if val_str.endswith('.0'):
						val_str = val_str[:-2]
					price_parts.append(f"{val_str}{curr.upper()}")
				except (ValueError, TypeError):
					continue
		return ",".join(price_parts) if price_parts else None
	
	# If list of price objects
	if isinstance(price_data, list):
		price_parts = []
		for item in price_data:
			if isinstance(item, dict):
				# Try different key patterns
				price_val = item.get('price') or item.get('value') or item.get('amount')
				price_curr = item.get('currency') or item.get('curr') or item.get('code')
				if price_val is not None and price_curr:
					try:
						val_str = str(float(price_val)) if isinstance(price_val, (int, float)) else str(price_val)
						if val_str.endswith('.0'):
							val_str = val_str[:-2]
						price_parts.append(f"{val_str}{str(price_curr).upper()}")
					except (ValueError, TypeError):
						continue
		return ",".join(price_parts) if price_parts else None
	
	# If single numeric value with currency
	if isinstance(price_data, (int, float)) and currency:
		# Handle Zara API prices in cents (minor units)
		# If it's a large integer >= 1000, assume it's in cents and convert
		if isinstance(price_data, int) and price_data >= 1000:
			val_str = str(price_data / 100.0)
		else:
			val_str = str(float(price_data))
		# Remove trailing .0 if present
		if val_str.endswith('.0'):
			val_str = val_str[:-2]
		return f"{val_str}{currency}"
	
	return None


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
	- price: str|dict|list (optional) - formatted as "20USD,450CZK,75PLN" or dict/list of prices
	- sale: str|dict|list (optional) - sale prices in same format, null if no sale
	- image_url: str
	- product_url: str
	- affiliate_url: str (optional)

	All other columns are left null unless provided.
	"""
	import hashlib

	row: Dict[str, Any] = {}

	# Generate deterministic ID using the most unique identifier available
	source = raw.get("source") or "zara"
	external_id = raw.get("external_id") or raw.get("product_id")
	product_url = raw.get("product_url")

	# Prefer external_id/product_id for uniqueness, fall back to product_url if needed
	if external_id:
		# Use source + external_id for maximum uniqueness
		id_string = f"{source}:{external_id}"
		row["id"] = hashlib.sha256(id_string.encode('utf-8')).hexdigest()
	else:
		# Fallback to product_url if no external_id (shouldn't happen for Zara)
		if source and product_url:
			id_string = f"{source}:{product_url}"
			row["id"] = hashlib.sha256(id_string.encode('utf-8')).hexdigest()
		else:
			# Last resort - use whatever we have
			row["id"] = str(raw.get("external_id") or raw.get("product_id") or raw.get("product_url") or "unknown")

	row["source"] = source
	row["title"] = raw.get("title") or "Unknown title"
	row["description"] = raw.get("description")
	row["brand"] = raw.get("brand")
	row["image_url"] = raw.get("image_url")
	row["product_url"] = product_url
	row["affiliate_url"] = raw.get("affiliate_url")
	# Set second_hand to FALSE for all current brands (they are not second-hand marketplaces)
	row["second_hand"] = False
	
	# Format price as comma-separated currencies (e.g., "20USD,450CZK,75PLN")
	price_data = raw.get("price")
	currency = raw.get("currency")  # Fallback currency if price is single value
	row["price"] = _format_price_string(price_data, currency)
	
	# Format sale price (same format, null if no sale)
	sale_data = raw.get("sale") or raw.get("sale_price") or raw.get("salePrice")
	row["sale"] = _format_price_string(sale_data, currency) if sale_data else None

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

	# Price and sale are already formatted by _format_price_string above
	# No additional normalization needed - they're stored as text strings

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


