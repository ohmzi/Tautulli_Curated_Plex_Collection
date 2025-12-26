# helpers/tmdb_cache.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import requests


class TMDbCache:
    """
    Supports BOTH cache formats:
      New (expected): {"ids": {...}, "ratings": {...}}
      Existing:       {"id_cache": {...}, "rating_cache": {...}}
    Automatically normalizes to internal keys: ids/ratings.
    """

    def __init__(self, api_key: str, cache_path: str | Path, logger=None):
        self.api_key = api_key
        self.cache_path = Path(cache_path)
        self.logger = logger

        self.data: Dict[str, Dict[str, Any]] = {"ids": {}, "ratings": {}}
        self._load()

    def _log(self, msg: str):
        if self.logger:
            self.logger.info(msg)

    def _load(self):
        if not self.cache_path.exists():
            self._log(f"TMDb cache not found, will create: {self.cache_path}")
            self._save()
            return

        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))

            # Existing format -> normalize
            if "id_cache" in raw or "rating_cache" in raw:
                self.data["ids"] = raw.get("id_cache", {}) or {}
                self.data["ratings"] = raw.get("rating_cache", {}) or {}
                self._log("Loaded TMDb cache (legacy format: id_cache/rating_cache)")
                return

            # New format -> use directly
            self.data["ids"] = raw.get("id_cache", raw.get("ids", {})) or {}
            self.data["ratings"] = raw.get("rating_cache", raw.get("ratings", {})) or {}
            self._log("Loaded TMDb cache (format: ids/ratings)")
        except Exception as e:
            if self.logger:
                self.logger.exception(f"Failed to load TMDb cache, resetting: {e}")
            self.data = {"ids": {}, "ratings": {}}
            self._save()

    def _save(self):
        # Save back in your existing format to preserve continuity
        payload = {
            "id_cache": self.data["ids"],
            "rating_cache": self.data["ratings"],
        }
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_tmdb_id(self, title: str) -> Optional[int]:
        if not title:
            return None

        if title in self.data["ids"]:
            return self.data["ids"][title]

        tmdb_id = self._fetch_tmdb_id(title)
        self.data["ids"][title] = tmdb_id
        self._save()
        return tmdb_id

    def get_rating(self, tmdb_id: int | str) -> float:
        if not tmdb_id:
            return 0.0

        key = str(tmdb_id)
        if key in self.data["ratings"]:
            return float(self.data["ratings"][key] or 0.0)

        rating = self._fetch_tmdb_rating(tmdb_id)
        self.data["ratings"][key] = float(rating or 0.0)
        self._save()
        return float(rating or 0.0)

    def _fetch_tmdb_id(self, title: str) -> Optional[int]:
        url = "https://api.themoviedb.org/3/search/movie"
        params = {"api_key": self.api_key, "query": title}
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            if data.get("results"):
                return int(data["results"][0]["id"])
        except Exception as e:
            if self.logger:
                self.logger.exception(f"TMDb ID lookup failed for '{title}': {e}")
        return None

    def _fetch_tmdb_rating(self, tmdb_id: int | str) -> float:
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
        params = {"api_key": self.api_key}
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            return float(data.get("vote_average", 0.0) or 0.0)
        except Exception as e:
            if self.logger:
                self.logger.exception(f"TMDb rating lookup failed for '{tmdb_id}': {e}")
        return 0.0
        
    def save(self):
        self._save()

