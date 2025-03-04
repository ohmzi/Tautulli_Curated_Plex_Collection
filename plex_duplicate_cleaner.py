import yaml
import logging
import sys
from plexapi.server import PlexServer
from pathlib import Path
from collections import defaultdict

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

def load_config():
    try:
        with open("config.yaml") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"Config error: {e}")
        sys.exit(1)

def get_plex_movies(config):
    try:
        plex = PlexServer(config['plex']['url'], config['plex']['token'])
        return plex.library.section(config['plex']['movie_library_name']).all()
    except Exception as e:
        logging.error(f"Plex connection failed: {e}")
        sys.exit(1)

def find_duplicates(movies):
    tmdb_dict = defaultdict(list)
    
    for movie in movies:
        tmdb_id = None
        for guid in movie.guids:
            if 'tmdb' in guid.id:
                tmdb_id = guid.id.split('//')[-1]
                break
        
        if tmdb_id and len(movie.media) > 0:
            for media in movie.media:
                for part in media.parts:
                    tmdb_dict[tmdb_id].append({
                        'movie': movie,
                        'file': part.file,
                        'size': part.size,
                        'quality': media.videoResolution,
                        'added_at': movie.addedAt
                    })
    
    return {k: v for k, v in tmdb_dict.items() if len(v) > 1}

def sort_files(files, config):
    preserve_terms = config['plex']['preserve_quality']
    pref = config['plex']['delete_preference']
    
    # First pass: filter out protected quality files
    filtered = [f for f in files if not any(
        term.lower() in f['quality'].lower() for term in preserve_terms
    )] or files
    
    # Sort according to preference
    reverse_sort = pref == 'largest_file' or pref == 'newest'
    if pref in ['largest_file', 'smallest_file']:
        return sorted(filtered, key=lambda x: x['size'], reverse=reverse_sort)
    elif pref in ['newest', 'oldest']:
        return sorted(filtered, key=lambda x: x['added_at'], reverse=reverse_sort)
    
    return filtered

def process_duplicates(duplicates, config, dry_run=True):
    deleted_files = 0
    
    for tmdb_id, files in duplicates.items():
        sorted_files = sort_files(files, config)
        keepers = sorted_files[:-1]
        to_delete = sorted_files[-1]
        
        logging.info(f"\nDuplicate found: TMDB {tmdb_id}")
        logging.info(f"Files:")
        for f in sorted_files:
            logging.info(f" - {Path(f['file']).name} [{f['quality']}] ({f['size']/1024/1024:.2f}MB)")
        
        if not dry_run:
            try:
                # Correct deletion method
                media = to_delete['movie'].media[0]
                media.delete()
                deleted_files += 1
                logging.info(f"Deleted: {Path(to_delete['file']).name}")
            except Exception as e:
                logging.error(f"Deletion failed: {e}")
                # Fallback to file system deletion if Plex API fails
                try:
                    Path(to_delete['file']).unlink()
                    logging.info(f"Deleted via filesystem: {to_delete['file']}")
                except Exception as fs_e:
                    logging.error(f"Filesystem deletion failed: {fs_e}")
        else:
            logging.info(f"[Dry Run] Would delete: {Path(to_delete['file']).name}")
            
    
    logging.info(f"\nTotal duplicates found: {len(duplicates)}")
    logging.info(f"Files {'marked for' if dry_run else ''} deletion: {deleted_files}")

if __name__ == "__main__":
    config = load_config()
    
    # Set dry_run=False to actually delete files
    dry_run = False

    logging.info("\n%s\n","========== PLEX DUPLICATE CLEANER DEBUG LOG ==========")

    logging.info("Fetching Plex library...")
    movies = get_plex_movies(config)
    
    logging.info("Scanning for duplicates...")
    duplicates = find_duplicates(movies)
    
    if duplicates:
        logging.info("Some duplicates found")
        process_duplicates(duplicates, config, dry_run)
    else:
        logging.info("No duplicates found")
    
    if dry_run:
        logging.info("\nDry run complete. No files were deleted.")
        logging.info("Set dry_run=False to perform actual deletions")
    
    logging.info("\n%s\n","========== END PLEX DUPLICATE CLEANER DEBUG LOG ==========")

