import random
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

import requests
from requests import Response
from urllib.parse import urlparse
from urllib import robotparser


@dataclass
class RateLimit:
	min_delay_seconds: float = 1.0
	max_delay_seconds: float = 2.5


class RobotsCache:
	def __init__(self) -> None:
		self._cache: Dict[str, robotparser.RobotFileParser] = {}

	def is_allowed(self, user_agent: str, url: str) -> bool:
		parsed = urlparse(url)
		base = f"{parsed.scheme}://{parsed.netloc}"
		robots_url = f"{base}/robots.txt"
		rp = self._cache.get(base)
		if rp is None:
			rp = robotparser.RobotFileParser()
			rp.set_url(robots_url)
			try:
				rp.read()
			except Exception:
				# If robots cannot be read, be conservative and treat as disallowed
				self._cache[base] = rp
				return False
			self._cache[base] = rp
		return rp.can_fetch(user_agent, url)


class PoliteSession:
	"""Requests session with robots.txt checks and randomized delays."""

	def __init__(self, default_headers: Optional[Dict[str, str]] = None, rate_limit: Optional[RateLimit] = None, respect_robots: bool = True) -> None:
		self.session = requests.Session()
		self.session.headers.update(default_headers or {})
		# Pick up proxies from environment if provided
		proxies = {}
		http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
		https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
		if http_proxy:
			proxies["http"] = http_proxy
		if https_proxy:
			proxies["https"] = https_proxy
		if proxies:
			self.session.proxies.update(proxies)
		self.robots = RobotsCache()
		self.rate_limit = rate_limit or RateLimit()
		self.respect_robots = respect_robots

	def _sleep(self) -> None:
		delay = random.uniform(self.rate_limit.min_delay_seconds, self.rate_limit.max_delay_seconds)
		time.sleep(delay)

	def get(self, url: str, **kwargs) -> Response:
		ua = self.session.headers.get("User-Agent", "*")
		if self.respect_robots and not self.robots.is_allowed(ua, url):
			raise PermissionError(f"Blocked by robots.txt: {url}")
		self._sleep()
		insecure = bool(os.environ.get("INSECURE_SSL"))
		return self.session.get(url, timeout=kwargs.pop("timeout", 30), verify=(not insecure), **kwargs)

	def fetch_json(self, url: str, **kwargs):
		last_err: Optional[Exception] = None
		for attempt in range(3):
			resp = self.get(url, **kwargs)
			try:
				resp.raise_for_status()
				return resp.json()
			except Exception as e:
				last_err = e
				# brief backoff before retry
				time.sleep(min(1.0 * (attempt + 1), 3.0))
		# if all retries failed, raise the last error
		if last_err is not None:
			raise last_err
		# fallback guard
		resp.raise_for_status()
		return resp.json()


