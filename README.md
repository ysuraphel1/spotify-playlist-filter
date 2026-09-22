# Spotify Playlist Filter

Two scripts for building a clean, vibe-curated playlist from any Spotify source playlist.

## What it does

1. Reads a source Spotify playlist
2. Finds clean (non-explicit) versions of any explicit tracks
3. Lets you filter by vibe (energy + mood) via a web UI
4. Saves the result to a target Spotify playlist you own

## Setup

### 1. Spotify Developer App

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and create an app
2. Under **Settings**, add `http://127.0.0.1:3000/callback` as a Redirect URI
3. Under **User Management**, add your Spotify account email
4. Copy your **Client ID** and **Client Secret**

### 2. Install dependencies

```bash
pip3 install spotipy flask
```

### 3. Set environment variables

Copy `.env.example` to `.env` and fill in your values, then export them before running:

```bash
export SPOTIFY_CLIENT_ID="your_client_id"
export SPOTIFY_CLIENT_SECRET="your_client_secret"
export SPOTIFY_USERNAME="your_spotify_username"
export SPOTIFY_SOURCE_URL="https://open.spotify.com/playlist/..."
export SPOTIFY_TARGET_URL="https://open.spotify.com/playlist/..."
```

> **Note:** The source playlist must be **public** or owned by your account. The target playlist must be created manually in Spotify beforehand.

---

## Scripts

### graduation_playlist.py (CLI)

Processes the full source playlist and saves clean tracks directly to the target playlist.

```bash
python3 graduation_playlist.py
```

On first run, a browser window opens for Spotify login. After approving, paste the redirect URL back into the terminal.

Set `SKIP_EXPLICIT_SEARCH = False` at the top to search for clean versions of explicit tracks (uses Spotify search quota — may hit rate limits on large playlists).

---

### `graduation_web.py` (Vibe Selector UI)

A local web app that lets you visually filter tracks by vibe before saving.

```bash
python3 graduation_web.py
```

Opens automatically at `http://localhost:5001`.

**Features:**
- **Preset buttons** — Ceremony, Celebration, Bangers, Nostalgic, All Clean
- **Energy slider** — filter out slow/chill tracks
- **Mood slider** — filter out melancholic/dark tracks
- **Click any track** to manually include or exclude it
- **Save button** — pushes the filtered set to your target playlist

Vibe scores are estimated from Spotify artist genre tags and track popularity, normalized across your playlist so the sliders reflect the actual distribution of your tracks.

---

## Notes

- Spotify restricts the audio features endpoint for development-mode apps — vibe scoring uses genre tags as a proxy instead
- The Spotify search API has a daily quota. On large playlists (500+ tracks), the clean-version search may hit the limit. Run again the next day or set `SKIP_EXPLICIT_SEARCH = True` to skip it
- Spotify restricts playlist *creation* for development-mode apps — create the target playlist manually in Spotify and paste its URL into `SPOTIFY_TARGET_URL`
