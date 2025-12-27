import random
import json
import time
from plexapi.exceptions import NotFound, BadRequest

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
        _apply_custom_order(plex, collection, final_items, logger=logger)
        
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

def _apply_custom_order(plex, collection, ordered_items, logger=None):
    """
    Force collection to 'custom' order and then reorder items to match ordered_items.
    ordered_items must be in the exact order you want displayed in Plex.
    This function will continue even if some items fail to reorder.
    """
    try:
        try:
            if logger:
                logger.debug("  Setting collection sort to 'custom'...")
            collection.sortUpdate(sort="custom")
        except Exception as e:
            if logger:
                logger.warning(f"  Could not set collection sort to custom: {e}")
            return

        cid = int(collection.ratingKey)
        prev_id = None
        total = len(ordered_items)
        failed_moves = []
        successful_moves = 0

        # Get current collection items to verify they exist
        try:
            current_collection_items = {int(item.ratingKey) for item in collection.items()}
        except Exception as e:
            if logger:
                logger.warning(f"  Could not verify collection items: {e}")
            current_collection_items = set()

        for i, item in enumerate(ordered_items, 1):
            # Log progress every 100 items or at key milestones
            if logger and (i % 100 == 0 or i == 1 or i == total or (i % 500 == 0)):
                logger.info(f"  Reordering progress: {i}/{total} items ({i*100//total}%) - {successful_moves} successful, {len(failed_moves)} failed")
            
            item_id = int(item.ratingKey)
            
            # Verify item is in collection before trying to move it
            if item_id not in current_collection_items:
                if logger:
                    logger.debug(f"  Skipping item {item_id} - not in collection (item {i}/{total})")
                failed_moves.append({
                    'item_id': item_id,
                    'title': getattr(item, 'title', 'Unknown'),
                    'reason': 'not in collection'
                })
                continue
            
            try:
                if prev_id is None:
                    path = f"/library/collections/{cid}/items/{item_id}/move"
                else:
                    # Verify prev_id is still valid (in case previous moves failed)
                    if prev_id not in current_collection_items:
                        if logger:
                            logger.debug(f"  Previous item {prev_id} not in collection, resetting order")
                        path = f"/library/collections/{cid}/items/{item_id}/move"
                        prev_id = None
                    else:
                        path = f"/library/collections/{cid}/items/{item_id}/move?after={prev_id}"
                
                plex.query(path, method=plex._session.put)
                prev_id = item_id
                successful_moves += 1
                
                # Small delay to avoid overwhelming Plex
                if i % 50 == 0:
                    import time
                    time.sleep(0.1)
                    
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                if logger:
                    item_title = getattr(item, 'title', 'Unknown')
                    logger.warning(f"  Failed to move item {item_id} ({item_title}) - item {i}/{total}: {error_type}")
                    if "bad_request" in error_msg.lower() or "400" in error_msg:
                        logger.debug(f"    Plex rejected the move request - item may already be in position")
                    elif "timeout" in error_msg.lower():
                        logger.warning(f"    Request timed out - Plex may be overloaded")
                
                failed_moves.append({
                    'item_id': item_id,
                    'title': getattr(item, 'title', 'Unknown'),
                    'reason': error_type,
                    'error': error_msg[:100]  # Truncate long error messages
                })
                # Don't update prev_id if move failed, but continue with next item
                # This way we can try to continue ordering from where we left off
                continue
        
        if logger:
            if failed_moves:
                logger.warning(f"  Reordering completed with {len(failed_moves)} failed moves out of {total} items")
                logger.info(f"  Successfully reordered: {successful_moves}/{total} items ({successful_moves*100//total}%)")
                if len(failed_moves) <= 10:
                    for failed in failed_moves:
                        logger.debug(f"    - {failed['title']} (ID: {failed['item_id']}) - {failed['reason']}")
                else:
                    logger.debug(f"    First 5 failed items:")
                    for failed in failed_moves[:5]:
                        logger.debug(f"      - {failed['title']} (ID: {failed['item_id']}) - {failed['reason']}")
                    logger.debug(f"    ... and {len(failed_moves) - 5} more")
            else:
                logger.info(f"  Successfully reordered all {total} items")
    
    except Exception as e:
        # Catch any unexpected exceptions to prevent script failure
        error_type = type(e).__name__
        error_msg = str(e)
        if logger:
            logger.warning(f"  Unexpected error during reordering: {error_type}")
            logger.warning(f"  Collection items have been added, but ordering may be incomplete")
            logger.debug(f"  Error details: {error_msg[:200]}")
        # Don't re-raise - collection is still functional

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


def save_collection_state_to_json(
    final_items: list,
    points_data: dict,
    output_path: str,
    logger=None,
):
    """
    Saves the collection state to JSON file instead of updating Plex directly.
    This allows the main script to defer collection updates to a separate process.
    
    Args:
        final_items: List of Plex items that should be in the collection
        points_data: Dictionary of rating keys to points
        output_path: Path to save the JSON file
        logger: Optional logger instance
    """
    collection_state = {
        "rating_keys": [str(item.ratingKey) for item in final_items],
        "items": [
            {
                "rating_key": str(item.ratingKey),
                "title": item.title,
                "year": getattr(item, "year", None),
                "points": _get_points(points_data, str(item.ratingKey)),
            }
            for item in final_items
        ],
    }
    
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(collection_state, f, indent=2, ensure_ascii=False)
        if logger:
            logger.info(f"Saved collection state to {output_path} (items={len(final_items)})")
    except Exception as e:
        if logger:
            logger.exception(f"Failed to save collection state to {output_path}")
        raise


def load_collection_state_from_json(input_path: str, logger=None):
    """
    Loads collection state from JSON file.
    
    Returns:
        dict with "rating_keys" and "items" keys, or None if file doesn't exist
    """
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if logger:
            logger.info(f"Loaded collection state from {input_path} (items={len(data.get('items', []))})")
        return data
    except FileNotFoundError:
        if logger:
            logger.info(f"Collection state file not found: {input_path}")
        return None
    except Exception as e:
        if logger:
            logger.exception(f"Failed to load collection state from {input_path}")
        return None


def apply_collection_state_to_plex(
    plex,
    library_name: str,
    collection_name: str,
    collection_state: dict,
    logger=None,
):
    """
    Applies the collection state to Plex by:
    1. Removing all existing items from the collection
    2. Adding all items from the collection_state in order
    
    This is designed to run during off-peak hours to avoid overwhelming Plex.
    
    Args:
        plex: PlexServer instance
        library_name: Name of the Plex library
        collection_name: Name of the collection
        collection_state: Dictionary with "rating_keys" and "items" keys
        logger: Optional logger instance
    """
    if logger:
        logger.info(f"apply_collection: loading library section={library_name!r}")
    
    # Verify connection is still alive before proceeding
    try:
        if logger:
            logger.debug("  Verifying Plex connection...")
        _ = plex.friendlyName  # Simple connection test
    except Exception as e:
        if logger:
            logger.error(f"apply_collection: Plex connection lost: {type(e).__name__}: {e}")
            logger.error("  Connection may have timed out or server is unreachable")
        raise
    
    # Load library section
    try:
        section = plex.library.section(library_name)
    except Exception as e:
        if logger:
            logger.error(f"apply_collection: Failed to load library section: {type(e).__name__}: {e}")
        raise
    
    # Get or create collection
    collection = None
    try:
        collection = section.collection(collection_name)
        existing_items = collection.items()
    except NotFound:
        # Collection doesn't exist yet - we'll create it with the items
        existing_items = []
        if logger:
            logger.info(f"apply_collection: collection not found, will create it")
    
    if logger:
        logger.info(f"apply_collection: existing_items={len(existing_items)}")
    
    # Fetch items by rating key and filter to only movies
    rating_keys = collection_state.get("rating_keys", [])
    desired_items = []
    failed_keys = []
    filtered_non_movies = []
    
    for rating_key in rating_keys:
        item = _fetch_by_rating_key(section, rating_key)
        if item:
            # Only include movie items (filter out clips, shows, etc.)
            item_type = getattr(item, 'type', '').lower()
            if item_type == 'movie':
                desired_items.append(item)
            else:
                filtered_non_movies.append({
                    'rating_key': rating_key,
                    'title': getattr(item, 'title', 'Unknown'),
                    'type': item_type
                })
                if logger:
                    logger.debug(f"apply_collection: filtering out non-movie item: {getattr(item, 'title', 'Unknown')} (type: {item_type})")
        else:
            failed_keys.append(rating_key)
            if logger:
                logger.debug(f"apply_collection: could not find item with rating_key={rating_key}")
    
    if failed_keys:
        if logger:
            logger.warning(f"apply_collection: failed to fetch {len(failed_keys)} items")
    
    if filtered_non_movies:
        if logger:
            logger.warning(f"apply_collection: filtered out {len(filtered_non_movies)} non-movie items (clips, shows, etc.)")
            # Log a sample of filtered items
            sample = filtered_non_movies[:5]
            for filtered in sample:
                logger.debug(f"  - {filtered['title']} (type: {filtered['type']})")
            if len(filtered_non_movies) > 5:
                logger.debug(f"  ... and {len(filtered_non_movies) - 5} more")
    
    if logger:
        logger.info(f"apply_collection: desired_items={len(desired_items)} (movies only)")
    
    # Remove all existing items
    if existing_items:
        if logger:
            logger.info(f"apply_collection: removing all {len(existing_items)} existing items...")
            logger.info("  This may take a while for large collections. Please wait...")
        try:
            start_time = time.time()
            collection.removeItems(existing_items)
            elapsed = time.time() - start_time
            if logger:
                logger.info(f"apply_collection: remove completed in {elapsed:.1f} seconds")
        except Exception as e:
            if logger:
                logger.error(f"apply_collection: ERROR removing items: {type(e).__name__}: {e}")
            raise
    
    # Add all desired items
    if desired_items:
        if not collection:
            # Create collection if it doesn't exist
            if logger:
                logger.info(f"apply_collection: creating collection with {len(desired_items)} items...")
            try:
                start_time = time.time()
                section.createCollection(collection_name, items=desired_items)
                collection = section.collection(collection_name)
                elapsed = time.time() - start_time
                if logger:
                    logger.info(f"apply_collection: collection created in {elapsed:.1f} seconds")
            except Exception as e:
                if logger:
                    logger.error(f"apply_collection: ERROR creating collection: {type(e).__name__}: {e}")
                raise
        else:
            if logger:
                logger.info(f"apply_collection: adding {len(desired_items)} items...")
                logger.info("  This may take a while for large collections. Please wait...")
            try:
                start_time = time.time()
                collection.addItems(desired_items)
                elapsed = time.time() - start_time
                if logger:
                    logger.info(f"apply_collection: add completed in {elapsed:.1f} seconds")
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                if logger:
                    logger.error(f"apply_collection: ERROR adding items: {error_type}: {error_msg}")
                    # Check for specific Plex API errors
                    if "mix media types" in error_msg.lower() or "badrequest" in error_type.lower():
                        logger.error("  This error means non-movie items were included in the collection")
                        logger.error("  The script should have filtered these out - this is a bug")
                        logger.error(f"  Items being added: {len(desired_items)}")
                        # Try to identify problematic items
                        if desired_items:
                            item_types = {}
                            for item in desired_items[:20]:  # Check first 20
                                item_type = getattr(item, 'type', 'unknown')
                                item_types[item_type] = item_types.get(item_type, 0) + 1
                            logger.error(f"  Item types found: {item_types}")
                    elif "timeout" in error_msg.lower():
                        logger.error("  Plex server timed out - it may be overloaded")
                        logger.error("  Try running the script again later")
                    elif "connection" in error_msg.lower():
                        logger.error("  Connection to Plex was lost")
                        logger.error("  Check if Plex server is still running")
                raise
    
    # Apply custom order (randomized order from JSON)
    if desired_items:
        if logger:
            logger.info(f"apply_collection: applying custom order for {len(desired_items)} items...")
            logger.info("  Reordering items. This may take several minutes for large collections...")
            logger.info("  Note: Some items may fail to reorder, but the script will continue...")
        try:
            start_time = time.time()
            _apply_custom_order(plex, collection, desired_items, logger=logger)
            elapsed = time.time() - start_time
            if logger:
                logger.info(f"apply_collection: custom order completed in {elapsed:.1f} seconds")
        except (BadRequest, Exception) as e:
            error_type = type(e).__name__
            error_msg = str(e)
            if logger:
                logger.warning(f"apply_collection: Some errors occurred during custom ordering: {error_type}")
                logger.warning(f"  The collection has been updated, but ordering may be incomplete")
                logger.warning(f"  This is usually not critical - items are still in the collection")
                if isinstance(e, BadRequest) or "bad_request" in error_msg.lower() or "400" in error_msg:
                    logger.warning(f"  Plex rejected some reorder requests (this is common with large collections)")
                logger.debug(f"  Full error: {error_msg[:200]}")
            # Don't raise - collection is still updated, just ordering may be incomplete
    
    return {
        "existing_items": len(existing_items),
        "desired_items": len(desired_items),
        "failed_keys": len(failed_keys),
    }

