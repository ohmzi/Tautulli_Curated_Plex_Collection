# helpers/radarr_utils.py
import requests
from helpers.logger import setup_logger

logger = setup_logger("radarr")

def _headers(cfg):
    return {"X-Api-Key": cfg.radarr.api_key}

def _base(cfg):
    return cfg.radarr.url.rstrip("/")

def get_or_create_tag(cfg, tag_name: str) -> int:
    r = requests.get(f"{_base(cfg)}/api/v3/tag", headers=_headers(cfg), timeout=30)
    r.raise_for_status()
    for tag in r.json():
        if tag.get("label", "").lower() == tag_name.lower():
            return tag["id"]

    logger.info(f"Creating Radarr tag: {tag_name}")
    r = requests.post(
        f"{_base(cfg)}/api/v3/tag",
        json={"label": tag_name},
        headers=_headers(cfg),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]

def _radarr_get_all_movies(cfg):
    r = requests.get(f"{_base(cfg)}/api/v3/movie", headers=_headers(cfg), timeout=60)
    r.raise_for_status()
    return r.json()

def radarr_find_movie_by_tmdb_id(cfg, tmdb_id: int):
    for movie in _radarr_get_all_movies(cfg):
        if movie.get("tmdbId") == tmdb_id:
            return movie
    return None

def radarr_set_monitored(cfg, movie: dict, monitored: bool = True):
    if movie.get("monitored") is monitored:
        logger.info(f"Already monitored in Radarr: {movie.get('title')}")
        return

    movie_id = movie["id"]
    updated = dict(movie)
    updated["monitored"] = monitored

    logger.info(f"Setting monitored={monitored} in Radarr: {movie.get('title')}")
    r = requests.put(
        f"{_base(cfg)}/api/v3/movie/{movie_id}",
        json=updated,
        headers=_headers(cfg),
        timeout=60,
    )
    r.raise_for_status()

def radarr_lookup_movie(cfg, title: str):
    r = requests.get(
        f"{_base(cfg)}/api/v3/movie/lookup",
        headers=_headers(cfg),
        params={"term": title},
        timeout=30,
    )
    r.raise_for_status()
    results = r.json()
    return results[0] if results else None

def radarr_add_and_search(cfg, title: str):
    tag_ids = [get_or_create_tag(cfg, cfg.radarr.tag_name)] if cfg.radarr.tag_name else []

    looked_up = None
    try:
        looked_up = radarr_lookup_movie(cfg, title)
    except Exception as e:
        logger.warning(f"Radarr lookup failed for '{title}': {e}")

    if not looked_up or not looked_up.get("tmdbId"):
        logger.warning(f"Could not resolve tmdbId for: {title}")
        return

    tmdb_id = int(looked_up["tmdbId"])
    existing = radarr_find_movie_by_tmdb_id(cfg, tmdb_id)
    if existing:
        logger.info(f"Already in Radarr by tmdbId: {existing.get('title')} -> forcing monitored")
        radarr_set_monitored(cfg, existing, True)
        return

    payload = {
        "title": looked_up.get("title", title),
        "tmdbId": tmdb_id,
        "year": looked_up.get("year"),
        "qualityProfileId": cfg.radarr.quality_profile_id,
        "rootFolderPath": cfg.radarr.root_folder,
        "monitored": True,
        "addOptions": {"searchForMovie": True},
        "tags": tag_ids,
    }

    logger.info(f"Adding movie to Radarr + searching: {payload['title']}")
    r = requests.post(f"{_base(cfg)}/api/v3/movie", json=payload, headers=_headers(cfg), timeout=60)
    r.raise_for_status()

def radarr_add_or_monitor_missing(cfg, titles: list[str]):
    for title in titles:
        try:
            # prefer tmdb-based matching via lookup, because title matching is messy
            radarr_add_and_search(cfg, title)
        except Exception as e:
            logger.error(f"Failed Radarr add/monitor for '{title}': {e}")

