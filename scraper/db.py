import os
import json
from typing import Dict, List, Any, Optional
import requests
import hashlib


class SupabaseREST:
    """
    Minimal Supabase PostgREST helper for upserting into 'products' table.

    Uses direct REST API calls to avoid Edge Function requirements.
    """

    def __init__(self, url: str = None, key: str = None):
        self.base_url = (url or os.getenv('SUPABASE_URL', '')).rstrip("/")
        self.key = key or os.getenv('SUPABASE_KEY', '')
        if not self.base_url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables are required")
        self.session = requests.Session()
        self.session.headers.update({
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        })

    def upsert_products(self, products: List[Dict[str, Any]]) -> bool:
        """
        Upsert products into the database.
        Args:
            products: List of product dictionaries
        Returns:
            True if successful, False otherwise
        """
        if not products:
            return True

        try:
            # Check if products are already formatted (have 'id' field from to_supabase_row)
            products_already_formatted = all(p.get('id') for p in products)

            if products_already_formatted:
                formatted_products = products
                # Still deduplicate by 'id'
                seen_ids = set()
                deduped_products = []
                for product in formatted_products:
                    product_id = product.get('id')
                    if product_id and product_id not in seen_ids:
                        seen_ids.add(product_id)
                        deduped_products.append(product)
                formatted_products = deduped_products
            else:
                # Convert products to the expected format
                formatted_products = []
                seen_ids = set()  # Track unique IDs

                for product in products:
                    formatted_product = self._format_product_for_db(product)
                    if formatted_product:
                        # Create unique key for deduplication based on source and product_url
                        dedup_key = f"{formatted_product.get('source')}:{formatted_product.get('product_url')}"
                        if dedup_key not in seen_ids:
                            seen_ids.add(dedup_key)
                            formatted_products.append(formatted_product)

            if not formatted_products:
                print("[WARNING] No valid products to upsert after formatting")
                return False

            print(f"[INFO] Upserting {len(formatted_products)} unique products (removed {len(products) - len(formatted_products)} duplicates)")

            # Deduplicate by 'id' within this batch to avoid conflicts
            seen: Dict[str, Dict] = {}
            for p in formatted_products:
                key = p.get('id')
                if key:
                    seen[key] = p
            products_to_upsert = list(seen.values())

            # Normalize all products to have the same keys (Supabase requirement)
            all_keys = set()
            for p in products_to_upsert:
                all_keys.update(p.keys())

            # Ensure every product has all keys (fill missing with None)
            normalized_products = []
            for p in products_to_upsert:
                normalized = {key: p.get(key) for key in all_keys}
                normalized_products.append(normalized)

            # Use direct POST with Prefer header for upsert (matching working code)
            endpoint = f"{self.base_url}/rest/v1/products"
            headers = {
                "Prefer": "resolution=merge-duplicates,return=minimal",
            }

            # Chunk inserts to keep requests reasonable (metadata can be large)
            chunk_size = 100
            success_count = 0
            failed_batches = []
            
            for i in range(0, len(normalized_products), chunk_size):
                chunk = normalized_products[i:i + chunk_size]
                batch_num = i//chunk_size + 1

                try:
                    resp = self.session.post(
                        endpoint,
                        headers=headers,
                        data=json.dumps(chunk),
                        timeout=60
                    )
                    if resp.status_code not in (200, 201, 204):
                        error_text = resp.text
                        # Check if it's a trigger/function error that we can retry individually
                        if "unrecognized configuration parameter" in error_text or "Edge function URL not configured" in error_text or "schema \"net\" does not exist" in error_text:
                            print(f"[WARNING] Batch {batch_num} failed due to database trigger issue, will retry individually")
                            failed_batches.append(chunk)
                        else:
                            print(f"[ERROR] Failed to upsert batch {batch_num}: {resp.status_code} {error_text}")
                        continue
                    success_count += len(chunk)

                except Exception as batch_error:
                    print(f"[ERROR] Failed to upsert batch {batch_num}: {batch_error}")
                    failed_batches.append(chunk)
                    continue

            # Retry failed batches individually (for trigger/function errors)
            if failed_batches:
                print(f"[INFO] Retrying {len(failed_batches)} failed batches individually...")
                individual_success = 0
                for batch in failed_batches:
                    for product in batch:
                        try:
                            resp = self.session.post(
                                endpoint,
                                headers=headers,
                                data=json.dumps([product]),
                                timeout=30
                            )
                            if resp.status_code in (200, 201, 204):
                                individual_success += 1
                            elif "unrecognized configuration parameter" in resp.text or "Edge function URL not configured" in resp.text:
                                # Skip products that trigger database function errors
                                # These will be handled by mobile app's trigger system
                                pass
                        except Exception:
                            pass
                if individual_success > 0:
                    print(f"[INFO] Successfully inserted {individual_success} products individually")
                    success_count += individual_success

            print(f"[SUCCESS] Successfully upserted {success_count} products in batches")
            return success_count > 0

        except Exception as e:
            print(f"[ERROR] Failed to upsert products: {e}")
            return False

    def _format_product_for_db(self, product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Format a product dictionary for database insertion.
        Args:
            product: Raw product data
        Returns:
            Formatted product data or None if invalid
        """
        try:
            # Required fields
            source = product.get('source', 'zara')
            product_url = product.get('product_url')
            image_url = product.get('image_url')
            title = product.get('title')

            if not source or not product_url or not image_url or not title:
                print(f"[WARNING] Missing required fields (source, product_url, image_url, title): {product}")
                return None

            # Generate deterministic ID from source and product_url
            # This ensures the same product always gets the same ID
            id_string = f"{source}:{product_url}"
            product_id = hashlib.sha256(id_string.encode('utf-8')).hexdigest()

            # Build the formatted product
            # Using source + product_url as the natural unique key
            formatted = {
                'id': product_id,  # Required: text primary key
                'source': source,
                'product_url': product_url,
                'image_url': image_url,
                'title': title,
                'brand': product.get('brand'),
                'gender': product.get('gender'),
                'price': product.get('price'),  # Text format: "20USD,450CZK,75PLN"
                'sale': product.get('sale'),  # Text format: "15USD,350CZK,60PLN" or null
                'size': product.get('size'),
                'second_hand': product.get('second_hand', False)
            }

            # Optional fields
            if 'affiliate_url' in product and product['affiliate_url']:
                formatted['affiliate_url'] = product['affiliate_url']

            if 'description' in product and product['description']:
                formatted['description'] = product['description']

            if 'category' in product and product['category']:
                formatted['category'] = product['category']

            # Optional embedding
            if 'embedding' in product and product['embedding'] is not None:
                formatted['embedding'] = product['embedding']

            # Optional metadata
            metadata = {}
            if 'merchant_name' in product:
                metadata['merchant_name'] = product['merchant_name']
            if 'country' in product:
                metadata['country'] = product['country']
            if 'original_currency' in product:
                metadata['original_currency'] = product['original_currency']
            if metadata:
                import json
                formatted['metadata'] = json.dumps(metadata)

            return formatted

        except Exception as e:
            print(f"[ERROR] Failed to format product: {e}")
            return None

    def delete_missing_for_source(self, source: str, current_ids: List[str]) -> None:
        """Delete products for a given source whose id is not in the provided list."""
        if current_ids is None:
            current_ids = []
        # PostgREST needs an IN filter; for large lists, do it in chunks
        chunk_size = 300
        for i in range(0, len(current_ids) or 1, chunk_size):
            chunk = current_ids[i:i + chunk_size]
            if chunk:
                ids_list = ",".join(['"' + (x or "").replace('"', '') + '"' for x in chunk])
                filter_qs = f"id=in.({ids_list})"
                url = f"{self.base_url}/rest/v1/products?source=eq.{source}&{filter_qs}"
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

    def get_product_count(self, source: Optional[str] = None) -> int:
        """
        Get count of products in database.
        Args:
            source: Optional source filter
        Returns:
            Number of products
        """
        try:
            url = f"{self.base_url}/rest/v1/products"
            params = {"select": "id"}
            if source:
                params["source"] = f"eq.{source}"

            resp = self.session.get(url, params=params, timeout=60)
            resp.raise_for_status()
            return len(resp.json())
        except Exception as e:
            print(f"[ERROR] Failed to get product count: {e}")
            return 0

    def get_recent_products(self, source: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recently created products for a source.
        Args:
            source: Source name
            limit: Maximum number of products to return
        Returns:
            List of recent products
        """
        try:
            url = f"{self.base_url}/rest/v1/products"
            params = {
                "source": f"eq.{source}",
                "order": "created_at.desc",
                "limit": str(limit)
            }
            resp = self.session.get(url, params=params, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[ERROR] Failed to get recent products: {e}")
            return []


class SupabaseDB:
    def __init__(self):
        self.rest_client = SupabaseREST()

    def upsert_products(self, products: List[Dict[str, Any]]) -> bool:
        """Convenience function to upsert products."""
        return self.rest_client.upsert_products(products)

    def delete_missing_for_source(self, source: str, current_ids: List[str]) -> None:
        """Convenience function to delete missing products."""
        self.rest_client.delete_missing_for_source(source, current_ids)

    def get_product_count(self, source: Optional[str] = None) -> int:
        """Convenience function to get product count."""
        return self.rest_client.get_product_count(source)

    def get_recent_products(self, source: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Convenience function to get recent products."""
        return self.rest_client.get_recent_products(source, limit)


# Global instance
_db_instance = None

def get_db() -> SupabaseDB:
    """Get global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = SupabaseDB()
    return _db_instance

def upsert_products(products: List[Dict[str, Any]]) -> bool:
    """Convenience function to upsert products."""
    return get_db().upsert_products(products)
