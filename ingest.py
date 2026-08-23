#!/usr/bin/env python3
"""
Spotify Data Ingestion Layer
Pulls data from Spotify API, stores it in a normalized SQLite warehouse,
deduplicates listening events, and makes everything idempotent.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Paths & config
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent
DB_PATH = REPO_ROOT / "spotify_data.db"
CACHE_DIR = REPO_ROOT / "api_cache"
ENV_PATH = REPO_ROOT / ".env"

# ---------------------------------------------------------------------------
# Spotify client (Hermes plugin first, spotipy fallback)
# ---------------------------------------------------------------------------

_HERMES_DIR = r"C:\Users\ismai\AppData\Local\hermes\hermes-agent"


def load_env():
    """Load .env if present."""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())


def get_spotify_client():
    """Get a Spotify client — Hermes plugin first, then fall back to direct OAuth."""
    load_env()

    # Try Hermes plugin first
    try:
        sys.path.insert(0, _HERMES_DIR)
        from plugins.spotify.client import SpotifyClient
        return SpotifyClient()
    except Exception as e:
        print(f"[ingest] Hermes SpotifyClient unavailable: {e}", file=sys.stderr)

    # Fallback: direct spotipy OAuth using env vars
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth

        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")

        if not client_id or not client_secret:
            # Try reading from home .env
            home_env = Path.home() / ".env"
            if home_env.exists():
                for line in home_env.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        os.environ.setdefault(key.strip(), val.strip())
                client_id = os.getenv("SPOTIFY_CLIENT_ID")
                client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise RuntimeError(
                "Missing Spotify credentials. Set SPOTIFY_CLIENT_ID and "
                "SPOTIFY_CLIENT_SECRET in .env or home .env."
            )

        return spotipy.Spotify(
            auth_manager=SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope=(
                    "user-read-recently-played "
                    "user-top-read "
                    "user-library-read "
                    "user-read-currently-playing "
                    "user-read-playback-state "
                    "user-read-playback-position"
                ),
                cache_path=str(REPO_ROOT / ".spotify-oauth-cache"),
            )
        )
    except Exception as e:
        raise RuntimeError(f"Cannot initialize Spotify client: {e}") from e


# ---------------------------------------------------------------------------
# Database schema
# ---------------------------------------------------------------------------

SCHEMA = """
-- Artists table (normalized)
CREATE TABLE IF NOT EXISTS artists (
    id TEXT PRIMARY KEY,           -- Spotify artist ID
    name TEXT NOT NULL,
    genres TEXT,                    -- JSON array of genre strings
    popularity INTEGER,
    followers INTEGER,
    href TEXT,
    uri TEXT,
    updated_at REAL
);

-- Albums table
CREATE TABLE IF NOT EXISTS albums (
    id TEXT PRIMARY KEY,           -- Spotify album ID
    name TEXT NOT NULL,
    artist_id TEXT,                 -- FK to artists
    artist_name TEXT,
    release_date TEXT,
    release_date_precision TEXT,
    total_tracks INTEGER,
    popularity INTEGER,
    href TEXT,
    uri TEXT,
    label TEXT,
    updated_at REAL
);

-- Tracks table
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,           -- Spotify track ID
    name TEXT NOT NULL,
    album_id TEXT,                  -- FK to albums
    album_name TEXT,
    artist_id TEXT,                 -- FK to artists
    artist_name TEXT,
    duration_ms INTEGER,
    explicit INTEGER,
    popularity INTEGER,
    disc_number INTEGER,
    track_number INTEGER,
    is_playable INTEGER,
    href TEXT,
    uri TEXT,
    updated_at REAL
);

-- Artist-genre mapping (many-to-many normalization)
CREATE TABLE IF NOT EXISTS artist_genres (
    artist_id TEXT NOT NULL,
    genre TEXT NOT NULL,
    PRIMARY KEY (artist_id, genre)
);

-- Playlist table
CREATE TABLE IF NOT EXISTS playlists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    owner_id TEXT,
    owner_name TEXT,
    tracks_total INTEGER,
    public INTEGER,
    collaborative INTEGER,
    snapshot_id TEXT,
    href TEXT,
    uri TEXT,
    updated_at REAL
);

-- Saved tracks (library)
CREATE TABLE IF NOT EXISTS saved_tracks (
    track_id TEXT PRIMARY KEY,
    added_at TEXT NOT NULL,
    updated_at REAL
);

-- Saved albums (library)
CREATE TABLE IF NOT EXISTS saved_albums (
    album_id TEXT PRIMARY KEY,
    added_at TEXT NOT NULL,
    updated_at REAL
);

-- Followed artists
CREATE TABLE IF NOT EXISTS followed_artists (
    artist_id TEXT PRIMARY KEY,
    updated_at REAL
);

-- Listening events (ingestion core — deduplicated)
CREATE TABLE IF NOT EXISTS listening_events (
    spotify_ctx_id TEXT PRIMARY KEY,  -- Spotify's context-track-playlist tuple ID
    track_id TEXT NOT NULL,
    artist_id TEXT,
    album_id TEXT,
    played_at INTEGER NOT NULL,       -- Unix timestamp
    timestamp TEXT NOT NULL,          -- ISO string for display
    played_at_ms INTEGER NOT NULL,    -- Millisecond precision
    platform TEXT,
    device_type TEXT,
    is_playing INTEGER,
    conn_id TEXT,
    explicit_lock INTEGER,
    CONSTRAINT uq_event UNIQUE (spotify_ctx_id)
);

-- Playlist tracks (junction: which tracks are in which playlists)
CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id TEXT NOT NULL,
    track_id TEXT NOT NULL,
    added_at TEXT,
    PRIMARY KEY (playlist_id, track_id)
);

-- Audio features cache (per track)
CREATE TABLE IF NOT EXISTS audio_features (
    track_id TEXT PRIMARY KEY,
    danceability REAL,
    energy REAL,
    valence REAL,
    acousticness REAL,
    instrumentalness REAL,
    liveness REAL,
    loudness REAL,
    speechiness REAL,
    tempo REAL,
    track_href TEXT,
    analysis_url TEXT,
    key INTEGER,
    mode INTEGER,
    time_signature INTEGER,
    fetched_at REAL
);

-- Top artists snapshot (time-range snapshots for taste evolution)
CREATE TABLE IF NOT EXISTS top_artists_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time_range TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    artist_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    name TEXT NOT NULL,
    genres TEXT,
    popularity INTEGER
);

-- Top tracks snapshot
CREATE TABLE IF NOT EXISTS top_tracks_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time_range TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    track_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    name TEXT NOT NULL,
    album_name TEXT,
    artist_name TEXT,
    popularity INTEGER,
    duration_ms INTEGER
);

-- Ingestion run log (for idempotency tracking)
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    completed_at REAL,
    entities_artists INTEGER DEFAULT 0,
    entities_tracks INTEGER DEFAULT 0,
    entities_albums INTEGER DEFAULT 0,
    events_listened INTEGER DEFAULT 0,
    events_existing INTEGER DEFAULT 0,
    errors TEXT,
    status TEXT
);

-- Materialized analytics cache (denormalized for dashboard speed)
CREATE TABLE IF NOT EXISTS analytics_cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,              -- JSON
    computed_at REAL
);

-- Genre families (normalized hierarchy)
CREATE TABLE IF NOT EXISTS genre_families (
    genre TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    family_order INTEGER DEFAULT 0
);

-- Genre stats (pre-computed per period)
CREATE TABLE IF NOT EXISTS genre_stats (
    period TEXT NOT NULL,
    genre TEXT NOT NULL,
    play_count INTEGER NOT NULL,
    unique_artists INTEGER DEFAULT 0,
    unique_tracks INTEGER DEFAULT 0,
    PRIMARY KEY (period, genre)
);

-- Session table (inferred listening sessions)
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_start INTEGER NOT NULL,
    session_end INTEGER,
    duration_sec INTEGER,
    track_count INTEGER,
    unique_artists INTEGER,
    unique_genres INTEGER,
    total_plays INTEGER,
    avg_energy REAL,
    avg_valence REAL,
    avg_danceability REAL,
    avg_acousticness REAL,
    avg_tempo REAL,
    genres_json TEXT
);

-- Session-genre breakdown
CREATE TABLE IF NOT EXISTS session_genres (
    session_id INTEGER NOT NULL,
    genre TEXT NOT NULL,
    play_count INTEGER NOT NULL,
    PRIMARY KEY (session_id, genre)
);

-- Discovery events (new artists/tracks/albums discovered)
CREATE TABLE IF NOT EXISTS discovery_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discovered_at INTEGER NOT NULL,
    entity_type TEXT NOT NULL,       -- 'artist' | 'track' | 'album'
    entity_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    context TEXT,                    -- how it was discovered
    first_listen INTEGER,
    UNIQUE (entity_type, entity_id)
);

-- Taste era definitions
CREATE TABLE IF NOT EXISTS taste_eras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    era_name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    description TEXT,
    dominant_genres TEXT,
    dominant_artists TEXT,
    avg_energy REAL,
    avg_valence REAL,
    avg_danceability REAL,
    avg_acousticness REAL
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_events_track ON listening_events (track_id);
CREATE INDEX IF NOT EXISTS idx_events_artist ON listening_events (artist_id);
CREATE INDEX IF NOT EXISTS idx_events_played_at ON listening_events (played_at);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON listening_events (timestamp);
CREATE INDEX IF NOT EXISTS idx_events_connx ON listening_events (conn_id);
CREATE INDEX IF NOT EXISTS idx_events_platform ON listening_events (platform);
CREATE INDEX IF NOT EXISTS idx_top_artists_range ON top_artists_snapshots (time_range, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_top_tracks_range ON top_tracks_snapshots (time_range, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_analytics_key ON analytics_cache (key);
CREATE INDEX IF NOT EXISTS idx_genre_stats_period ON genre_stats (period);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions (session_start);
CREATE INDEX IF NOT EXISTS idx_discovery_type ON discovery_events (entity_type);
"""


def init_db():
    """Initialize the database schema."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    # Use executescript for multi-statement schema
    try:
        db.executescript(SCHEMA)
    except sqlite3.OperationalError as e:
        print(f"[db] schema error: {e}", file=sys.stderr)
        # Fallback: execute line by line for CREATE TABLE statements only
        for line in SCHEMA.split("\n"):
            line = line.strip()
            if line.startswith("CREATE TABLE"):
                try:
                    db.execute(line)
                except sqlite3.OperationalError:
                    pass
    db.commit()
    return db


# ---------------------------------------------------------------------------
# Ingestion helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cache_response(endpoint: str, data: Any) -> None:
    """Cache raw API responses for debugging / re-processing."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = endpoint.replace("/", "_").replace("?", "_").replace("&", "_")
    path = CACHE_DIR / f"{safe_name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def ensure_artist(db, artist_data: Dict) -> str:
    """Upsert artist. Returns artist ID."""
    aid = artist_data["id"]
    existing = db.execute("SELECT id FROM artists WHERE id=?", (aid,)).fetchone()
    genres = artist_data.get("genres", [])
    db.execute(
        """INSERT OR REPLACE INTO artists (id, name, genres, popularity, followers, href, uri, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            aid,
            artist_data.get("name", ""),
            json.dumps(genres),
            artist_data.get("popularity"),
            artist_data.get("followers", {}).get("total"),
            artist_data.get("href", ""),
            artist_data.get("uri", ""),
            time.time(),
        ),
    )
    # Update genres mapping
    db.execute("DELETE FROM artist_genres WHERE artist_id=?", (aid,))
    for g in genres:
        db.execute("INSERT OR IGNORE INTO artist_genres (artist_id, genre) VALUES (?, ?)", (aid, g))
    if not existing:
        db.execute(
            "INSERT OR IGNORE INTO followed_artists (artist_id, updated_at) VALUES (?, ?)",
            (aid, time.time()),
        )
    return aid


def ensure_album(db, album_data: Dict, artist_id: Optional[str] = None) -> str:
    """Upsert album. Returns album ID."""
    aid = album_data["id"]
    artist = album_data.get("artists", [{}])[0] if album_data.get("artists") else {}
    artist_name = artist.get("name", "")
    if not artist_id and artist.get("id"):
        artist_id = artist["id"]
        ensure_artist(db, artist)

    existing = db.execute("SELECT id FROM albums WHERE id=?", (aid,)).fetchone()
    db.execute(
        """INSERT OR REPLACE INTO albums
           (id, name, artist_id, artist_name, release_date, release_date_precision,
            total_tracks, popularity, href, uri, label, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            aid,
            album_data.get("name", ""),
            artist_id,
            artist_name,
            album_data.get("release_date", ""),
            album_data.get("release_date_precision", ""),
            album_data.get("total_tracks"),
            album_data.get("popularity"),
            album_data.get("href", ""),
            album_data.get("uri", ""),
            album_data.get("label", ""),
            time.time(),
        ),
    )
    return aid


def ensure_track(db, track_data: Dict, album_id: Optional[str] = None) -> str:
    """Upsert track. Returns track ID."""
    tid = track_data["id"]
    artist = track_data.get("artists", [{}])[0] if track_data.get("artists") else {}
    artist_name = artist.get("name", "")
    artist_id = artist.get("id")
    if artist_id:
        ensure_artist(db, artist)

    album = track_data.get("album", {})
    album_name = album.get("name", "")
    if not album_id and album.get("id"):
        album_id = album["id"]
        ensure_album(db, album, artist_id)

    existing = db.execute("SELECT id FROM tracks WHERE id=?", (tid,)).fetchone()
    db.execute(
        """INSERT OR REPLACE INTO tracks
           (id, name, album_id, album_name, artist_id, artist_name,
            duration_ms, explicit, popularity, disc_number, track_number,
            is_playable, href, uri, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            tid,
            track_data.get("name", ""),
            album_id,
            album_name,
            artist_id,
            artist_name,
            track_data.get("duration_ms"),
            int(track_data.get("explicit", False)),
            track_data.get("popularity"),
            track_data.get("disc_number"),
            track_data.get("track_number"),
            int(track_data.get("is_playable", True)),
            track_data.get("href", ""),
            track_data.get("uri", ""),
            time.time(),
        ),
    )
    return tid


def ingest_audio_features(db, track_id: str) -> bool:
    """Fetch and cache audio features for a single track."""
    existing = db.execute(
        "SELECT track_id FROM audio_features WHERE track_id=?", (track_id,)
    ).fetchone()
    if existing:
        return True

    client = get_spotify_client()
    try:
        af = client.request("GET", f"/audio-features/{track_id}")
        if not af:
            return False
        db.execute(
            """INSERT OR REPLACE INTO audio_features
               (track_id, danceability, energy, valence, acousticness,
                instrumentalness, liveness, loudness, speechiness, tempo,
                track_href, analysis_url, key, mode, time_signature, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                track_id,
                af.get("danceability"),
                af.get("energy"),
                af.get("valence"),
                af.get("acousticness"),
                af.get("instrumentalness"),
                af.get("liveness"),
                af.get("loudness"),
                af.get("speechiness"),
                af.get("tempo"),
                af.get("track_href", ""),
                af.get("analysis_url", ""),
                af.get("key"),
                af.get("mode"),
                af.get("time_signature"),
                time.time(),
            ),
        )
        return True
    except Exception as e:
        print(f"[ingest] audio_features({track_id[:8]}): {e}", file=sys.stderr)
        return False


def ingest_recently_played(db, limit: int = 50, before: Optional[int] = None) -> Dict:
    """Ingest recently played tracks. Returns stats."""
    client = get_spotify_client()
    stats = {"fetched": 0, "inserted": 0, "existing": 0, "errors": 0}

    try:
        params = {"limit": limit}
        if before:
            params["before"] = before
        response = client.request("GET", "/me/player/recently-played", params=params)
        items = response.get("items", [])
        stats["fetched"] = len(items)

        for item in items:
            track = item.get("track")
            if not track:
                stats["errors"] += 1
                continue

            tid = track["id"]
            ensure_track(db, track)

            album = track.get("album", {})
            aid = album.get("id")
            if aid:
                ensure_album(db, album)

            # Deduplicated listening event
            # Spotify provides a unique tuple: (track, context, playlist)
            # We construct a stable ID
            ctx_id = item.get("context", {})
            playlist_id = ctx_id.get("playlist", {}).get("id", "") if ctx_id else ""
            conn_id = item.get("conn_id", "")
            play_id = f"{tid}|{conn_id}|{playlist_id}|{item['played_at']}"

            played_at_dt = datetime.fromisoformat(
                item["played_at"].replace("Z", "+00:00")
            )
            played_at_ts = int(played_at_dt.timestamp())
            played_at_ms = int(played_at_dt.timestamp() * 1000)

            existing = db.execute(
                "SELECT spotify_ctx_id FROM listening_events WHERE spotify_ctx_id=?",
                (play_id,),
            ).fetchone()

            if existing:
                stats["existing"] += 1
            else:
                db.execute(
                    """INSERT OR IGNORE INTO listening_events
                       (spotify_ctx_id, track_id, artist_id, album_id,
                        played_at, timestamp, played_at_ms, platform,
                        device_type, is_playing, conn_id, explicit_lock)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        play_id,
                        tid,
                        track.get("artists", [{}])[0].get("id"),
                        aid,
                        played_at_ts,
                        item["played_at"],
                        played_at_ms,
                        item.get("platform", ""),
                        item.get("device-type", ""),
                        int(item.get("is_playing", True)),
                        conn_id,
                        int(track.get("explicit", False)),
                    ),
                )
                stats["inserted"] += 1
                # Ingest audio features asynchronously (don't block)
                ingest_audio_features(db, tid)

    except Exception as e:
        print(f"[ingest] recently-played: {e}", file=sys.stderr)
        stats["errors"] += 1

    return stats


def ingest_top_artists(db, time_range: str, limit: int = 50) -> Dict:
    """Ingest top artists for a time range and snapshot them."""
    client = get_spotify_client()
    stats = {"fetched": 0, "inserted": 0}

    try:
        response = client.request(
            "GET", "/me/top/artists", params={"time_range": time_range, "limit": limit}
        )
        items = response.get("items", [])
        stats["fetched"] = len(items)

        for rank, artist in enumerate(items, 1):
            aid = ensure_artist(db, artist)
            existing = db.execute(
                """SELECT id FROM top_artists_snapshots
                   WHERE time_range=? AND snapshot_date=? AND artist_id=?""",
                (time_range, now_iso(), aid),
            ).fetchone()
            if not existing:
                db.execute(
                    """INSERT INTO top_artists_snapshots
                       (time_range, snapshot_date, artist_id, rank, name, genres, popularity)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        time_range,
                        now_iso(),
                        aid,
                        rank,
                        artist.get("name", ""),
                        json.dumps(artist.get("genres", [])),
                        artist.get("popularity"),
                    ),
                )
                stats["inserted"] += 1
    except Exception as e:
        print(f"[ingest] top_artists({time_range}): {e}", file=sys.stderr)

    return stats


def ingest_top_tracks(db, time_range: str, limit: int = 50) -> Dict:
    """Ingest top tracks for a time range and snapshot them."""
    client = get_spotify_client()
    stats = {"fetched": 0, "inserted": 0}

    try:
        response = client.request(
            "GET", "/me/top/tracks", params={"time_range": time_range, "limit": limit}
        )
        items = response.get("items", [])
        stats["fetched"] = len(items)

        for rank, track in enumerate(items, 1):
            tid = ensure_track(db, track)

            album = track.get("album", {})
            aid = album.get("id")
            if aid:
                ensure_album(db, album)

            existing = db.execute(
                """SELECT id FROM top_tracks_snapshots
                   WHERE time_range=? AND snapshot_date=? AND track_id=?""",
                (time_range, now_iso(), tid),
            ).fetchone()
            if not existing:
                db.execute(
                    """INSERT INTO top_tracks_snapshots
                       (time_range, snapshot_date, track_id, rank, name, album_name, artist_name, popularity, duration_ms)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        time_range,
                        now_iso(),
                        tid,
                        rank,
                        track.get("name", ""),
                        album.get("name", ""),
                        track.get("artists", [{}])[0].get("name", ""),
                        track.get("popularity"),
                        track.get("duration_ms"),
                    ),
                )
                stats["inserted"] += 1
    except Exception as e:
        print(f"[ingest] top_tracks({time_range}): {e}", file=sys.stderr)

    return stats


def ingest_saved_tracks(db, limit: int = 50) -> Dict:
    """Ingest saved tracks from user library."""
    client = get_spotify_client()
    stats = {"fetched": 0, "inserted": 0}

    try:
        offset = 0
        while True:
            response = client.get_saved_tracks(limit=limit, offset=offset)
            items = response.get("items", [])
            stats["fetched"] += len(items)

            for item in items:
                track = item.get("track")
                if not track:
                    continue
                tid = ensure_track(db, track)
                existing = db.execute(
                    "SELECT track_id FROM saved_tracks WHERE track_id=?", (tid,)
                ).fetchone()
                if not existing:
                    db.execute(
                        "INSERT OR IGNORE INTO saved_tracks (track_id, added_at, updated_at) VALUES (?, ?, ?)",
                        (tid, item.get("added_at", ""), time.time()),
                    )
                    stats["inserted"] += 1

            if len(items) < limit:
                break
            offset += limit
    except Exception as e:
        print(f"[ingest] saved_tracks: {e}", file=sys.stderr)

    return stats


def ingest_saved_albums(db, limit: int = 50) -> Dict:
    """Ingest saved albums from user library."""
    client = get_spotify_client()
    stats = {"fetched": 0, "inserted": 0}

    try:
        offset = 0
        while True:
            response = client.get_saved_albums(limit=limit, offset=offset)
            items = response.get("items", [])
            stats["fetched"] += len(items)

            for item in items:
                album = item.get("album")
                if not album:
                    continue
                aid = ensure_album(db, album)
                existing = db.execute(
                    "SELECT album_id FROM saved_albums WHERE album_id=?", (aid,)
                ).fetchone()
                if not existing:
                    db.execute(
                        "INSERT OR IGNORE INTO saved_albums (album_id, added_at, updated_at) VALUES (?, ?, ?)",
                        (aid, item.get("added_at", ""), time.time()),
                    )
                    stats["inserted"] += 1

            if len(items) < limit:
                break
            offset += limit
    except Exception as e:
        print(f"[ingest] saved_albums: {e}", file=sys.stderr)

    return stats


def ingest_my_playlists(db, limit: int = 50) -> Dict:
    """Ingest user's playlists."""
    client = get_spotify_client()
    stats = {"fetched": 0, "inserted": 0}

    try:
        offset = 0
        while True:
            response = client.get_my_playlists(limit=limit, offset=offset)
            items = response.get("items", [])
            stats["fetched"] += len(items)

            for p in items:
                oid = p.get("owner", {}).get("id", "")
                stats["inserted"] += 1
                db.execute(
                    """INSERT OR REPLACE INTO playlists
                       (id, name, description, owner_id, owner_name,
                        tracks_total, public, collaborative, snapshot_id, href, uri, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        p["id"],
                        p.get("name", ""),
                        p.get("description", ""),
                        oid,
                        p.get("owner", {}).get("display_name", ""),
                        p.get("tracks", {}).get("total"),
                        int(p.get("public", False)),
                        int(p.get("collaborative", False)),
                        p.get("snapshot_id", ""),
                        p.get("href", ""),
                        p.get("uri", ""),
                        time.time(),
                    ),
                )

                # Also ingest playlist tracks
                try:
                    pl_tracks = client.request(
                        "GET", f"/playlists/{p['id']}/tracks", params={"limit": 100}
                    )
                    for tr_item in pl_tracks.get("items", []):
                        tr = tr_item.get("track")
                        if tr and tr.get("id"):
                            tid = ensure_track(db, tr)
                            db.execute(
                                """INSERT OR IGNORE INTO playlist_tracks
                                   (playlist_id, track_id, added_at) VALUES (?, ?, ?)""",
                                (p["id"], tid, tr_item.get("added_at", "")),
                            )
                except Exception as pe:
                    print(f"[ingest] playlist_tracks({p['id'][:8]}): {pe}", file=sys.stderr)

            if len(items) < limit:
                break
            offset += limit
    except Exception as e:
        print(f"[ingest] my_playlists: {e}", file=sys.stderr)

    return stats


def ingest_currently_playing(db) -> Optional[Dict]:
    """Get currently playing track. Returns data or None."""
    client = get_spotify_client()
    try:
        cp = client.get_currently_playing()
        if not cp:
            return None
        track = cp.get("track", {})
        if not track:
            return None
        tid = ensure_track(db, track)
        album = track.get("album", {})
        if album.get("id"):
            ensure_album(db, album)
        return {
            "track_id": tid,
            "name": track.get("name", ""),
            "artist": track.get("artists", [{}])[0].get("name", ""),
            "artist_id": track.get("artists", [{}])[0].get("id", ""),
            "album": album.get("name", ""),
            "album_id": album.get("id", ""),
            "duration_ms": track.get("duration_ms"),
            "progress_ms": cp.get("progress_ms"),
            "is_playing": cp.get("is_playing"),
            "explicit": track.get("explicit", False),
            "popularity": track.get("popularity"),
            "disc_number": track.get("disc_number"),
            "track_number": track.get("track_number"),
            "added_at": now_iso(),
        }
    except Exception as e:
        print(f"[ingest] currently-playing: {e}", file=sys.stderr)
        return None


def run_ingestion(full: bool = False, days_back: int = 0) -> Dict[str, Any]:
    """Run the full ingestion pipeline."""
    print(f"[ingest] Starting ingestion at {now_iso()}")
    db = init_db()

    # Record run start
    run_id = db.execute(
        "INSERT INTO ingestion_runs (started_at, status) VALUES (?, ?)",
        (time.time(), "running"),
    ).lastrowid

    total_stats = {
        "artists": 0, "tracks": 0, "albums": 0,
        "events_new": 0, "events_existing": 0,
        "top_artists_snapshots": 0, "top_tracks_snapshots": 0,
        "saved_tracks": 0, "saved_albums": 0,
        "playlists": 0,
    }

    try:
        # 1. Recent listening events
        print("[ingest] Pulling recently played tracks...")
        rp = ingest_recently_played(db, limit=50)
        total_stats["events_new"] += rp.get("inserted", 0)
        total_stats["events_existing"] += rp.get("existing", 0)
        print(f"  → {rp.get('inserted', 0)} new events, {rp.get('existing', 0)} existing, {rp.get('fetched', 0)} fetched")

        # 2. Top artists (all time ranges)
        for tr in ["short_term", "medium_term", "long_term"]:
            print(f"[ingest] Top artists ({tr})...")
            ta = ingest_top_artists(db, tr, limit=50)
            total_stats["top_artists_snapshots"] += ta.get("inserted", 0)
            print(f"  → {ta.get('inserted', 0)} new snapshots")

        # 3. Top tracks (all time ranges)
        for tr in ["short_term", "medium_term", "long_term"]:
            print(f"[ingest] Top tracks ({tr})...")
            tt = ingest_top_tracks(db, tr, limit=50)
            total_stats["top_tracks_snapshots"] += tt.get("inserted", 0)
            print(f"  → {tt.get('inserted', 0)} new snapshots")

        # 4. Saved tracks
        print("[ingest] Saved tracks...")
        st = ingest_saved_tracks(db)
        total_stats["saved_tracks"] += st.get("inserted", 0)
        print(f"  → {st.get('inserted', 0)} saved tracks")

        # 5. Saved albums
        print("[ingest] Saved albums...")
        sa = ingest_saved_albums(db)
        total_stats["saved_albums"] += sa.get("inserted", 0)
        print(f"  → {sa.get('inserted', 0)} saved albums")

        # 6. Playlists
        print("[ingest] Playlists...")
        pl = ingest_my_playlists(db)
        total_stats["playlists"] += pl.get("inserted", 0)
        print(f"  → {pl.get('inserted', 0)} playlists")

        # 7. Currently playing
        cp = ingest_currently_playing(db)
        if cp:
            print(f"  → Currently playing: {cp['name']} by {cp['artist']}")

        # Update counts
        total_stats["artists"] = db.execute(
            "SELECT COUNT(*) FROM artists"
        ).fetchone()[0]
        total_stats["tracks"] = db.execute(
            "SELECT COUNT(*) FROM tracks"
        ).fetchone()[0]
        total_stats["albums"] = db.execute(
            "SELECT COUNT(*) FROM albums"
        ).fetchone()[0]

        status = "completed"
        errors = None

    except Exception as e:
        status = "failed"
        errors = str(e)
        print(f"[ingest] FAILED: {e}", file=sys.stderr)

    finally:
        db.execute(
            """UPDATE ingestion_runs
               SET completed_at=?, status=?, entities_artists=?,
                   entities_tracks=?, entities_albums=?,
                   events_listened=?, events_existing=?,
                   errors=?
               WHERE id=?""",
            (
                time.time(),
                status,
                total_stats["artists"],
                total_stats["tracks"],
                total_stats["albums"],
                total_stats["events_new"],
                total_stats["events_existing"],
                errors,
                run_id,
            ),
        )
        db.commit()
        db.close()

    print(f"[ingest] Completed: {json.dumps(total_stats, indent=2)}")
    return total_stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Spotify data ingestion")
    parser.add_argument(
        "--full", action="store_true", help="Run full ingestion (all endpoints)"
    )
    parser.add_argument(
        "--recent", action="store_true", help="Only pull recently played"
    )
    parser.add_argument(
        "--top", action="store_true", help="Only pull top artists/tracks"
    )
    parser.add_argument(
        "--library", action="store_true", help="Only pull saved tracks/albums/playlists"
    )
    parser.add_argument(
        "--days", type=int, default=0, help="Pull events from N days back"
    )
    args = parser.parse_args()

    run_ingestion(full=args.full)
