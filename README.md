# Plex Movie Recommendations Script Triggered from Tautulli within Docker

**Table of Contents**  
- [Overview](#overview)  
- [Features](#features)  
- [Requirements](#requirements)  
- [Usage (Docker)](#usage-docker)  
  - [1. Prerequisites](#1-prerequisites)  
  - [2. Prepare Your `config.yaml`](#2-prepare-your-configyaml)  
  - [3. Build the Docker Image](#3-build-the-docker-image)  
  - [4. Redeploy Tautulli with the Custom Image](#4-redeploy-tautulli-with-the-custom-image)  
  - [5. Set Up Tautulli Automation](#5-set-up-tautulli-automation)

---

## Overview

This script automates the process of:

1. **Generating movie recommendations** via **OpenAI** or fallback **TMDB** .
2. **Checking Plex** to see if recommended movies already exist.
3. **Adding missing movies to Radarr** for automate downloading.
4. **Refreshing a custom Plex collection** (“Inspired by your Immaculate Taste”) using a **points system** to keep it relevant and cycle them out as they get old.

---

## Features

- **GPT Recommendations:**  
  Generates up to 50 movie suggestions based on a “seed” title, including sequels, same-director picks, similar genres, hidden gems, etc.

- **Plex Integration:**  
  - Searches Plex for each recommended title.  
  - If found, the script will later include it in (or keep it in) a dedicated collection.

- **Radarr Automation:**  
  - If a recommended title is not in Plex, the script adds it to Radarr with a configurable root folder and tag, so Radarr can download it.

- **Points System:**  
  - New recommendations get +10 points.  
  - Each run, existing items lose 1 point.  
  - Movies must have ≥5 points or a TMDb rating >8 to remain in the collection.  
  - Points are persisted across runs in a JSON file.

- **TMDb Caching & Ratings:**  
  - Caches TMDb IDs and ratings locally to reduce external API calls.  
  - Uses each movie’s rating (>8) to help decide if it stays in the collection despite low points.

- **YAML Configuration:**  
  - No hardcoding credentials.  
  - All API keys, file paths, and server URLs are loaded from `config.yaml`.

---

## Requirements

1. **Docker & Portainer**  
2. **Tautulli**
3. **Plex**
4. **Radarr**

---

## Usage (Docker)

This project includes a **Dockerfile** based on
[`lscr.io/linuxserver/tautulli:latest`](https://hub.docker.com/r/lscr.io/linuxserver/tautulli).
It installs the necessary Python libraries (e.g., `openai`, `arrapi`, `PyYAML`) and allows
you to run the recommendation script **inside** the Tautulli container.

### 1. Prerequisites

- **Docker, Portainer, Plex, Tautulli, and Radarr** must already be installed and working.
- You’ll need valid credentials for each service (tokens, API keys, etc.).

### 2. Prepare Your `config.yaml`

1. Create or edit `config.yaml` with your real **Plex**, **OpenAI**, **Radarr**, and **TMDb** credentials.  
2. Make sure `config.yaml` is placed alongside your Docker build or mounted at runtime (see below).

### 3. Build the Docker Image

From the directory containing your `Dockerfile`, run the command in terminal: 
```bash
docker build -t tautulli-recommendations .
```
### 4. Redeploy Tautulli with the Custom Image
If you removed the old container, you’ll now create a new one:

1. In Portainer, choose Add Container (if you removed the old one) or Duplicate/Edit (if you’re editing the existing container).
2. In the Image field, enter the name of your custom image:
```bash
tautulli-recommendations:latest
```
3. Proceed to configure ports, volumes, and environment variables as needed, then Deploy the container.

### 5. Set Up Tautulli Automation
To have Tautulli automatically call your script whenever someone finishes watching a movie (or meets another trigger):

1. Open Tautulli → Settings → Notification Agents.
2. Click Add a new notification agent and choose Script.
3. Script Folder: Browse to the folder where you stored the recommendation script (e.g., /app if that’s where tautulli_watched_movies.py resides).
4. Script File: Select the script file you want Tautulli to run (e.g., tautulli_watched_movies.py).
5. Description: Provide a friendly name (e.g., “Movie Recommendation Script”).
6. Trigger: Choose Watched (so the script runs when a user finishes watching a movie).
7. Arguments: Under Watched arguments, pass "{title}" (including quotes), so the script receives the movie’s title.
   Example:
   ```bash
    python tautulli_watched_movies.py "{title}"
9. Test Notification:
   Click Test → select your script → provide "Inception (2010)" as the argument.
   This simulates a watch event for “Inception (2010).”
10. Verify:
    Check Tautulli’s logs to see if the script ran successfully and see any output (e.g., “Found in Plex already,” “Added to Radarr,” etc.).


---


**Now Whenever Tautulli detects that a user has finished watching a movie, it will trigger your script with the movie’s title. With each run, your collection becomes more finely curated.**

**Tip: Add the collection to your Home screen and position it at the very top—right beneath the Continue Watching list.**

**Enjoy using this script! If it enhances your movie nights. If you Encounter any issues or have ideas for enhancements? Feel free to open an issue or submit a pull request.**


---


## License

This project is provided “as is” without warranty of any kind. You are free to use, modify, and distribute this code as per the [MIT License](https://opensource.org/licenses/MIT).

---
View of Collection in Plex App:
![alt text](https://github.com/ohmzi/Tautulli_Curated_Plex_Collection/blob/main/sample_run_pictures/plex_mobile_app_screenshot.jpg?raw=true)

Sample Run in Tautulli:
![alt text](https://github.com/ohmzi/Tautulli_Curated_Plex_Collection/blob/main/sample_run_pictures/tautulli_log_screenshot_1.jpg?raw=true)
![alt text](https://github.com/ohmzi/Tautulli_Curated_Plex_Collection/blob/main/sample_run_pictures/tautulli_log_screenshot_2.jpg?raw=true)
![alt text](https://github.com/ohmzi/Tautulli_Curated_Plex_Collection/blob/main/sample_run_pictures/tautulli_log_screenshot_3.jpg?raw=true)


