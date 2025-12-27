import sys
from tautulli_curated.helpers.logger import setup_logger
from tautulli_curated.helpers.pipeline_recent_watch import run_pipeline
from tautulli_curated.helpers.config_loader import load_config

logger = setup_logger("tautulli_immaculate_taste_collection")

def main():
    # Expect: python3 tautulli_immaculate_taste_collection.py "Title" movie
    if len(sys.argv) < 3:
        print('Usage: python3 tautulli_immaculate_taste_collection.py "Movie Title" movie')
        return 1

    movie_name = sys.argv[1]
    media_type = sys.argv[2].lower().strip()

    logger.info("=" * 60)
    logger.info("IMMACULATE TASTE COLLECTION SCRIPT START")
    logger.info("=" * 60)
    logger.info(f"Movie: {movie_name}")
    logger.info(f"Media type: {media_type}")
    logger.info("")

    try:
        # Load configuration to check if collection refresher should run
        logger.info("Loading configuration...")
        config = load_config()
        logger.info(f"  ✓ Configuration loaded")
        logger.info("")
        
        # Check collection refresher setting
        run_refresher = config.scripts_run.run_collection_refresher
        logger.info("Collection Refresher Configuration:")
        if run_refresher:
            logger.info(f"  ✓ Collection Refresher: ENABLED")
            logger.info(f"    → Immaculate Taste Collection Refresher will run at the end of this script")
            logger.info(f"    → This will randomize and update the Plex collection")
            logger.info(f"    → Note: This may take a while for large collections")
        else:
            logger.info(f"  ⚠ Collection Refresher: DISABLED")
            logger.info(f"    → Immaculate Taste Collection Refresher will NOT run as part of this script")
            logger.info(f"    → To run it independently, use: ./src/scripts/run_refresher.sh")
            logger.info(f"    → Or set 'run_collection_refresher: true' in config/config.yaml")
        logger.info("")
        
        # Run the main pipeline
        logger.info("Running main pipeline...")
        logger.info("-" * 60)
        run_pipeline(movie_name, media_type)
        logger.info("-" * 60)
        logger.info("  ✓ Main pipeline completed successfully")
        logger.info("")
        
        # Optionally run collection refresher
        if run_refresher:
            logger.info("=" * 60)
            logger.info("RUNNING COLLECTION REFRESHER")
            logger.info("=" * 60)
            logger.info("Starting Immaculate Taste Collection Refresher...")
            logger.info("  This will:")
            logger.info("    1. Read recommendation_points.json")
            logger.info("    2. Randomize the order of movies")
            logger.info("    3. Remove all items from the Plex collection")
            logger.info("    4. Add all items back in randomized order")
            logger.info("  Note: This process may take a while for large collections")
            logger.info("")
            
            try:
                # Import and run the refresher
                # We need to temporarily modify sys.argv to avoid argument conflicts
                from tautulli_curated import refresher as refresher_module
                
                # Save original argv
                original_argv = sys.argv
                try:
                    # Set up minimal argv for the refresher's argument parser
                    # This ensures parse_args() doesn't try to parse the main script's arguments
                    sys.argv = ['Immaculate_taste_collection_refresher.py']
                    
                    # Run the refresher's main function
                    # It will call parse_args() internally, which will get empty args (no --dry-run or --verbose)
                    exit_code = refresher_module.main()
                finally:
                    # Restore original argv
                    sys.argv = original_argv
                
                if exit_code == 0:
                    logger.info("")
                    logger.info("  ✓ Collection Refresher completed successfully")
                else:
                    logger.warning("")
                    logger.warning(f"  ⚠ Collection Refresher completed with exit code: {exit_code}")
                    logger.warning("  The main pipeline completed successfully, but collection refresh had issues")
            except KeyboardInterrupt:
                logger.warning("")
                logger.warning("  ⚠ Collection Refresher interrupted by user")
                logger.warning("  The main pipeline completed successfully")
            except Exception as e:
                logger.error("")
                logger.error(f"  ✗ Collection Refresher failed: {type(e).__name__}: {e}")
                logger.error("  The main pipeline completed successfully, but collection refresh failed")
                logger.error("  You can run the refresher independently later if needed")
        else:
            logger.info("Collection Refresher skipped (disabled in config)")
            logger.info("  To enable: Set 'run_collection_refresher: true' in config/config.yaml")
            logger.info("  Or run independently: ./src/scripts/run_refresher.sh")
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("IMMACULATE TASTE COLLECTION SCRIPT END OK")
        logger.info("=" * 60)
        return 0
    except KeyboardInterrupt:
        logger.warning("")
        logger.warning("Script interrupted by user")
        logger.info("=" * 60)
        logger.info("IMMACULATE TASTE COLLECTION SCRIPT END (interrupted)")
        logger.info("=" * 60)
        return 130
    except Exception:
        logger.exception("")
        logger.error("=" * 60)
        logger.error("IMMACULATE TASTE COLLECTION SCRIPT END FAIL")
        logger.error("=" * 60)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())

