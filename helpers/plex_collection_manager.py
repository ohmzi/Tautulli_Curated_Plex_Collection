import random
from plexapi.exceptions import NotFound

def _get_points(points_data, key: str) -> int:
    v = points_data.get(key, 0)
    if isinstance(v, dict):
        # common shapes: {"points": 3} or {"score": 3}
        if "points" in v:
            return int(v.get("points") or 0)
        if "score" in v:
            return int(v.get("score") or 0)
        return 0
    try:
        return int(v or 0)
    except Exception:
        return 0

def _set_points(points_data, key: str, new_points: int):
    v = points_data.get(key)
    if isinstance(v, dict):
        v["points"] = int(new_points)
        points_data[key] = v
    else:
        points_data[key] = int(new_points)


def _get_or_create_collection(section, collection_name: str, seed_items):
    try:
        return section.collection(collection_name)
    except NotFound:
        if not seed_items:
            raise NotFound(f'Collection "{collection_name}" not found and cannot be created (no seed items).')
        section.createCollection(collection_name, items=seed_items)
        return section.collection(collection_name)

def _fetch_by_rating_key(section, rating_key: str):
    try:
        return section.fetchItem(int(rating_key))
    except Exception:
        return None

def refresh_collection_with_points(
    plex,
    library_name: str,
    collection_name: str,
    plex_movies_this_run: list,
    tmdb_cache,
    points_data: dict,
    *,
    max_points: int = 50,
    logger=None,
    randomize: bool = False,
):
    if logger:
        logger.info(f"collection_refresh: loading library section={library_name!r}")
    section = plex.library.section(library_name)

    # get existing collection
    if logger:
        logger.info(f"collection_refresh: loading collection={collection_name!r}")

    collection = None
    try:
        collection = section.collection(collection_name)
        existing_items = collection.items()
    except NotFound:
        existing_items = []

    if logger:
        logger.info(f"collection_refresh: existing_items={len(existing_items)}")
        
    if existing_items:
        k0 = str(existing_items[0].ratingKey)
        if logger:
            logger.info(f"collection_refresh: points_data sample type={type(points_data.get(k0)).__name__}")


    # ✅ Build the intended final collection set BEFORE diff-update
    final_items, suggested_now_keys = build_final_items_with_points(
        section=section,
        existing_items=existing_items,
        plex_movies_this_run=plex_movies_this_run,
        tmdb_cache=tmdb_cache,
        points_data=points_data,
        max_points=max_points,
    )

    # ... your existing scoring logic that builds final_items ...
    # final_items = [...]
    if logger:
        logger.info(f"collection_refresh: plex_movies_this_run={len(plex_movies_this_run)}")


    # ✅ DIFF UPDATE instead of remove-all/add-all
    current = collection.items() if collection else []
    current_ids = {str(i.ratingKey) for i in current}
    desired_ids = {str(i.ratingKey) for i in final_items}

    to_remove = [i for i in current if str(i.ratingKey) not in desired_ids]
    to_add = [i for i in final_items if str(i.ratingKey) not in current_ids]

    if logger:
        logger.info(
            f"collection_refresh: will_remove={len(to_remove)} will_add={len(to_add)} "
            f"(current={len(current)} desired={len(final_items)})"
        )

    # remove only what’s needed
    if to_remove:
        if logger:
            logger.info("collection_refresh: removing items from collection...")
        collection.removeItems(to_remove)
        if logger:
            logger.info("collection_refresh: remove done")

    # add only what’s needed
    if to_add:
        if logger:
            logger.info("collection_refresh: adding items to collection...")
        collection.addItems(to_add)
        if logger:
            logger.info("collection_refresh: add done")

    # optional: custom random order (can be heavy)
    if randomize:
        if logger:
            logger.info(f"collection_refresh: randomize_collection=ON items={len(final_items)}")

        # ✅ Make it actually random
        random.shuffle(final_items)

        # ✅ Log a “fingerprint” so you can SEE that it changed
        if logger:
            sample = [m.title for m in final_items[:10]]
            logger.info(f"collection_refresh: random sample top10={sample}")
        _apply_custom_order(plex, collection, final_items)
        
        if logger:
            logger.info("collection_refresh: custom order done")
    else:
        if logger:
            logger.info("collection_refresh: randomize disabled (skipping reorder)")

    return {
        "existing_seeded": len(existing_items),
        "suggested_now": len(suggested_now_keys),
        "kept_in_collection": len(final_items),
        "points_total": len(points_data),
    }

def _apply_custom_order(plex, collection, ordered_items):
    """
    Force collection to 'custom' order and then reorder items to match ordered_items.
    ordered_items must be in the exact order you want displayed in Plex.
    """
    try:
        collection.sortUpdate(sort="custom")
    except Exception:
        return

    cid = int(collection.ratingKey)
    prev_id = None

    for item in ordered_items:
        item_id = int(item.ratingKey)
        if prev_id is None:
            path = f"/library/collections/{cid}/items/{item_id}/move"
        else:
            path = f"/library/collections/{cid}/items/{item_id}/move?after={prev_id}"
        plex.query(path, method=plex._session.put)
        prev_id = item_id

def build_final_items_with_points(
    section,
    existing_items: list,
    plex_movies_this_run: list,
    tmdb_cache,
    points_data: dict,
    max_points: int = 50,
):
    """
    Returns:
      final_items: list of Plex items to keep in the collection
      suggested_now_keys: list[str] ratingKeys for items suggested in this run
    Notes:
      - points_data is assumed to be {ratingKey(str): points(int)} (or similar)
      - if an item has no points yet, it starts at 0
    """

    # Start with all existing items + this run's items, de-duped by ratingKey
    by_key = {str(i.ratingKey): i for i in existing_items}
    for i in plex_movies_this_run:
        by_key[str(i.ratingKey)] = i

    # "suggested now" are the movies from this run (keys)
    suggested_now_keys = [str(i.ratingKey) for i in plex_movies_this_run]

    # ensure points exist
    for k in by_key.keys():
        if k not in points_data:
            _set_points(points_data, k, 0)

    # boost this run
    for k in suggested_now_keys:
        _set_points(points_data, k, _get_points(points_data, k) + 1)


    # Sort all items by points desc, then stable by title to avoid jitter
    def sort_key(item):
        k = str(item.ratingKey)
        return (_get_points(points_data, k), (item.title or "").lower())


    all_items = list(by_key.values())
    all_items.sort(key=sort_key, reverse=True)

    # Keep a larger base (existing collection size) but allow cap if you want:
    # If you truly want only max_points total items, uncomment next line.
    # final_items = all_items[:max_points]

    # Better default: keep the whole existing collection, but ensure the top "max_points"
    # are always present by points (prevents stale collection drift)
    final_items = all_items  # keep everything for now

    return final_items, suggested_now_keys

