from helpers.logger import setup_logger
from helpers.run_context import RunContext
from helpers.config_loader import load_config
from helpers.tmdb_cache import TMDbCache
from helpers.recommender import get_recommendations
from helpers.plex_search import find_plex_movie
from helpers.plex_collection_manager import refresh_collection_with_points
from plexapi.server import PlexServer
import helpers.radarr_utils as radarr_utils  # ✅ use ONE style

import json

logger = setup_logger("pipeline")


def load_points(path, logger):
    try:
        with open(str(path), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        logger.exception(f"Failed reading points file: {path}")
        return {}


def save_points(path, points_data, logger):
    try:
        with open(str(path), "w", encoding="utf-8") as f:
            json.dump(points_data, f, indent=2, ensure_ascii=False)
    except Exception:
        logger.exception(f"Failed writing points file: {path}")


def run_pipeline(movie_name, media_type, ctx=None):
    ctx = ctx or RunContext()

    # ✅ One stats dict for the pipeline (NOT the collection function return)
    pipeline_stats = {
        "recs": 0,
        "plex_found": 0,
        "plex_missing": 0,
        "radarr_added": 0,
        "radarr_monitored": 0,
        "radarr_already_monitored": 0,
        "radarr_failed": 0,
    }

    if media_type != "movie":
        logger.info(f"Skipping: media_type={media_type} title={movie_name!r}")
        return

    cfg = load_config()

    plex = PlexServer(cfg.plex.url, cfg.plex.token)

    tmdb_cache_path = (cfg.base_dir / cfg.files.tmdb_cache_file).resolve()
    tmdb_cache = TMDbCache(cfg.tmdb.api_key, str(tmdb_cache_path))

    points_path = (cfg.base_dir / cfg.files.points_file).resolve()
    points_data = load_points(points_path, logger)
    logger.info(f"Loaded points entries={len(points_data)} from {points_path}")

    # --- Recommend
    with ctx.step(logger, "recommend", movie=movie_name):
        recs = get_recommendations(movie_name, plex=plex, tmdb_cache=tmdb_cache)


    pipeline_stats["recs"] = len(recs)

    # --- Plex lookup
    plex_movies = []
    missing_titles = []

    with ctx.step(logger, "plex_lookup", count=len(recs)):
        total = len(recs)
        for i, title in enumerate(recs, 1):
            movie = find_plex_movie(plex, title)
            if movie:
                plex_movies.append(movie)
            else:
                missing_titles.append(title)

            # progress every 5, and also at the end
            if i % 5 == 0 or i == total:
                logger.info(f"progress {i}/{total} found={len(plex_movies)} missing={len(missing_titles)}")

    pipeline_stats["plex_found"] = len(plex_movies)
    pipeline_stats["plex_missing"] = len(missing_titles)

    # --- Radarr for missing
    if missing_titles:
        with ctx.step(logger, "radarr_missing", missing=len(missing_titles)):
            radarr_result = radarr_utils.radarr_add_or_monitor_missing(cfg, missing_titles) or {}

        pipeline_stats["radarr_added"] += radarr_result.get("added", 0)
        pipeline_stats["radarr_monitored"] += radarr_result.get("monitored", 0)
        pipeline_stats["radarr_already_monitored"] += radarr_result.get("already_monitored", 0)
        pipeline_stats["radarr_failed"] += radarr_result.get("failed", 0)

    # --- Collection refresh
    with ctx.step(logger, "collection_refresh", found=len(plex_movies)):
        collection_stats = refresh_collection_with_points(
            plex=plex,
            library_name=cfg.plex.movie_library_name,
            collection_name=cfg.plex.collection_name,
            plex_movies_this_run=plex_movies,
            tmdb_cache=tmdb_cache,
            points_data=points_data,
            max_points=50,
            logger=logger,  # ✅ pass pipeline logger
            randomize=getattr(cfg.plex, "randomize_collection", False),  # ✅ boolean
        )
        logger.info(f"collection_refresh stats={collection_stats}")

    save_points(points_path, points_data, logger)
    logger.info(f"Saved points entries={len(points_data)} to {points_path}")

    tmdb_cache.save()

    # --- Final summary (very readable)
    logger.info("============ PIPELINE SUMMARY ============")
    logger.info(f"seed_title={movie_name!r}")
    logger.info(f"recommendations={pipeline_stats['recs']}")
    logger.info(f"plex_found={pipeline_stats['plex_found']} plex_missing={pipeline_stats['plex_missing']}")
    logger.info(
        "radarr_added=%d radarr_monitored=%d radarr_already_monitored=%d radarr_failed=%d",
        pipeline_stats["radarr_added"],
        pipeline_stats["radarr_monitored"],
        pipeline_stats["radarr_already_monitored"],
        pipeline_stats["radarr_failed"],
    )
    logger.info("==========================================")


