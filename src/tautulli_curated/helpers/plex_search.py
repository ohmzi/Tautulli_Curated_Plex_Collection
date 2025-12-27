import re

def normalize(title: str) -> str:
    return re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip().lower()

def find_plex_movie(plex, title):
    """
    Fast Plex lookup using server-side search.
    """
    section = plex.library.section("Movies")
    results = section.search(title=title)

    if not results:
        return None

    target = normalize(title)

    for movie in results:
        if normalize(movie.title) == target:
            return movie

    return None

