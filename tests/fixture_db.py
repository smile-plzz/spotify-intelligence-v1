"""Build a small, self-contained warehouse database for the test suite.

The production `spotify_data.db` is gitignored (it holds personal listening
history), so CI needs its own.  The schema here mirrors the columns the
dashboard endpoints actually query — if an endpoint starts using a new column,
its test fails here first.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SCHEMA = """
CREATE TABLE artists (
    id TEXT PRIMARY KEY,
    name TEXT,
    genres TEXT,
    popularity INTEGER
);
CREATE TABLE artist_genres (
    artist_id TEXT,
    genre TEXT
);
CREATE TABLE albums (
    id TEXT PRIMARY KEY,
    name TEXT,
    artist_name TEXT,
    release_date TEXT,
    total_tracks INTEGER,
    popularity INTEGER
);
CREATE TABLE tracks (
    id TEXT PRIMARY KEY,
    name TEXT,
    artist_id TEXT,
    artist_name TEXT,
    album_id TEXT,
    album_name TEXT,
    duration_ms INTEGER,
    popularity INTEGER,
    explicit INTEGER,
    disc_number INTEGER,
    track_number INTEGER
);
CREATE TABLE audio_features (
    track_id TEXT PRIMARY KEY,
    danceability REAL,
    energy REAL,
    valence REAL,
    acousticness REAL,
    instrumentalness REAL,
    speechiness REAL,
    loudness REAL,
    tempo REAL
);
CREATE TABLE listening_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT,
    artist_id TEXT,
    album_id TEXT,
    played_at INTEGER,
    timestamp INTEGER
);
CREATE TABLE saved_tracks (
    track_id TEXT,
    added_at TEXT
);
CREATE TABLE saved_albums (
    album_id TEXT,
    added_at TEXT
);
CREATE TABLE playlists (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    tracks_total INTEGER,
    public INTEGER,
    collaborative INTEGER
);
CREATE TABLE top_artists_snapshots (
    artist_id TEXT,
    time_range TEXT,
    rank INTEGER
);
CREATE TABLE top_tracks_snapshots (
    track_id TEXT,
    time_range TEXT,
    rank INTEGER
);
CREATE TABLE analytics_cache (
    key TEXT PRIMARY KEY,
    value TEXT,
    computed_at REAL
);
"""

# (artist_id, name, popularity, genres)
ARTISTS = [
    ("ar1", "Bob Dylan", 78, ["folk rock", "singer-songwriter"]),
    ("ar2", "Taylor Swift", 98, ["pop", "country pop"]),
    ("ar3", "Death Cab for Cutie", 65, ["indie rock", "alternative rock"]),
    ("ar4", "Ben Folds", 55, ["pop rock", "piano"]),
    ("ar5", "Nirvana", 82, ["grunge", "hard rock"]),
]

# (track_id, artist_id, name, plays, explicit, audio-feature profile)
TRACKS = [
    ("tr1", "ar3", "Soul Meets Body", 3, 0, (0.55, 0.62, 0.48, 0.21, 0.02, 0.04, -6.1, 118.0)),
    ("tr2", "ar1", "The Hard Way", 2, 0, (0.41, 0.38, 0.35, 0.72, 0.01, 0.03, -9.4, 96.0)),
    ("tr3", "ar4", "Rockin' the Suburbs", 2, 1, (0.63, 0.71, 0.66, 0.14, 0.00, 0.06, -5.2, 132.0)),
    ("tr4", "ar1", "Like a Rolling Stone", 3, 0, (0.47, 0.55, 0.52, 0.58, 0.01, 0.04, -8.0, 108.0)),
    ("tr5", "ar2", "All Too Well", 4, 0, (0.58, 0.49, 0.30, 0.44, 0.00, 0.03, -7.3, 93.0)),
    ("tr6", "ar5", "Come as You Are", 1, 0, (0.51, 0.84, 0.42, 0.05, 0.03, 0.05, -4.1, 120.0)),
]

# The warehouse is small on purpose. Spotify's snapshot tables list an artist
# the warehouse has never seen, so the list-padding path stays exercised.
UNPLAYED_ARTIST = ("ar_unplayed", "Never Played", 10)


def _seed_rows(db, now: int) -> None:
    """Insert the warehouse rows. `now` anchors the listening events."""
    for artist_id, name, popularity, genres in ARTISTS:
        db.execute(
            "INSERT INTO artists VALUES (?,?,?,?)",
            (artist_id, name, ",".join(genres), popularity),
        )
        for genre in genres:
            db.execute("INSERT INTO artist_genres VALUES (?,?)", (artist_id, genre))
    db.execute("INSERT INTO artists VALUES (?,?,?,?)", (*UNPLAYED_ARTIST[:2], "", UNPLAYED_ARTIST[2]))

    artist_names = {a[0]: a[1] for a in ARTISTS}

    # One album per artist, so the album joins have something to find.
    for artist_id, name, popularity, _genres in ARTISTS:
        db.execute(
            "INSERT INTO albums VALUES (?,?,?,?,?,?)",
            (f"al{artist_id}", f"{name} — Greatest", name, "2020-01-01", 12, popularity),
        )

    # Plays walk backwards from `now` in 3-hour steps, so they land across
    # several hours and weekdays and always look recent to the analytics
    # engine's date-range maths.
    offset = 0
    for position, (track_id, artist_id, name, plays, explicit, features) in enumerate(TRACKS, start=1):
        album_id = f"al{artist_id}"
        db.execute(
            "INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                track_id,
                name,
                artist_id,
                artist_names[artist_id],
                album_id,
                f"{artist_names[artist_id]} — Greatest",
                215_000,
                60,
                explicit,
                1,
                position,
            ),
        )
        db.execute(
            "INSERT INTO audio_features VALUES (?,?,?,?,?,?,?,?,?)", (track_id, *features)
        )
        for _ in range(plays):
            offset += 3 * 3600
            played_at = now - offset
            db.execute(
                "INSERT INTO listening_events (track_id, artist_id, album_id, played_at, timestamp)"
                " VALUES (?,?,?,?,?)",
                (track_id, artist_id, album_id, played_at, played_at),
            )
        db.execute("INSERT INTO saved_tracks VALUES (?,?)", (track_id, "2026-01-01T00:00:00Z"))

    for artist_id, *_ in ARTISTS:
        db.execute(
            "INSERT INTO saved_albums VALUES (?,?)", (f"al{artist_id}", "2026-01-01T00:00:00Z")
        )

    for i in range(3):
        db.execute(
            "INSERT INTO playlists VALUES (?,?,?,?,?,?)",
            (f"pl{i}", f"Playlist {i}", f"Description {i}", 20 + i, 1, 0),
        )

    for rank, (artist_id, *_rest) in enumerate(ARTISTS, start=1):
        db.execute(
            "INSERT INTO top_artists_snapshots VALUES (?,?,?)", (artist_id, "long_term", rank)
        )
    db.execute(
        "INSERT INTO top_artists_snapshots VALUES (?,?,?)", (UNPLAYED_ARTIST[0], "long_term", 99)
    )

    for rank, (track_id, *_rest) in enumerate(TRACKS, start=1):
        db.execute(
            "INSERT INTO top_tracks_snapshots VALUES (?,?,?)", (track_id, "long_term", rank)
        )


def _cache_analytics(path: str) -> None:
    """Run the real analytics engine over the fixture and cache its output.

    The endpoints that read `full_intelligence` are only as well tested as the
    blob they read, so the fixture uses whatever analytics.py actually
    produces rather than a hand-written approximation that can drift from it.
    """
    import analytics

    original = analytics.DB_PATH
    analytics.DB_PATH = path
    try:
        results = analytics.run_all_analytics()
        analytics.save_analytics_cache(results)
    finally:
        analytics.DB_PATH = original


def build_fixture_db(path: str, now: int | None = None) -> str:
    """Create a seeded warehouse DB at `path` and return the path."""
    if now is None:
        now = int(time.time())

    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    _seed_rows(db, now)
    db.commit()
    db.close()

    _cache_analytics(path)
    return path
