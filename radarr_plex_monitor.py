import requests
import yaml
from plexapi.server import PlexServer
import logging
import sys

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

def load_config():
    try:
        with open("config.yaml") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"Error loading config: {e}")
        sys.exit(1)

def get_radarr_movies(config):
    url = f"{config['radarr']['url']}/api/v3/movie"
    headers = {"X-Api-Key": config['radarr']['api_key']}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return [movie for movie in response.json() if movie['monitored']]
    except Exception as e:
        logging.error(f"Radarr API error: {e}")
        sys.exit(1)

def get_plex_tmdb_ids(config):
    try:
        plex = PlexServer(config['plex']['url'], config['plex']['token'])
        movies = plex.library.section(config['plex']['movie_library_name']).all()
        
        tmdb_ids = set()
        for movie in movies:
            for guid in movie.guids:
                if 'tmdb' in guid.id:
                    tmdb_id = guid.id.split('//')[-1]
                    tmdb_ids.add(int(tmdb_id))
        return tmdb_ids
    except Exception as e:
        logging.error(f"Plex error: {e}")
        sys.exit(1)

def unmonitor_movies(radarr_movies, plex_tmdb_ids, config, dry_run=True):
    unmonitored = 0
    for movie in radarr_movies:
        tmdb_id = movie.get('tmdbId')
        if not tmdb_id:
            continue
            
        if tmdb_id in plex_tmdb_ids:
            logging.info(f"Found in Plex: {movie['title']} (TMDB: {tmdb_id})")
            if not dry_run:
                try:
                    # Update movie to unmonitored
                    movie['monitored'] = False
                    url = f"{config['radarr']['url']}/api/v3/movie/{movie['id']}"
                    headers = {"X-Api-Key": config['radarr']['api_key']}
                    response = requests.put(url, json=movie, headers=headers)
                    response.raise_for_status()
                    unmonitored += 1
                except Exception as e:
                    logging.error(f"Failed to update {movie['title']}: {e}")
            else:
                unmonitored += 1
                
    logging.info(f"Dry run: {unmonitored} movies would be unmonitored" if dry_run 
                else f"Successfully unmonitored {unmonitored} movies")

if __name__ == "__main__":
    config = load_config()
    
    # Set dry_run=False to make actual changes
    dry_run = False

    logging.info("\n%s\n","========== RADARR DUPLICATE UNMONITOR DEBUG LOG ==========")
    logging.info("Fetching monitored movies from Radarr...")
    radarr_movies = get_radarr_movies(config)
    logging.info(f"Found {len(radarr_movies)} monitored movies in Radarr")
    
    logging.info("Fetching TMDB IDs from Plex...")
    plex_tmdb_ids = get_plex_tmdb_ids(config)
    logging.info(f"Found {len(plex_tmdb_ids)} movies in Plex")
    
    logging.info("Comparing libraries...")
    unmonitor_movies(radarr_movies, plex_tmdb_ids, config, dry_run=dry_run)
    
    if dry_run:
        logging.info("Dry run completed. No changes made. Set dry_run=False to apply changes")
    
    logging.info("\n%s\n","========== END RADARR DUPLICATE UNMONITOR DEBUG LOG ==========")


