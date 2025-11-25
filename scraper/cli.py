import argparse
from datetime import datetime
from typing import Dict, List

from .config import load_env, load_sites_config, get_site_configs, get_default_headers, get_supabase_env
from .http_client import PoliteSession
from .db import SupabaseDB
from .api_ingestor import ingest_api, discover_category_urls, discover_from_html
from .transform import to_supabase_row
# from .html_scraper import scrape_category_for_links, scrape_product_page, scrape_category_for_products
from .sitemap import fetch_sitemap_urls
from .embeddings import get_image_embedding


def run_for_site(site: Dict, session: PoliteSession, db: SupabaseDB, sync: bool = False, limit: int = 0, dry_run: bool = False) -> int:
	brand = site.get("brand", "Unknown")
	merchant = site.get("merchant", brand)
	dbg = bool(site.get("debug"))
	collected: List[Dict] = []
	if site.get("api"):
		api_conf = site["api"]
		request_kwargs = {}
		if "headers" in api_conf:
			# merge default session headers with site-specific headers
			request_kwargs["headers"] = {**session.session.headers, **api_conf["headers"]}
		if "params" in api_conf:
			request_kwargs["params"] = api_conf["params"]

		# Prewarm cookies/session by hitting listed URLs first (helps avoid 403)
		for warm_url in api_conf.get("prewarm", []) or api_conf.get("prewarm_urls", []):
			try:
				session.get(warm_url, headers=request_kwargs.get("headers"))
			except Exception:
				pass
		dbg = dbg or bool(api_conf.get("debug"))
		endpoints: List[str] = []
		if isinstance(api_conf.get("endpoints"), list) and api_conf.get("endpoints"):
			endpoints.extend(api_conf["endpoints"])
		elif api_conf.get("endpoint"):
			endpoints.append(api_conf["endpoint"])
		# Optionally discover category-specific endpoints
		if api_conf.get("discover_categories"):
			try:
				found = discover_category_urls(session, api_conf["discover_categories"], request_kwargs)
				if found:
					endpoints = found
			except Exception:
				pass
		# Optionally discover endpoints via HTML category pages
		if api_conf.get("discover_categories_html"):
			try:
				found_html = discover_from_html(session, api_conf["discover_categories_html"])
				if found_html:
					endpoints = found_html
			except Exception:
				pass
		# Debug: print discovered endpoints summary
		if dbg:
			try:
				print(f"Debug: discovered {len(endpoints)} endpoints")
				for ep in endpoints[:5]:
					print(f"Debug endpoint: {ep}")
			except Exception:
				pass
		products = []
		for ep in endpoints:
			try:
				batch = ingest_api(
					session,
					ep,
					api_conf["items_path"],
					api_conf["field_map"],
					request_kwargs,
					dbg,
				)
				# If JSON returns items, use them; otherwise try HTML fallback if configured
				if batch:
					products.extend(batch)
					if limit and len(products) >= limit:
						products = products[:limit]
						break
				else:
					fh = api_conf.get("fallback_html")
					if fh:
						try:
							h_html = {**session.session.headers, **(fh.get("headers") or {})}
							for warm in fh.get("prewarm", []):
								try:
									session.get(warm, headers=h_html)
								except Exception:
									pass
							page_url = fh.get("page_url") or (ep.split("?", 1)[0] if isinstance(ep, str) else ep)
							links = scrape_category_for_links(session, page_url, fh["product_link_selector"], headers=h_html, use_browser=bool(fh.get("use_browser")))
							if dbg:
								try:
									print(f"Debug: fallback_html found {len(links)} links on {page_url}")
								except Exception:
									pass
							for url in links[: (limit or len(links))]:
								prod = scrape_product_page(session, url, fh["product_selectors"], headers=h_html)
								prod["merchant"] = merchant
								prod["source"] = site.get("source", "scraper")
								prod["external_id"] = prod.get("product_id") or url
								prod["product_url"] = url
								row = to_supabase_row(prod)
								emb = get_image_embedding(row.get("image_url"))
								if emb is not None:
									row["embedding"] = emb
								collected.append(row)
							# Skip to next endpoint after HTML fallback
							continue
						except Exception:
							pass
			except Exception:
				# Fallback to HTML scraping if configured
				fh = api_conf.get("fallback_html")
				if fh:
					try:
						h_html = {**session.session.headers, **(fh.get("headers") or {})}
						# prewarm
						for warm in fh.get("prewarm", []):
							try:
								session.get(warm, headers=h_html)
							except Exception:
								pass
						page_url = fh.get("page_url") or (ep.split("?", 1)[0] if isinstance(ep, str) else ep)
						links = scrape_category_for_links(session, page_url, fh["product_link_selector"], headers=h_html, use_browser=bool(fh.get("use_browser")))
						if dbg:
							try:
								print(f"Debug: fallback_html found {len(links)} links on {page_url}")
							except Exception:
								pass
						for url in links[: (limit or len(links))]:
							prod = scrape_product_page(session, url, fh["product_selectors"], headers=h_html)
							prod["merchant"] = merchant
							prod["source"] = site.get("source", "scraper")
							prod["external_id"] = prod.get("product_id") or url
							prod["product_url"] = url
							row = to_supabase_row(prod)
							emb = get_image_embedding(row.get("image_url"))
							if emb is not None:
								row["embedding"] = emb
							collected.append(row)
						# skip normal product flow for this endpoint
						continue
					except Exception:
						pass
		for p in products:
			p.setdefault("merchant", merchant)
			p.setdefault("source", site.get("source", "scraper"))
			# propagate country from site config if present
			if site.get("country") and not p.get("country"):
				p["country"] = site.get("country")
			# decide external_id based on mapping or fallbacks
			if not p.get("external_id"):
				p["external_id"] = p.get("product_id") or p.get("product_url")
			# pass along seo keyword and template if configured
			if api_conf.get("product_url_template"):
				p["product_url_template"] = api_conf["product_url_template"]
			row = to_supabase_row(p)
			# compute image embedding only
			emb = get_image_embedding(row.get("image_url"))
			if emb is not None:
				row["embedding"] = emb
			collected.append(row)
	elif site.get("html"):
		html_conf = site["html"]
		print(f"Processing {brand} HTML scraping...")
		# per-site headers for HTML scraping if provided
		h_html = {**session.session.headers, **(html_conf.get("headers") or {})}
		# Prewarm HTML cookies/session to reduce 403s
		for warm_url in html_conf.get("prewarm", []) or html_conf.get("prewarm_urls", []):
			try:
				session.get(warm_url, headers=h_html)
				print(f"Prewarmed {brand}: {warm_url}")
			except Exception as e:
				print(f"Prewarm failed for {brand}: {warm_url} - {e}")
		product_links = []
		# Optional: collect from sitemaps first if configured
		if html_conf.get("sitemaps"):
			try:
				site_urls = fetch_sitemap_urls(session, html_conf["sitemaps"], headers=h_html, url_contains=html_conf.get("sitemap_url_contains"))
				product_links.extend(site_urls)
				if dbg:
					try:
						print(f"Debug: sitemap yielded {len(site_urls)} urls")
						for u in site_urls[:5]:
							print(f"Debug sitemap url: {u}")
					except Exception:
						pass
			except Exception:
				pass
		# Check if we should extract products directly from category pages
		if html_conf.get("product_selector"):
			print(f"Extracting {brand} products directly from category pages...")
			# Mode: Extract products directly from category pages
			for cat in html_conf.get("category_urls", []):
				print(f"Processing {brand} category: {cat}")
				try:
					products = scrape_category_for_products(
						session,
						cat,
						html_conf["product_selector"],
						html_conf["product_selectors"],
						headers=h_html,
						use_browser=bool(html_conf.get("use_browser"))
					)
					print(f"{brand} category {cat} yielded {len(products)} products")
					for prod in products[: (limit or len(products))]:
						prod["merchant"] = merchant
						prod["source"] = site.get("source", "scraper")
						if site.get("country") and not prod.get("country"):
							prod["country"] = site.get("country")
						prod["external_id"] = prod.get("external_id") or prod.get("product_id") or f"unknown_{len(collected)}"
						# No product_url since we extracted from category page
						row = to_supabase_row(prod)
						image_url = row.get("image_url")
						if image_url:
							print(f"Getting embedding for {brand} product {prod.get('external_id', 'unknown')}: {image_url[:100]}...")
							emb = get_image_embedding(image_url)
							if emb is not None:
								row["embedding"] = emb
								print(f"✓ Embedding generated for {brand} product {prod.get('external_id', 'unknown')}")
							else:
								print(f"✗ Failed to generate embedding for {brand} product {prod.get('external_id', 'unknown')}")
						else:
							print(f"No image URL for {brand} product {prod.get('external_id', 'unknown')}")
						collected.append(row)
						if limit and len(collected) >= limit:
							break
					if limit and len(collected) >= limit:
						break
				except Exception as e:
					try:
						print(f"Error processing {brand} category {cat}: {e}")
					except UnicodeEncodeError:
						print(f"Error processing {brand} category {cat}: [Unicode encoding error in error message]")
					continue
		else:
			# Mode: Find links, then visit each product page (original behavior)
			for cat in html_conf.get("category_urls", []):
				product_links.extend(scrape_category_for_links(
					session,
					cat,
					html_conf["product_link_selector"],
					headers=h_html,
					use_browser=bool(html_conf.get("use_browser"))
				))
			product_links = list(dict.fromkeys(product_links))
			# Debug: show how many links were found on HTML pages
			if dbg or bool(site.get("debug")):
				try:
					print(f"Debug: HTML found {len(product_links)} product links")
					for l in product_links[:5]:
						print(f"Debug link: {l}")
				except Exception:
					pass
			for url in product_links[: (limit or len(product_links))]:
				prod = scrape_product_page(session, url, html_conf["product_selectors"], headers=h_html, use_browser=bool(html_conf.get("use_browser")))
				prod["merchant"] = merchant
				prod["source"] = site.get("source", "scraper")
				if site.get("country") and not prod.get("country"):
					prod["country"] = site.get("country")
				prod["external_id"] = prod.get("product_id") or url
				prod["product_url"] = url
				row = to_supabase_row(prod)
				emb = get_image_embedding(row.get("image_url"))
				if emb is not None:
					row["embedding"] = emb
				collected.append(row)
			else:
				raise ValueError(f"Site {brand} missing 'api' or 'html' config")
			if collected:
				if dry_run:
					print(f"[{datetime.now().strftime('%H:%M:%S')}] {brand}: processed {len(collected)} products (DRY RUN - skipping database operations)")
				else:
					print(f"[{datetime.now().strftime('%H:%M:%S')}] {brand}: processed {len(collected)} products, generating embeddings...")

					# Generate embeddings for products (like your working scraper)
					for product in collected:
						image_url = product.get('image_url')
						if image_url:
							embedding = get_image_embedding(image_url)
							if embedding:
								product['embedding'] = embedding
								print(f"[EMBEDDING] Generated for: {product.get('title', 'Unknown')[:50]}")
							else:
								print(f"[SKIP] No embedding for: {product.get('title', 'Unknown')[:50]}")

					print(f"[{datetime.now().strftime('%H:%M:%S')}] {brand}: processed {len(collected)} products, upserting to database...")
					success = db.upsert_products(collected)
					if not success:
						print(f"[{datetime.now().strftime('%H:%M:%S')}] {brand}: WARNING - database upsert failed")
					else:
						print(f"[{datetime.now().strftime('%H:%M:%S')}] {brand}: database upsert completed successfully")
			if sync:
				print(f"[{datetime.now().strftime('%H:%M:%S')}] {brand}: syncing database (removing unseen products)...")
				# Delete products from this (source, merchant, country) not seen in this run
				seen_ids = [r.get("id") for r in collected if r.get("id")]
				country = site.get("country") or ""
				db.delete_missing_for_source_merchant_country(site.get("source", "scraper"), merchant, country, seen_ids)
			print(f"[{datetime.now().strftime('%H:%M:%S')}] {brand}: database operations completed")
	return len(collected)


def main() -> None:
	parser = argparse.ArgumentParser(description="AI fashion scraper runner")
	parser.add_argument("--sites", default="all", help="Comma-separated brand names from sites.yaml or 'all'")
	parser.add_argument("--config", default="sites.yaml", help="Path to sites.yaml")
	parser.add_argument("--sync", action="store_true", help="Delete products not seen in this run for each source")
	parser.add_argument("--limit", type=int, default=0, help="Limit number of products per site (for testing)")
	parser.add_argument("--dry-run", action="store_true", help="Skip database operations (for testing scraping without DB writes)")
	parser.add_argument("--migrate", action="store_true", help="Run database migration for 1024-dim embeddings")
	args = parser.parse_args()

	load_env()
	supa_env = get_supabase_env()
	db = SupabaseDB()

	# Handle migration first
	if args.migrate:
		if args.dry_run:
			print("DRY RUN: Would run database migration to update embedding column to 1024 dimensions (skipped)")
			return
		print("Running database migration to update embedding column to 1024 dimensions...")
		with open("migrations/20251103_update_embedding_1024dim.sql", "r") as f:
			migration_sql = f.read()
		db.run_migration(migration_sql)
		print("Migration completed. You can now run the scraper normally.")
		return

	sites_all = load_sites_config(args.config)
	sites = get_site_configs(sites_all, args.sites)
	headers = get_default_headers()
	# If any site sets respect_robots: false, we will bypass robots checks for this run
	respect = True
	for s in sites:
		if s.get("respect_robots") is False:
			respect = False
			break
	session = PoliteSession(default_headers=headers, respect_robots=respect)

	total = 0
	print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing {len(sites)} sites: {[s.get('brand', 'Unknown') for s in sites]}")
	for i, site in enumerate(sites):
		brand = site.get("brand", "Unknown")
		print(f"\n[{datetime.now().strftime('%H:%M:%S')}] --- Processing {brand} --- ({i+1}/{len(sites)})")

		start_time = datetime.now()
		site_count = run_for_site(site, session, db, sync=args.sync, limit=args.limit, dry_run=args.dry_run)
		end_time = datetime.now()
		duration = (end_time - start_time).total_seconds()

		print(f"[{datetime.now().strftime('%H:%M:%S')}] {brand}: imported {site_count} products ({duration:.1f}s)")
		total += site_count
	print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Total: imported {total} products")


if __name__ == "__main__":
	main()


