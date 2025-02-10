#!/usr/bin/python3
import sys
import re
import json
import requests
import time
import os
import yaml  # <-- You need PyYAML installed: pip install pyyaml

from plexapi.server import PlexServer
from openai import OpenAI
from arrapi import RadarrAPI, exceptions as arr_exceptions

# -------------- Function to Load YAML Configuration --------------
def load_config(config_path="config.yaml"):
    """
    Loads the configuration from a local YAML file.
    Returns a dictionary with all the relevant settings.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config

# ----------------- Global Variables (populated later) -------------
PLEX_URL = None
PLEX_TOKEN = None
OPENAI_API_KEY = None
RADARR_API_KEY = None
RADARR_URL = None
RADARR_ROOT_FOLDER = None
RADARR_TAG_NAME = None
TMDB_API_KEY = None
POINTS_FILE = None
TMDB_CACHE_FILE = None

# We'll define these references so we don't break code below when we set them after loading config
plex = None
client = None
radarr = None

# ----------------- TMDb Caches (In-Memory) -----------------
tmdb_id_cache = {}       # Key: movie_title (str), Value: tmdb_id (int or None)
tmdb_rating_cache = {}   # Key: tmdb_id (int), Value: rating (float)

# ----------------- Cache Persistence -----------------

def load_tmdb_cache():
    global tmdb_id_cache, tmdb_rating_cache
    if not os.path.exists(TMDB_CACHE_FILE):
        return
    try:
        with open(TMDB_CACHE_FILE, 'r') as f:
            data = json.load(f)
        tmdb_id_cache = data.get('id_cache', {})
        tmdb_rating_cache = data.get('rating_cache', {})
    except Exception as e:
        print(f"Warning: Could not load TMDb cache from {TMDB_CACHE_FILE}: {e}")

def save_tmdb_cache():
    data = {
        'id_cache': tmdb_id_cache,
        'rating_cache': tmdb_rating_cache,
    }
    try:
        with open(TMDB_CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save TMDb cache to {TMDB_CACHE_FILE}: {e}")

# ----------------- Points JSON -----------------

def load_points():
    if not os.path.exists(POINTS_FILE):
        return {}
    try:
        with open(POINTS_FILE, "r") as f:
            data = json.load(f)
        # If older style was just int, convert
        for key, value in list(data.items()):
            if isinstance(value, int):
                data[key] = {"title": "unknown", "points": value}
        return data
    except Exception as e:
        print(f"Error loading points file: {e}")
        return {}

def save_points(points_dict):
    try:
        with open(POINTS_FILE, "w") as f:
            json.dump(points_dict, f, indent=2)
    except Exception as e:
        print(f"Error saving points file: {e}")

# ----------------- TMDb Fetch Functions (no caching) -----------------

def fetch_tmdb_id(movie_title):
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_title}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data["results"]:
            return data["results"][0]["id"]
        else:
            print(f"TMDb ID not found for: {movie_title}")
            return None
    except Exception as e:
        print(f"Error fetching TMDb ID for {movie_title}: {e}")
        return None

def fetch_tmdb_rating(tmdb_id):
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get("vote_average", 0.0)
    except Exception as e:
        print(f"Error fetching TMDb rating for id {tmdb_id}: {e}")
        return 0.0

# ----------------- TMDb Cached Wrappers -----------------

def get_tmdb_id_cached(movie_title):
    if movie_title in tmdb_id_cache:
        return tmdb_id_cache[movie_title]
    tmdb_id = fetch_tmdb_id(movie_title)
    tmdb_id_cache[movie_title] = tmdb_id
    return tmdb_id

def get_tmdb_rating_cached(tmdb_id):
    if tmdb_id in tmdb_rating_cache:
        return tmdb_rating_cache[tmdb_id]
    rating = fetch_tmdb_rating(tmdb_id)
    tmdb_rating_cache[tmdb_id] = rating
    return rating

# ----------------- GPT Recommendation -----------------

def get_recommendations(movie_name: str) -> list:
    prompt = f"""Return a list of 50 movies for fans of "{movie_name}" in the following categories:
Direct sequels/prequels,
Movies by the same director or featuring the lead actor,
Movies with similar genres or themes,
One hidden gem,
Five movies from different franchises,
Two indie movies.
Ensure all movies are released.
Format:
Provide the list as a single comma-separated string in the format "Title (Year), Title (Year), ..." , no bulleting or indexing each name serperately.
Example Output: "The Dark Knight (2008), Inception (2010), ..." """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a movie recommendation engine."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=300
        )
        raw = response.choices[0].message.content.strip()
        recs = [title.strip() for title in re.split(r',|\n', raw) if title.strip()]
        return recs
    except Exception as e:
        print(f"API Error: {e}")
        return []

# ----------------- Plex & Radarr Helpers -----------------

def find_plex_movie(title: str):
    try:
        match = re.match(r"(.*?)(\s*\(\d{4}\)|\s*\[\d{4}\])$", title)
        if match:
            base_title = match.group(1).strip()
            year = match.group(2).strip("()[] ")
        else:
            base_title = title
            year = None
        results = plex.library.section('Movies').search(title=base_title, year=year, libtype='movie')
        return results[0] if results else None
    except Exception as e:
        print(f"Search error for {title}: {e}")
        return None

def search_radarr_movie(tmdb_id: int):
    try:
        return radarr.get_movie(tmdb_id=tmdb_id)
    except arr_exceptions.NotFound:
        return None
    except Exception as e:
        print(f"Error searching for movie with TMDb ID {tmdb_id}: {e}")
        return None

def get_or_create_radarr_tag(tag_name: str) -> int:
    try:
        tags = radarr.all_tags(detail=True)
        for tag in tags:
            if tag.label.lower() == tag_name.lower():
                return tag.id
        tag_obj = radarr.create_tag(tag_name)
        if tag_obj:
            return tag_obj.id
        else:
            print(f"Failed to create tag '{tag_name}'.")
            return None
    except Exception as e:
        print(f"Error in tag lookup/creation for '{tag_name}': {e}")
        return None

def add_to_radarr(title: str):
    print(f"Processing movie: {title}")
    match = re.match(r"(.*?)(\s*\(\d{4}\)|\s*\[\d{4}\])$", title)
    base_title = match.group(1).strip() if match else title
    year = match.group(2).strip("()[] ") if match else None

    tmdb_id = get_tmdb_id_cached(base_title)
    if not tmdb_id:
        print(f"⚠️ Could not find TMDb ID for '{title}', skipping...")
        return

    movie = search_radarr_movie(tmdb_id)
    if movie:
        if not movie.monitored:
            try:
                movie.edit(monitored=True)
                print(f"✅ '{title}' set to monitored in Radarr!")
            except Exception as e:
                print(f"⚠️ Failed to update '{title}': {e}")
        else:
            print(f"✅ '{title}' is already monitored in Radarr.")
        return

    print(f"Adding '{title}' to Radarr...")
    tag_id = get_or_create_radarr_tag(RADARR_TAG_NAME)
    if tag_id is None:
        print(f"⚠️ Skipping '{title}' due to tag creation failure.")
        return

    try:
        radarr.add_movie(
            root_folder=RADARR_ROOT_FOLDER,
            quality_profile=1,
            tmdb_id=tmdb_id,
            title=base_title,
            year=int(year) if year else None,
            monitor=True,
            search=True,
            minimum_availability="announced",
            tags=[tag_id]
        )
        print(f"✅ Added '{title}' to Radarr.")
    except Exception as e:
        print(f"⚠️ Failed to add '{title}': {e}")

# ----------------- Refresh Collection with Points -----------------

def refresh_collection_with_points(recommended_titles):
    collection_name = "Inspired by your Immaculate Taste"
    movies_section = plex.library.section('Movies')
    
    print("Refreshing Plex Movies library...")
    try:
        movies_section.refresh()
    except Exception as e:
        print(f"Warning: Could not refresh library: {e}")
    time.sleep(10)
    
    # Find or create collection
    collection = None
    for col in movies_section.collections():
        if col.title.strip().lower() == collection_name.lower():
            collection = col
            break

    if collection:
        old_movies = collection.items()
        print(f"Existing collection '{collection_name}' has {len(old_movies)} items.")
    else:
        old_movies = []
        print("No existing collection found; will create one if needed.")

    points_data = load_points()
    
    # 1) Start with the old collection
    candidate_dict = {}
    for plexmovie in old_movies:
        tmdb_id = get_tmdb_id_cached(plexmovie.title)
        if tmdb_id:
            candidate_dict[plexmovie.title] = plexmovie

    # 2) Merge recommended titles (that are in Plex)
    for title in recommended_titles:
        plexmovie = find_plex_movie(title)
        if plexmovie and plexmovie.title not in candidate_dict:
            candidate_dict[plexmovie.title] = plexmovie

    candidates = list(candidate_dict.values())
    print(f"Total candidate movies in Plex after merging recommended titles: {len(candidates)}")

    # 3) Update points
    candidate_tuples = []
    removed_list = []
    kept_list = []

    for movie in candidates:
        tmdb_id = get_tmdb_id_cached(movie.title)
        if not tmdb_id:
            continue
        key = str(tmdb_id)
        if key not in points_data:
            # new entry => +10
            points_data[key] = {
                "title": movie.title,
                "points": 10
            }
        else:
            old_points = points_data[key].get("points", 0)
            new_points = max(old_points - 1, 0)
            points_data[key]["title"] = movie.title
            points_data[key]["points"] = new_points

        current_points = points_data[key]["points"]
        rating = get_tmdb_rating_cached(int(key))
        candidate_tuples.append((movie, current_points, rating))

    # 4) Filter
    filtered_candidates = []
    for movie, pts, rating in candidate_tuples:
        if pts >= 5 or rating > 8:
            filtered_candidates.append((movie, pts, rating))
            kept_list.append((movie.title, pts, rating))
        else:
            removed_list.append((movie.title, pts, rating))

    filtered_candidates.sort(key=lambda x: (x[2], x[1]), reverse=True)
    final_movies = [t[0] for t in filtered_candidates]

    save_points(points_data)

    # Debug
    print("\n========== DEBUG LOG ==========")
    print("REMOVED (points <5 and rating <=8):")
    for title, pts, rating in removed_list:
        print(f"  - {title} => points={pts}, rating={rating}")

    print("\nKEPT in collection (before sorting):")
    for title, pts, rating in kept_list:
        print(f"  + {title} => points={pts}, rating={rating}")

    print("\nFinal sorted set:")
    for movie, pts, rating in filtered_candidates:
        print(f"  => {movie.title}, points={pts}, rating={rating}")

    print(f"Final total: {len(final_movies)}")
    print("========== END DEBUG LOG ==========\n")

    # Update or create
    try:
        if collection:
            print(f"Updating collection '{collection_name}'...")
            collection.removeItems(collection.items())
            time.sleep(2)
            if final_movies:
                collection.addItems(final_movies)
                print(f"Collection updated with {len(final_movies)} items.")
            else:
                print("No movies to add; collection will be empty.")
        else:
            if final_movies:
                new_collection = movies_section.createCollection(collection_name, final_movies)
                print(f"Created new collection '{collection_name}' with {len(final_movies)} items.")
            else:
                print("No movies to create a new collection with.")
    except Exception as e:
        print(f"Error updating collection: {e}")

# ----------------- Main -----------------

def main(movie_name: str):
    """
    1) Load YAML config and set up global variables
    2) Initialize clients (Plex, OpenAI, Radarr) from config
    3) Load TMDb cache
    4) GPT recommendations
    5) Add to Radarr if not in Plex
    6) Refresh collection
    7) Save TMDb cache
    """
    # Step 1) Load config
    config = load_config("config.yaml")
    
    # Step 2) Set up globals
    global PLEX_URL, PLEX_TOKEN, OPENAI_API_KEY, RADARR_API_KEY
    global RADARR_URL, RADARR_ROOT_FOLDER, RADARR_TAG_NAME, TMDB_API_KEY
    global POINTS_FILE, TMDB_CACHE_FILE
    global plex, client, radarr

    PLEX_URL = config["plex"]["url"]
    PLEX_TOKEN = config["plex"]["token"]
    OPENAI_API_KEY = config["openai"]["api_key"]
    RADARR_URL = config["radarr"]["url"]
    RADARR_API_KEY = config["radarr"]["api_key"]
    RADARR_ROOT_FOLDER = config["radarr"]["root_folder"]
    RADARR_TAG_NAME = config["radarr"]["tag_name"]
    TMDB_API_KEY = config["tmdb"]["api_key"]

    # File paths
    POINTS_FILE = config["files"]["points_file"]
    TMDB_CACHE_FILE = config["files"]["tmdb_cache_file"]

    # Re-initialize the clients with new config
    plex = PlexServer(PLEX_URL, PLEX_TOKEN)
    client = OpenAI(api_key=OPENAI_API_KEY)
    radarr = RadarrAPI(RADARR_URL, RADARR_API_KEY)

    # Step 3) Load TMDb cache
    load_tmdb_cache()

    # Step 4) GPT
    recs = get_recommendations(movie_name)
    if not recs:
        print("No recommendations generated.")
        return

    # Step 5) Add to Radarr
    print("\nProcessing recommendations from OpenAI:")
    for title in recs:
        found_in_plex = find_plex_movie(title)
        if found_in_plex:
            print(f"Found in Plex already: {found_in_plex.title}")
        else:
            print(f"Not found in Plex: {title} => adding to Radarr...")
            add_to_radarr(title)

    # Step 6) Refresh collection
    refresh_collection_with_points(recs)

    # Step 7) Save the TMDb cache
    save_tmdb_cache()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        print("Usage: python script.py 'Movie Title'")

