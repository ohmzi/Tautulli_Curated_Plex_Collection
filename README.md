# Plex Movie Recommendations Script Triggered from Tautulli within Docker

**Version:** 2.0.0

**Table of Contents**  
- [Overview](#overview)  
- [Architecture & Flow](#architecture--flow)
- [Features](#features)  
- [Requirements](#requirements)  
- [Installation-Setup](#installation-setup)  
  - [1. Prerequisites](#1-prerequisites)  
  - [2. Prepare Your `config.yaml`](#2-prepare-your-configyaml)  
  - [3. Build the Docker Image](#3-build-the-docker-image)  
  - [4. Redeploy Tautulli with the Custom Image](#4-redeploy-tautulli-with-the-custom-image)  
  - [5. Set Up Tautulli Automation](#5-set-up-tautulli-automation)
- [Project Structure](#project-structure)

---

## Overview

This script automates the process of:

1. **Generating movie recommendations via OpenAI (with TMDb fallback)**
2. **Checking Plex for existing recommendations**
3. **Adding missing movies to Radarr**
4. **Maintaining a dynamic Plex collection ("Inspired by your Immaculate Taste")**
5. **Using a points system to keep recommendations fresh and relevant**

---

## Architecture & Flow

### Entry Point
The main script `tautulli_immaculate_taste_collection.py` is triggered by Tautulli when a movie is watched. It accepts two arguments:
- Movie title (from Tautulli)
- Media type (should be "movie")

### Execution Pipeline

The script follows this flow:

1. **Initialization** (`helpers/pipeline_recent_watch.py`)
   - Loads configuration from `config.yaml` via `config_loader.py`
   - Connects to Plex server
   - Initializes TMDb cache (`tmdb_cache.json`)
   - Loads recommendation points data (`recommendation_points.json`)

2. **Recommendation Generation** (`helpers/recommender.py`)
   - **Primary**: Attempts OpenAI recommendations via `chatgpt_utils.py`
     - Uses GPT to generate up to 50 movie suggestions based on tone, themes, atmosphere, and cinematic style
     - Includes mix of mainstream, indie, international, and arthouse films
   - **Fallback**: If OpenAI fails or returns empty, uses TMDb advanced recommender (`tmdb_recommender.py`)
     - Merges recommendations from `/recommendations`, `/similar`, and `/discover` endpoints
     - Filters by genre overlap and vote count
     - Scores candidates by TMDb rating (cached)

3. **Plex Lookup** (`helpers/plex_search.py`)
   - Searches Plex library for each recommended movie
   - Normalizes titles (removes year suffixes) for accurate matching
   - Separates movies into: found in Plex vs. missing

4. **Radarr Integration** (`helpers/radarr_utils.py`)
   - For movies not found in Plex:
     - Looks up movie in Radarr by TMDb ID
     - If exists but unmonitored, sets to monitored
     - If missing, adds to Radarr with:
       - Configurable root folder
       - Quality profile
       - Custom tag
       - Triggers automatic search

5. **Collection Management** (`helpers/plex_collection_manager.py`)
   - Updates points for all movies:
     - New recommendations from this run: +1 point
     - Existing items: points remain (decay handled separately if needed)
   - Builds final collection set based on points
   - Performs diff-based update (only adds/removes what changed)
   - Optional: Randomizes collection order if configured

6. **Persistence**
   - Saves updated points data to `recommendation_points.json`
   - Saves TMDb cache (IDs and ratings) to `tmdb_cache.json`

### Supporting Modules

- **`config_loader.py`**: Loads and validates YAML configuration into typed dataclasses
- **`logger.py`**: Sets up structured logging with step context tracking
- **`run_context.py`**: Provides step-based timing and logging context
- **`tmdb_cache.py`**: Caches TMDb movie IDs and ratings to reduce API calls
- **`tmdb_client.py`**: Basic TMDb API client functions

---

## Features

- **GPT Recommendations:**  
  Generates up to 50 (configurable) movie suggestions based on a "seed" title, including sequels, same-director picks, similar genres, hidden gems, etc. Uses intelligent prompting to ensure a diverse mix of mainstream, indie, international, and arthouse films.

- **TMDb Fallback:**  
  If OpenAI is unavailable, falls back to TMDb's recommendation engine, which merges results from multiple endpoints (`/recommendations`, `/similar`, `/discover`) and scores by rating.

- **Plex Integration:**  
  - Searches Plex library for each recommended title using server-side search
  - Normalizes titles for accurate matching (handles year suffixes)
  - Maintains a dedicated collection with dynamic updates

- **Radarr Automation:**  
  - If a recommended title is not in Plex, the script adds it to Radarr
  - Uses TMDb ID for accurate matching
  - Configurable root folder, quality profile, and tags
  - Automatically triggers search for newly added movies
  - If movie already exists in Radarr but is unmonitored, sets it to monitored

- **Points System:**  
  - New recommendations from each run get +1 point
  - Points are persisted across runs in `recommendation_points.json`
  - Collection maintains all movies with their current points
  - Points can be used to prioritize or filter collection items

- **TMDb Caching & Ratings:**  
  - Caches TMDb IDs and ratings locally in `tmdb_cache.json` to reduce external API calls
  - Automatically fetches and stores ratings for scoring recommendations
  - Supports both legacy and new cache formats

- **YAML Configuration:**  
  - No hardcoded credentials
  - All API keys, file paths, and server URLs are loaded from `config.yaml`
  - Type-safe configuration with dataclasses

- **Structured Logging:**  
  - Step-based logging with timing information
  - Context-aware log messages
  - Pipeline summary statistics

---

## Requirements

1. **Core Services:**
   - Docker
   - Plex Media Server
   - Tautulli
   - Radarr (for automatic movie downloads)

2. **APIs:**
   - TMDb API Key (required)
   - OpenAI API Key (optional, but recommended for better recommendations)

3. **Python Dependencies:**
   - `requests` (for API calls)
   - `PyYAML` (for configuration)
   - `plexapi` (for Plex integration)
   - `openai` (optional, for GPT recommendations)

---

## Installation-Setup

This project includes a **Dockerfile** based on [`lscr.io/linuxserver/tautulli:latest`](https://hub.docker.com/r/lscr.io/linuxserver/tautulli). It installs the necessary Python libraries and allows you to run the recommendation script **inside** the Tautulli container.

### 1. Prerequisites

- **Docker, Plex, Tautulli, and Radarr** must already be installed and working.
- You'll need valid credentials for each service (tokens, API keys, etc.).

### 2. Prepare Your `config.yaml`

1. Create or edit `config.yaml` in the project root with your real credentials:

```yaml
plex:
  url: "http://localhost:32400"
  token: "YOUR_PLEX_TOKEN"
  movie_library_name: "Movies"
  collection_name: "Inspired by your Immaculate Taste"
  randomize_collection: true  # Optional: randomize collection order

openai:
  api_key: "sk-proj-XXXXXXXXXXXXXXXXXXX"
  model: "gpt-5.2"  # Default model used by all scripts
  recommendation_count: 50

tmdb:
  api_key: "YOUR_TMDB_API_KEY"
  recommendation_count: 50

radarr:
  url: "http://localhost:7878"
  api_key: "YOUR_RADARR_API_KEY"
  root_folder: "/path/to/Movies"
  tag_name: "recommended"  # Optional tag for recommended movies
  quality_profile_id: 1

files:
  points_file: "recommendation_points.json"
  tmdb_cache_file: "tmdb_cache.json"
```

2. Make sure `config.yaml` is placed in the project root and will be accessible to the Docker container (either copied into the image or mounted as a volume).

### 3. Build the Docker Image

From the directory `custom-tautulli/` that contains the `Dockerfile`, run:

```bash
docker build -t tautulli_recommendations .
```

### 4. Redeploy Tautulli with the Custom Image

If you removed the old container, you'll now create a new one. Follow the steps based on whether you're using Portainer or Docker Compose.

- **Option 1: Using Portainer**

1. In Portainer, choose Add Container (if you removed the old one) or Duplicate/Edit (if you're editing the existing container).
2. In the Image field, enter the name of your custom image:
   ```bash
   tautulli_recommendations:latest
   ```
3. Proceed to configure ports, volumes, and environment variables as needed, then Deploy the container.

- **Option 2: Using Docker Compose**

If you are managing Tautulli with Docker Compose, follow these steps:

1. Stop the existing Tautulli container:
   ```bash
   docker compose stop tautulli
   ```

2. Build the new custom image:
   ```bash
   docker build -t tautulli_recommendations .
   ```

3. Start Tautulli with Docker Compose:
   ```bash
   docker compose up -d tautulli
   ```

**Important**: Ensure that your `config.yaml` and data files (`recommendation_points.json`, `tmdb_cache.json`) are either:
- Copied into the Docker image during build, or
- Mounted as volumes in your container configuration

### 5. Set Up Tautulli Automation

To have Tautulli automatically call your script whenever someone finishes watching a movie:

1. Open Tautulli → Settings → Notification Agents.
2. Click Add a new notification agent and choose **Script**.
3. **Script Folder**: Browse to the folder where the script is located (e.g., `/app` or the mounted volume path).
4. **Script File**: Select `tautulli_immaculate_taste_collection.py`.
5. **Description**: Provide a friendly name (e.g., "Movie Recommendation Script").
6. **Trigger**: Choose **Watched** (so the script runs when a user finishes watching a movie).
7. **Arguments**: Under Watched arguments, pass:
   ```bash
   "{title}" "{media_type}"
   ```
   This passes both the movie title and media type to the script.
8. **Test Notification**:  
   Click Test → select your script → provide `"Inception (2010)"` as the first argument and `movie` as the second argument.
9. **Verify**:  
   Check Tautulli's logs to see if the script ran successfully and view the output (e.g., "Found in Plex already," "Added to Radarr," etc.).

---

## Project Structure

```
Tautulli_Curated_Plex_Collection/
├── tautulli_immaculate_taste_collection.py  # Main entry point
├── config.yaml                              # Configuration file
├── requirements.txt                         # Python dependencies
├── recommendation_points.json              # Points data (generated)
├── tmdb_cache.json                          # TMDb cache (generated)
├── helpers/
│   ├── pipeline_recent_watch.py            # Main pipeline orchestration
│   ├── config_loader.py                     # YAML config loader
│   ├── logger.py                            # Logging setup
│   ├── run_context.py                       # Step tracking context
│   ├── recommender.py                       # Recommendation orchestrator
│   ├── chatgpt_utils.py                     # OpenAI integration
│   ├── tmdb_recommender.py                  # TMDb recommendation engine
│   ├── tmdb_cache.py                        # TMDb caching layer
│   ├── tmdb_client.py                       # Basic TMDb API client
│   ├── plex_search.py                       # Plex movie search
│   ├── plex_collection_manager.py           # Collection management
│   └── radarr_utils.py                      # Radarr integration
└── custom-tautulli/
    ├── Dockerfile                           # Custom Tautulli image
    ├── docker-compose.yml                   # Docker Compose config
    └── requirements.txt                     # Additional dependencies
```

---

**Now whenever Tautulli detects that a user has finished watching a movie, it will trigger your script with the movie's title. With each run, your collection becomes more finely curated.**

**Tip: Add the collection to your Home screen and position it at the very top—right beneath the Continue Watching list.**

**Enjoy using this script! I hope it enhances your movie selection. If you encounter any issues or have ideas for enhancements, feel free to open an issue or submit a pull request.**

---

## License

This project is provided "as is" without warranty of any kind. You are free to use, modify, and distribute this code as per the [MIT License](https://opensource.org/licenses/MIT).

---

## Screenshots

**View of Collection in Plex App:**
![alt text](https://github.com/ohmzi/Tautulli_Curated_Plex_Collection/blob/main/sample_run_pictures/plex_mobile_app_screenshot.jpg?raw=false)

**Logs from Tautulli after a test run:**
![alt text](https://github.com/ohmzi/Tautulli_Curated_Plex_Collection/blob/main/sample_run_pictures/tautulli_log_screenshot_1.jpg?raw=false)
![alt text](https://github.com/ohmzi/Tautulli_Curated_Plex_Collection/blob/main/sample_run_pictures/tautulli_log_screenshot_2.jpg?raw=false)
![alt text](https://github.com/ohmzi/Tautulli_Curated_Plex_Collection/blob/main/sample_run_pictures/tautulli_log_screenshot_3.jpg?raw=false)
