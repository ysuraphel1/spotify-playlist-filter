#!/usr/bin/env python3
"""
Spotify Graduation Playlist Generator
Creates a clean playlist derived from a source playlist.

Requirements:
    pip install spotipy
"""

import os
import re
import time

import spotipy
from spotipy.oauth2 import SpotifyOAuth

CACHE_PATH = os.path.expanduser("~/.graduation_spotify_cache")

# ── Config ────────────────────────────────────────────────────────────────────
CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID",     "your_client_id")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "your_client_secret")
REDIRECT_URI  = os.getenv("SPOTIFY_REDIRECT_URI",  "http://127.0.0.1:3000/callback")
USERNAME      = os.getenv("SPOTIFY_USERNAME",       "your_spotify_username")
SOURCE_URL    = os.getenv("SPOTIFY_SOURCE_URL",     "https://open.spotify.com/playlist/your_source_playlist")
TARGET_URL    = os.getenv("SPOTIFY_TARGET_URL",     "https://open.spotify.com/playlist/your_target_playlist")

# Set to True to skip searching for clean versions (uses zero search quota).
# Explicit tracks will just be left out instead of substituted.
SKIP_EXPLICIT_SEARCH = True

SCOPE = (
    "playlist-read-private "
    "playlist-read-collaborative "
    "playlist-modify-public "
    "playlist-modify-private"
)
# ──────────────────────────────────────────────────────────────────────────────


def get_all_tracks(sp, playlist_id):
    items, page = [], sp.playlist_items(playlist_id)
    items.extend(page["items"])
    while page.get("next"):
        page = sp.next(page)
        items.extend(page["items"])
    return items


def normalize(name: str) -> str:
    name = name.lower()
    for pat in [
        r"\(clean( version)?\)", r"\[clean( version)?\]",
        r"\(radio edit\)",       r"\[radio edit\]",
        r"\(explicit\)",         r"\[explicit\]",
        r"\(censored\)",         r"\(edited\)",
        r"\(feat\..*?\)",        r"\(ft\..*?\)",
    ]:
        name = re.sub(pat, "", name, flags=re.IGNORECASE)
    return name.strip()


def names_match(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    return na == nb or na.startswith(nb) or nb.startswith(na)


_search_cache: dict = {}

def spotify_search(sp, query):
    """Search with caching and proper rate-limit backoff."""
    if query in _search_cache:
        return _search_cache[query]
    while True:
        try:
            result = sp.search(q=query, type="track", limit=10)
            _search_cache[query] = result
            time.sleep(0.3)
            return result
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                retry_after = int(getattr(e, "headers", {}).get("Retry-After", 5) if hasattr(e, "headers") else 5)
                print(f"\n  Rate limited — waiting {retry_after}s…")
                time.sleep(retry_after + 1)
            else:
                return None
        except Exception:
            return None


def find_clean_version(sp, track):
    if not track["explicit"]:
        return track["id"]

    name   = track["name"]
    artist = track["artists"][0]["name"]
    key    = normalize(name)

    # Only use 2 queries max: structured search first, plain fallback
    queries = [
        f"track:{key} artist:{artist}",
        f"{key} {artist}",
    ]

    for query in queries:
        results = spotify_search(sp, query)
        if not results:
            continue
        for item in results["tracks"]["items"]:
            if item["explicit"]:
                continue
            item_artists = {a["name"].lower() for a in item["artists"]}
            if artist.lower() not in item_artists:
                continue
            if names_match(name, item["name"]):
                return item["id"]

    return None


def add_tracks(sp, playlist_id, track_ids):
    for i in range(0, len(track_ids), 100):
        sp.playlist_add_items(playlist_id, track_ids[i : i + 100])


def main():
    auth_manager = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        username=USERNAME,
        cache_path=CACHE_PATH,
    )
    sp = spotipy.Spotify(auth_manager=auth_manager)

    me = sp.me()
    print(f"Authenticated as: {me['display_name']} ({me['id']})")
    token_info = sp.auth_manager.get_cached_token()
    granted = token_info.get("scope", "") if token_info else ""
    print(f"Granted scopes: {granted}\n")

    target_id = TARGET_URL.split("/")[-1].split("?")[0]

    # Verify write access before spending time processing tracks
    print("Checking write access to target playlist…")
    try:
        sp.playlist_change_details(target_id, description="Graduation (Clean) — filling now…")
    except Exception as e:
        print(f"Cannot write to target playlist: {e}")
        return
    print("  OK\n")

    playlist_id = SOURCE_URL.split("/")[-1].split("?")[0]

    try:
        meta = sp.playlist(playlist_id, fields="name,owner")
        print(f"Source playlist: \"{meta['name']}\" by {meta['owner']['display_name']}")
    except Exception as e:
        print(f"Cannot access source playlist: {e}")
        return

    print("Fetching tracks…")
    raw = get_all_tracks(sp, playlist_id)
    print(f"  {len(raw)} tracks found\n")

    clean_ids, skipped = [], []

    for i, item in enumerate(raw, 1):
        track = item.get("track") or item.get("item")
        if not track or item.get("is_local") or track.get("is_local"):
            continue
        if track.get("type") != "track":
            continue

        name   = track["name"]
        artist = track["artists"][0]["name"]
        tag    = "EXPLICIT" if track["explicit"] else "clean  "

        print(f"[{i:>3}/{len(raw)}] [{tag}] {name} — {artist}")

        if track["explicit"]:
            if SKIP_EXPLICIT_SEARCH:
                skipped.append(f"{name} — {artist}")
            else:
                cid = find_clean_version(sp, track)
                if cid:
                    clean_ids.append(cid)
                    print(f"          └─ clean version found")
                else:
                    skipped.append(f"{name} — {artist}")
                    print(f"          └─ no clean version found, skipping")
        else:
            clean_ids.append(track["id"])

    print(f"\n{len(clean_ids)} clean tracks — clearing target and adding…")
    sp.playlist_replace_items(target_id, [])
    add_tracks(sp, target_id, clean_ids)
    sp.playlist_change_details(target_id, description=f"Clean graduation tracks. {len(clean_ids)} songs.")
    print(f"Done! Playlist: {TARGET_URL}")

    if skipped:
        print(f"\nSkipped {len(skipped)} tracks (no clean version on Spotify):")
        for s in skipped:
            print(f"  • {s}")


if __name__ == "__main__":
    main()
