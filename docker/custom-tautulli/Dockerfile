FROM lscr.io/linuxserver/tautulli:latest


# Remove Tautulli's bundled libraries if they conflict.
RUN rm -rf \
  /app/tautulli/lib/pydantic* \
  /app/tautulli/lib/pydantic_core* \
  /app/tautulli/lib/typing_extensions.py \
  /app/tautulli/lib/typing_extensions*.pyc


# 1) Install build deps for PyYAML & other C extensions
RUN apk update && apk add --no-cache \
    build-base \
    python3-dev \
    cython

# 2) Copy in your requirements (from project root)
COPY requirements.txt /tmp/requirements.txt

# 3) Upgrade pip, setuptools, wheel; then install your dependencies
RUN pip install --upgrade pip setuptools wheel \
 && pip install -r /tmp/requirements.txt --break-system-packages