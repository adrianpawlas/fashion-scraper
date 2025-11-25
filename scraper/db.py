import json
from typing import Dict, List

import requests


class SupabaseREST:
	"""Minimal Supabase PostgREST helper for upserting into 'products' table.

	This helper uses the primary key 'id' for idempotent upserts.
	"""

	def __init__(self, url: str, key: str) -> None:
		self.base_url = url.rstrip("/")
		self.key = key
		self.session = requests.Session()
		self.session.headers.update({
			"apikey": key,
			"Authorization": f"Bearer {key}",
			"Content-Type": "application/json",
		})

	def run_migration(self, migration_sql: str) -> None:
		"""Run a SQL migration script."""
		print("Running database migration...")
		print("Migration SQL:")
		print("=" * 50)
		print(migration_sql)
		print("=" * 50)

		# Use the SQL execution endpoint
		endpoint = f"{self.base_url}/rest/v1/rpc/exec_sql"
		payload = {"sql": migration_sql}

		resp = self.session.post(endpoint, json=payload, timeout=60)

		if resp.status_code not in (200, 201, 204):
			error_msg = f"Migration failed: {resp.status_code} {resp.text}"
			print(error_msg)
			# Don't raise an exception for now, let the user handle it manually if needed
			print("You may need to run this migration manually in your Supabase SQL editor.")
		else:
			print("Migration completed successfully!")
			print(resp.json() if resp.text else "No response body")

	def upsert_products(self, products: List[Dict]) -> None:
		"""Upsert a list of product dicts into the 'products' table using primary key 'id'."""
		if not products:
			return
		# Deduplicate by 'id' within this batch to avoid conflicts
		seen: Dict[str, Dict] = {}
		for p in products:
			key = p.get('id')
			if key:
				# last one wins; typically identical so doesn't matter
				seen[key] = p
		products = list(seen.values())
		
		# Normalize all products to have the same keys (Supabase requirement)
		# Collect all possible keys from the batch
		all_keys = set()
		for p in products:
			all_keys.update(p.keys())
		
		# Ensure every product has all keys (fill missing with None)
		normalized_products = []
		for p in products:
			normalized = {key: p.get(key) for key in all_keys}
			normalized_products.append(normalized)
		
		endpoint = f"{self.base_url}/rest/v1/products"
		headers = {
			"Prefer": "resolution=merge-duplicates,return=minimal",
		}
		# Try bulk inserts with trigger bypass using raw SQL
		chunk_size = 50  # Smaller chunks for better error recovery

		# First, try using raw SQL with session_replication_role to bypass triggers
		sql_success = self._try_sql_insert_with_trigger_bypass(normalized_products)
		if sql_success:
			print(f"[SUCCESS] Inserted all {len(normalized_products)} products using SQL bypass")
			return

		# Fallback: regular REST API inserts with graceful error handling
		print(f"[INFO] SQL bypass failed, falling back to REST API inserts...")
		failed_chunks = []

		for i in range(0, len(normalized_products), chunk_size):
			chunk = normalized_products[i:i + chunk_size]
			resp = self.session.post(endpoint, headers=headers, data=json.dumps(chunk), timeout=60)
			if resp.status_code not in (200, 201, 204):
				# If it's the Edge Function error, collect failed chunks for individual processing
				if "Edge function URL not configured" in resp.text:
					print(f"[WARNING] Bulk insert failed due to Edge Function trigger, will try individual inserts for chunk {i//chunk_size + 1}")
					failed_chunks.append(chunk)
				else:
					error_msg = f"Supabase upsert failed: {resp.status_code} {resp.text}"

					# Provide more helpful error messages for common Supabase issues
					if "Could not find the" in resp.text and "column" in resp.text:
						error_msg += "\n\n💡 SOLUTION: Your database schema doesn't match the expected columns. Check your products table schema and run any pending migrations."

					raise RuntimeError(error_msg)

		# Handle failed chunks with individual inserts
		if failed_chunks:
			print(f"[INFO] Processing {len(failed_chunks)} failed chunks individually...")
			for chunk_idx, chunk in enumerate(failed_chunks):
				successful_inserts = 0
				for product_idx, product in enumerate(chunk):
					try:
						# Insert one product at a time
						resp = self.session.post(endpoint, headers=headers, data=json.dumps([product]), timeout=30)
						if resp.status_code not in (200, 201, 204):
							if "Edge function URL not configured" in resp.text:
								print(f"[SKIP] Product {product.get('id', 'unknown')} skipped due to Edge Function trigger (mobile app will handle it)")
							else:
								print(f"[ERROR] Failed to insert product {product.get('id', 'unknown')}: {resp.status_code} {resp.text}")
						else:
							print(f"[SUCCESS] Inserted product {product.get('id', 'unknown')} individually")
							successful_inserts += 1
					except Exception as e:
						print(f"[ERROR] Exception inserting product {product.get('id', 'unknown')}: {e}")
						continue

				if successful_inserts == 0:
					print(f"[WARNING] All products in chunk {chunk_idx + 1} were skipped due to trigger issues")
				else:
					print(f"[INFO] Successfully inserted {successful_inserts}/{len(chunk)} products from chunk {chunk_idx + 1}")

	def _try_sql_insert_with_trigger_bypass(self, normalized_products: List[Dict]) -> bool:
		"""Try to insert products using raw SQL with trigger bypass. Returns True if successful."""
		# Skip this for now since it requires database changes the user doesn't want
		return False

	def delete_missing_for_source(self, source: str, current_ids: List[str]) -> None:
		"""Delete products for a given source whose id is not in the provided list.

		This implements a simple sync: keep-only currently seen items per source.
		"""
		if current_ids is None:
			current_ids = []
		# PostgREST needs an IN filter; for large lists, do it in chunks
		chunk_size = 300
		for i in range(0, len(current_ids) or 1, chunk_size):
			chunk = current_ids[i:i + chunk_size]
			if chunk:
				# Build a comma-separated list of quoted IDs without using f-strings in expressions
				ids_list = ",".join(['"' + (x or "").replace('"', '') + '"' for x in chunk])
				filter_qs = f"id=in.({ids_list})"
				url = f"{self.base_url}/rest/v1/products?source=eq.{source}&{filter_qs}"
				# Select IDs to keep; then DELETE where NOT IN this set using negation on a second call
				# Easiest: DELETE where source=source and not in current set (use neq on each chunk complement)
				# Since PostgREST doesn't support NOT IN directly, invert by deleting all except current in two steps:
				# 1) Mark current as protected with a header hint is not available; fallback to range delete in complement chunks is complex.
				# Simpler robust approach: upsert a temp table would be ideal; but keep to API-only:
				# We fallback to deleting in small negative chunks by querying candidates then deleting individually.
				resp = self.session.get(f"{self.base_url}/rest/v1/products?source=eq.{source}&select=id", timeout=60)
				resp.raise_for_status()
				all_ids = [r.get("id") for r in resp.json() if r.get("id") is not None]
				to_delete = [eid for eid in all_ids if eid not in current_ids]
				for j in range(0, len(to_delete), chunk_size):
					chunk_del = to_delete[j:j + chunk_size]
					for eid in chunk_del:
						del_url = f"{self.base_url}/rest/v1/products?source=eq.{source}&id=eq.{eid}"
						del_resp = self.session.delete(del_url, timeout=60)
						if del_resp.status_code not in (200, 204):
							raise RuntimeError(f"Supabase delete failed: {del_resp.status_code} {del_resp.text}")

	def delete_missing_for_source_and_merchant(self, source: str, merchant_name: str, current_ids: List[str]) -> None:
		"""Delete products for a given (source, merchant_name) not present in current_ids.

		Use this in multi-brand runs to avoid cross-brand deletions when sources are shared.
		"""
		if current_ids is None:
			current_ids = []
		# Fetch all existing ids for this (source, merchant_name)
		mn_enc = merchant_name.replace(" ", "%20")
		resp = self.session.get(f"{self.base_url}/rest/v1/products?source=eq.{source}&merchant_name=eq.{mn_enc}&select=id", timeout=60)
		resp.raise_for_status()
		all_ids = [r.get("id") for r in resp.json() if r.get("id") is not None]
		to_delete = [eid for eid in all_ids if eid not in current_ids]
		chunk_size = 300
		for j in range(0, len(to_delete), chunk_size):
			chunk_del = to_delete[j:j + chunk_size]
			for eid in chunk_del:
				del_url = f"{self.base_url}/rest/v1/products?source=eq.{source}&merchant_name=eq.{mn_enc}&id=eq.{eid}"
				del_resp = self.session.delete(del_url, timeout=60)
				if del_resp.status_code not in (200, 204):
					raise RuntimeError(f"Supabase delete failed: {del_resp.status_code} {del_resp.text}")

	def delete_missing_for_source_merchant_country(self, source: str, merchant_name: str, country: str, current_ids: List[str]) -> None:
		"""Delete products for a given source not present in current_ids.

		Since the new schema doesn't have merchant_name and country columns, we just filter by source.
		"""
		if current_ids is None:
			current_ids = []
		# Fetch existing IDs scoped by source only
		url = f"{self.base_url}/rest/v1/products?source=eq.{source}&select=id"
		resp = self.session.get(url, timeout=60)
		resp.raise_for_status()
		all_ids = [r.get("id") for r in resp.json() if r.get("id") is not None]
		to_delete = [eid for eid in all_ids if eid not in current_ids]
		chunk_size = 300
		for j in range(0, len(to_delete), chunk_size):
			chunk_del = to_delete[j:j + chunk_size]
			for eid in chunk_del:
				del_url = f"{self.base_url}/rest/v1/products?source=eq.{source}&id=eq.{eid}"
				del_resp = self.session.delete(del_url, timeout=60)
				if del_resp.status_code not in (200, 204):
					raise RuntimeError(f"Supabase delete failed: {del_resp.status_code} {del_resp.text}")


