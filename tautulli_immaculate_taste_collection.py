import sys
from helpers.logger import setup_logger
from helpers.pipeline_recent_watch import run_pipeline  # adjust if your module name differs

logger = setup_logger("tautulli_immaculate_taste_collection")

def main():
    # Expect: python3 tautulli_immaculate_taste_collection.py "Title" movie
    if len(sys.argv) < 3:
        print('Usage: python3 tautulli_immaculate_taste_collection.py "Movie Title" movie')
        return 1

    movie_name = sys.argv[1]
    media_type = sys.argv[2].lower().strip()

    logger.info(f"SCRIPT START title={movie_name!r} media_type={media_type!r}")

    try:
        run_pipeline(movie_name, media_type)
        logger.info("SCRIPT END OK")
        return 0
    except Exception:
        logger.exception("SCRIPT END FAIL")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())

