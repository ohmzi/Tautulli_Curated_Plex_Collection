FROM lscr.io/linuxserver/tautulli:latest


# (Optional) Remove Tautulli's bundled libraries if they conflict.
# For example, if Tautulli bundles its own versions of pydantic,
# you can remove them:
RUN rm -rf /app/tautulli/lib/pydantic* /app/tautulli/lib/pydantic_core*

# 1) Install build deps for PyYAML & other C extensions
RUN apk update && apk add --no-cache \
    build-base \
    python3-dev \
    cython

# 2) Copy in your requirements
COPY requirements.txt /tmp/requirements.txt

# 3) Upgrade pip, setuptools, wheel; then install your dependencies
RUN pip install --upgrade pip setuptools wheel \
 && pip install -r /tmp/requirements.txt --break-system-packages

# 4) (Optionally) copy your custom scripts
# COPY tautulli_watched_movies.py /config/scripts/tautulli_watched_movies.py





