import json
import time
from pathlib import Path
from typing import Dict, Optional
import requests

CACHE_DIR = Path("modrinth_cache")
CACHE_DURATION = 3600  # 1 hour in seconds


class ModrinthCache:
    """Simple filesystem cache for Modrinth API requests."""

    def __init__(self) -> None:
        self.cache_dir = CACHE_DIR
        self.cache_dir.mkdir(exist_ok=True)
        self.rate_limit = 300
        self.rate_remaining = 300
        self.rate_reset = 0
        self.last_request_time = 0
        self.min_request_interval = 0.1

    def _get_mod_cache_file(self, mod_slug: str) -> Path:
        return self.cache_dir / f"{mod_slug}.json"

    def get_all_data(self, mod_slug: str) -> Optional[dict]:
        cache_file = self._get_mod_cache_file(mod_slug)
        if cache_file.exists():
            try:
                cache_data = json.loads(cache_file.read_text())
                key = f"{mod_slug}_all"
                if key in cache_data:
                    entry = cache_data[key]
                    if time.time() - entry["cached_at"] < CACHE_DURATION:
                        return entry["data"]
            except (json.JSONDecodeError, KeyError):
                pass
        return None

    def cache_all_data(self, mod_slug: str, data: dict) -> None:
        cache_file = self._get_mod_cache_file(mod_slug)
        if cache_file.exists():
            try:
                cache_data = json.loads(cache_file.read_text())
            except json.JSONDecodeError:
                cache_data = {}
        else:
            cache_data = {}

        cache_data[f"{mod_slug}_all"] = {
            "cached_at": time.time(),
            "data": data,
        }
        cache_file.write_text(json.dumps(cache_data, indent=2))

    def get_cached_data(self, mod_slug: str, version: str, loader: str) -> Optional[dict]:
        cache_file = self._get_mod_cache_file(mod_slug)
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                version_key = f"{version}_{loader}"
                if version_key in cache_data:
                    data = cache_data[version_key]
                    if time.time() - data["cached_at"] < CACHE_DURATION:
                        return data["data"]
            except (json.JSONDecodeError, KeyError, OSError):
                pass
        return None

    def cache_data(self, mod_slug: str, version: str, loader: str, data: dict) -> None:
        cache_file = self._get_mod_cache_file(mod_slug)
        version_key = f"{version}_{loader}"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                cache_data = {}
        else:
            cache_data = {}

        cache_data[version_key] = {
            "cached_at": time.time(),
            "data": data,
        }
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, separators=(",", ":"))

    def update_rate_limits(self, headers: Dict[str, str]) -> None:
        self.rate_limit = int(headers.get("X-Ratelimit-Limit", 300))
        self.rate_remaining = int(headers.get("X-Ratelimit-Remaining", 300))
        self.rate_reset = int(headers.get("X-Ratelimit-Reset", 0))

    def should_wait(self) -> float:
        if self.rate_remaining < 10:
            return max(0, self.rate_reset)
        time_since_last = time.time() - self.last_request_time
        if time_since_last < self.min_request_interval:
            return self.min_request_interval - time_since_last
        return 0

    def make_request(self, url: str) -> requests.Response:
        wait_time = self.should_wait()
        if wait_time > 0:
            time.sleep(wait_time)
        response = requests.get(url)
        self.last_request_time = time.time()
        self.update_rate_limits(response.headers)
        return response


# Shared cache instance for all API requests
cache = ModrinthCache()
