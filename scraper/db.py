import json
from typing import Dict, List

import requests


class SupabaseREST:
	"""Minimal Supabase PostgREST helper for upserting into 'products' table.

	This helper assumes a unique constraint on (source, external_id) for idempotent upserts.
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

	def upsert_products(self, products: List[Dict]) -> None:
		"""Upsert a list of product dicts into the 'products' table using (source, external_id)."""
		if not products:
			return
		# Deduplicate by (source, external_id) within this batch to avoid ON CONFLICT hitting same row twice
		seen: Dict[str, Dict] = {}
		for p in products:
			key = f"{p.get('source')}::{p.get('external_id')}"
			# last one wins; typically identical so doesn't matter
			seen[key] = p
		products = list(seen.values())
		endpoint = f"{self.base_url}/rest/v1/products?on_conflict=source,external_id"
		headers = {
			"Prefer": "resolution=merge-duplicates,return=minimal",
		}
		# Chunk inserts to keep requests reasonable
		chunk_size = 500
		for i in range(0, len(products), chunk_size):
			chunk = products[i:i + chunk_size]
			resp = self.session.post(endpoint, headers=headers, data=json.dumps(chunk), timeout=60)
			if resp.status_code not in (200, 201, 204):
				raise RuntimeError(f"Supabase upsert failed: {resp.status_code} {resp.text}")

	def delete_missing_for_source(self, source: str, current_external_ids: List[str]) -> None:
		"""Delete products for a given source whose external_id is not in the provided list.

		This implements a simple sync: keep-only currently seen items per source.
		"""
		if current_external_ids is None:
			current_external_ids = []
		# PostgREST needs an IN filter; for large lists, do it in chunks
		chunk_size = 300
		for i in range(0, len(current_external_ids) or 1, chunk_size):
			chunk = current_external_ids[i:i + chunk_size]
			if chunk:
				# Build a comma-separated list of quoted IDs without using f-strings in expressions
				ids_list = ",".join(['"' + (x or "").replace('"', '') + '"' for x in chunk])
				filter_qs = f"external_id=in.({ids_list})"
				url = f"{self.base_url}/rest/v1/products?source=eq.{source}&{filter_qs}"
				# Select IDs to keep; then DELETE where NOT IN this set using negation on a second call
				# Easiest: DELETE where source=source and not in current set (use neq on each chunk complement)
				# Since PostgREST doesn't support NOT IN directly, invert by deleting all except current in two steps:
				# 1) Mark current as protected with a header hint is not available; fallback to range delete in complement chunks is complex.
				# Simpler robust approach: upsert a temp table would be ideal; but keep to API-only:
				# We fallback to deleting in small negative chunks by querying candidates then deleting individually.
				resp = self.session.get(f"{self.base_url}/rest/v1/products?source=eq.{source}&select=external_id", timeout=60)
				resp.raise_for_status()
				all_ids = [r.get("external_id") for r in resp.json() if r.get("external_id") is not None]
				to_delete = [eid for eid in all_ids if eid not in current_external_ids]
				for j in range(0, len(to_delete), chunk_size):
					chunk_del = to_delete[j:j + chunk_size]
					for eid in chunk_del:
						del_url = f"{self.base_url}/rest/v1/products?source=eq.{source}&external_id=eq.{eid}"
						del_resp = self.session.delete(del_url, timeout=60)
						if del_resp.status_code not in (200, 204):
							raise RuntimeError(f"Supabase delete failed: {del_resp.status_code} {del_resp.text}")

	def delete_missing_for_source_and_merchant(self, source: str, merchant_name: str, current_external_ids: List[str]) -> None:
		"""Delete products for a given (source, merchant_name) not present in current_external_ids.

		Use this in multi-brand runs to avoid cross-brand deletions when sources are shared.
		"""
		if current_external_ids is None:
			current_external_ids = []
		# Fetch all existing external_ids for this (source, merchant_name)
		mn_enc = merchant_name.replace(" ", "%20")
		resp = self.session.get(f"{self.base_url}/rest/v1/products?source=eq.{source}&merchant_name=eq.{mn_enc}&select=external_id", timeout=60)
		resp.raise_for_status()
		all_ids = [r.get("external_id") for r in resp.json() if r.get("external_id") is not None]
		to_delete = [eid for eid in all_ids if eid not in current_external_ids]
		chunk_size = 300
		for j in range(0, len(to_delete), chunk_size):
			chunk_del = to_delete[j:j + chunk_size]
			for eid in chunk_del:
				del_url = f"{self.base_url}/rest/v1/products?source=eq.{source}&merchant_name=eq.{mn_enc}&external_id=eq.{eid}"
				del_resp = self.session.delete(del_url, timeout=60)
				if del_resp.status_code not in (200, 204):
					raise RuntimeError(f"Supabase delete failed: {del_resp.status_code} {del_resp.text}")


