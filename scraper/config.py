import os
from typing import Any, Dict, List

from dotenv import load_dotenv
import yaml


def load_env() -> None:
	"""Load environment variables from .env if present."""
	load_dotenv(override=False)


def load_sites_config(config_path: str = "sites.yaml") -> List[Dict[str, Any]]:
	with open(config_path, "r", encoding="utf-8") as f:
		data = yaml.safe_load(f) or []
	if not isinstance(data, list):
		raise ValueError("sites.yaml must be a list of site configurations")
	return data


def get_site_configs(all_sites: List[Dict[str, Any]], requested: str) -> List[Dict[str, Any]]:
	"""Filter sites by name or 'all'. Uses 'brand' key as the identifier."""
	if requested.lower() == "all":
		return all_sites
	requested_names = {s.strip().lower() for s in requested.split(",")}
	return [s for s in all_sites if s.get("brand", "").lower() in requested_names]


def get_default_headers() -> Dict[str, str]:
	ua = os.getenv("USER_AGENT", "FindsBot/0.1 (+contact@example.com)")
	return {
		"User-Agent": ua,
		"Accept": "*/*",
		"Accept-Language": "en-US,en;q=0.9",
	}


def get_supabase_env() -> Dict[str, str]:
	url = os.getenv("SUPABASE_URL", "").rstrip("/")
	key = os.getenv("SUPABASE_KEY", "")
	if not url or not key:
		raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in environment")
	return {"url": url, "key": key}


