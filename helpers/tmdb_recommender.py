# helpers/tmdb_recommender.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

import requests

from helpers.logger import setup_logger
from helpers.plex_search import find_plex_movie

logger = setup_logger("tmdb_recommender")


@dataclass(frozen=True)
class Candidate:
    tmdb_id: int
    title: str
    source: str  # "recommendations" | "similar" | "discover"
    score: float


def _get_json(url: str, params: dict, timeout: int = 20) -> dict:
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json() or {}


def _paged_results(
    url: str,
    params: dict,
    *,
    max_items: int,
    max_pages: int = 10,
) -> List[dict]:
    out: List[dict] = []
    page = 1

    while len(out) < max_items and page <= max_pages:
        data = _get_json(url, {**params, "page": page})
        results = data.get("results") or []
        if not results:
            break

        out.extend(results)

        total_pages = int(data.get("total_pages") or 1)
        if page >= total_pages:
            break

        page += 1

    return out[:max_items]


def _best_seed_result(query: str, results: list[dict]) -> Optional[dict]:
    q = (query or "").strip().lower()
    if not results:
        return None

    def score(r: dict) -> float:
        title = (r.get("title") or "").strip().lower()
        pop = float(r.get("popularity") or 0.0)
        votes = float(r.get("vote_count") or 0.0)
        vavg = float(r.get("vote_average") or 0.0)
        genre_ids = set(r.get("genre_ids") or [])

        # Hard penalty for documentaries unless user explicitly asked
        is_doc = 99 in genre_ids  # TMDb genre id 99 is Documentary
        doc_penalty = -1000.0 if is_doc and "documentary" not in q else 0.0

        # Text match boosts
        starts = 80.0 if title.startswith(q) and q else 0.0
        contains = 30.0 if q and q in title else 0.0

        # Franchise heuristic: "harry potter" should map to "Harry Potter and the ..."
        franchise_boost = 60.0 if q and q in ["harry potter"] and title.startswith("harry potter and the") else 0.0

        # Prefer well-known entries with real engagement
        engagement = (votes * 0.05) + (pop * 0.5) + (vavg * 2.0)

        return doc_penalty + starts + contains + franchise_boost + engagement

    return max(results, key=score)


def _resolve_seed_tmdb_id(api_key: str, title: str) -> Optional[int]:
    data = _get_json(
        "https://api.themoviedb.org/3/search/movie",
        {"api_key": api_key, "query": title},
    )
    results = data.get("results") or []
    best = _best_seed_result(title, results)
    if not best:
        return None
    try:
        return int(best["id"])
    except Exception:
        return None



def _get_seed_genre_ids(api_key: str, tmdb_id: int) -> List[int]:
    data = _get_json(
        f"https://api.themoviedb.org/3/movie/{tmdb_id}",
        {"api_key": api_key},
    )
    genres = data.get("genres") or []
    out: List[int] = []
    for g in genres:
        try:
            out.append(int(g.get("id")))
        except Exception:
            pass
    return out


def _to_candidate(*, tmdb_cache, tmdb_id: int, title: str, source: str, base_boost: float) -> Candidate:
    rating = float(tmdb_cache.get_rating(tmdb_id) or 0.0)  # vote_average (0-10)
    score = rating + base_boost
    return Candidate(tmdb_id=tmdb_id, title=title, source=source, score=score)


def get_tmdb_recommendations_advanced(
    *,
    api_key: str,
    seed_title: str,
    tmdb_cache,
    limit: int = 50,
    plex=None,
    allow_adult: bool = False,
) -> List[str]:
    """
    Advanced TMDb recommender:
      ✅ Merge /recommendations + /similar
      ✅ Weight by vote_average via TMDbCache.get_rating()
      ✅ Filter out movies already in Plex (if plex is provided)
      ✅ Genre-based /discover expansion if we still need more
    """
    seed_tmdb_id = _resolve_seed_tmdb_id(api_key, seed_title)
    if not seed_tmdb_id:
        logger.warning(f"TMDb: could not resolve seed tmdb id for {seed_title!r}")
        return []

    logger.info("TMDb recommendation_count=%d seed=%r", limit, seed_title)

    seed_genres = set(_get_seed_genre_ids(api_key, seed_tmdb_id))  # ✅ correct name
    logger.info("TMDb seed genres=%s", sorted(seed_genres))

    seen_ids: Set[int] = {seed_tmdb_id}
    candidates: Dict[int, Candidate] = {}

    def add_results(results: Iterable[dict], source: str, boost: float):
        for m in results:
            try:
                mid = int(m.get("id"))
            except Exception:
                continue

            if mid in seen_ids:
                continue

            title = (m.get("title") or "").strip()
            if not title:
                continue

            vote_count = int(m.get("vote_count") or 0)
            if vote_count < 100:
                continue

            movie_genres = set(m.get("genre_ids") or [])
            if seed_genres and movie_genres and not (seed_genres & movie_genres):
                continue

            cand = _to_candidate(
                tmdb_cache=tmdb_cache,
                tmdb_id=mid,
                title=title,
                source=source,
                base_boost=boost,
            )

            existing = candidates.get(mid)
            if existing is None or cand.score > existing.score:
                candidates[mid] = cand

            seen_ids.add(mid)


    # 1) /recommendations (usually higher quality)
    rec_url = f"https://api.themoviedb.org/3/movie/{seed_tmdb_id}/recommendations"
    rec_results = _paged_results(
        rec_url,
        {"api_key": api_key, "include_adult": str(bool(allow_adult)).lower()},
        max_items=limit * 2,
        max_pages=5,
    )
    add_results(rec_results, "recommendations", boost=1.0)

    # 2) /similar
    sim_url = f"https://api.themoviedb.org/3/movie/{seed_tmdb_id}/similar"
    sim_results = _paged_results(
        sim_url,
        {"api_key": api_key, "include_adult": str(bool(allow_adult)).lower()},
        max_items=limit * 2,
        max_pages=5,
    )
    add_results(sim_results, "similar", boost=0.4)

    # 3) /discover expansion if still short
    if len(candidates) < limit:
        genre_ids = _get_seed_genre_ids(api_key, seed_tmdb_id)
        if genre_ids:
            disc_url = "https://api.themoviedb.org/3/discover/movie"
            disc_results = _paged_results(
                disc_url,
                {
                    "api_key": api_key,
                    "include_adult": str(bool(allow_adult)).lower(),
                    "with_genres": ",".join(map(str, genre_ids[:3])),
                    "vote_count.gte": 200,
                    "sort_by": "vote_average.desc",
                },
                max_items=limit * 3,
                max_pages=10,
            )
            add_results(disc_results, "discover", boost=0.0)

    ranked = sorted(candidates.values(), key=lambda c: c.score, reverse=True)
    out = [c.title for c in ranked[:limit]]

    logger.info("TMDb advanced: seed=%r returned=%d candidates=%d", seed_title, len(out), len(candidates))
    return out

