"""Build a small, self-contained warehouse database for the test suite.

The production `spotify_data.db` is gitignored (it holds personal listening
history), so CI needs its own.  The schema here mirrors the columns the
dashboard endpoints actually query — if an endpoint starts using a new column,
its test fails here first.
"""

from __future__ import annotations

import json
import sqlite3

SCHEMA = """
CREATE TABLE artists (
    id TEXT PRIMARY KEY,
    name TEXT,
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
    popularity INTEGER
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
    value TEXT
);
"""

# (artist_id, name, popularity, genres, play_count)
ARTISTS = [
    ("ar1", "Bob Dylan", 78, ["folk rock", "singer-songwriter"], 5),
    ("ar2", "Taylor Swift", 98, ["pop", "country pop"], 4),
    ("ar3", "Death Cab for Cutie", 65, ["indie rock", "alternative rock"], 3),
    ("ar4", "Ben Folds", 55, ["pop rock", "piano"], 2),
    ("ar5", "Nirvana", 82, ["grunge", "hard rock"], 1),
]

# (track_id, artist_id, name, plays)
TRACKS = [
    ("tr1", "ar3", "Soul Meets Body", 3),
    ("tr2", "ar1", "The Hard Way", 2),
    ("tr3", "ar4", "Rockin' the Suburbs", 2),
    ("tr4", "ar1", "Like a Rolling Stone", 3),
    ("tr5", "ar2", "All Too Well", 4),
    ("tr6", "ar5", "Come as You Are", 1),
]

FULL_INTELLIGENCE = {
    "findings": [{"title": "Rock dominates", "detail": "Rock is 40% of plays."}],
    "anomalies": {"findings": [{"title": "Late-night spike", "detail": "2am plays up."}]},
    "listener_archetype": {
        "archetype": "The Explorer",
        "archetype_key": "explorer",
        "archetype_signals": [
            {"signal": "artist_variety", "description": "You spread plays across many artists."}
        ],
        "supporting_metrics": {"unique_artists": 5},
    },
    "audio_characteristics": {
        "audio_characteristics": {
            "avg_valence": 0.42,
            "avg_energy": 0.61,
            "avg_acousticness": 0.28,
            "avg_danceability": 0.5,
        }
    },
    "explicit_content": {"explicit_percentage": 12.5},
    "taste_evolution": {
        "timeline": [
            {
                "period": "2026-07",
                "plays": 7,
                "unique_tracks": 5,
                "unique_artists": 4,
                "top_genre": "folk rock",
            },
            {
                "period": "2026-08",
                "plays": 8,
                "unique_tracks": 6,
                "unique_artists": 5,
                "top_genre": "pop",
            },
        ]
    },
    "time_of_day": {
        "hourly_breakdown": {"14": 6, "22": 9},
        "daily_breakdown": {"Monday": 5, "Friday": 10},
        "time_of_day": {"afternoon": 6, "night": 9},
        "peak_hour": 22,
        "peak_day": "Friday",
    },
    "listening_frequency": {"active_days": ["Monday", "Friday"]},
}


def build_fixture_db(path: str) -> str:
    """Create a seeded warehouse DB at `path` and return the path."""
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)

    for artist_id, name, popularity, genres, _plays in ARTISTS:
        db.execute("INSERT INTO artists VALUES (?,?,?)", (artist_id, name, popularity))
        for genre in genres:
            db.execute("INSERT INTO artist_genres VALUES (?,?)", (artist_id, genre))

    artist_names = {a[0]: a[1] for a in ARTISTS}

    # One album per artist, named after them, so album joins have something.
    for artist_id, name, popularity, _genres, _plays in ARTISTS:
        db.execute(
            "INSERT INTO albums VALUES (?,?,?,?,?,?)",
            (f"al{artist_id}", f"{name} — Greatest", name, "2020-01-01", 12, popularity),
        )

    played_at = 1_750_000_000
    for track_id, artist_id, name, plays in TRACKS:
        album_id = f"al{artist_id}"
        db.execute(
            "INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?)",
            (
                track_id,
                name,
                artist_id,
                artist_names[artist_id],
                album_id,
                f"{artist_names[artist_id]} — Greatest",
                215_000,
                60,
            ),
        )
        for _ in range(plays):
            played_at += 3600
            db.execute(
                "INSERT INTO listening_events (track_id, artist_id, album_id, played_at, timestamp)"
                " VALUES (?,?,?,?,?)",
                (track_id, artist_id, album_id, played_at, played_at),
            )
        db.execute("INSERT INTO saved_tracks VALUES (?,?)", (track_id, "2026-01-01T00:00:00Z"))

    for artist_id, *_ in ARTISTS:
        db.execute("INSERT INTO saved_albums VALUES (?,?)", (f"al{artist_id}", "2026-01-01T00:00:00Z"))

    for i in range(3):
        db.execute(
            "INSERT INTO playlists VALUES (?,?,?,?,?,?)",
            (f"pl{i}", f"Playlist {i}", f"Description {i}", 20 + i, 1, 0),
        )

    # Snapshots deliberately overlap the plays only partially — this is the
    # condition that used to make every play count read 0.
    for rank, (artist_id, *_rest) in enumerate(ARTISTS, start=1):
        db.execute("INSERT INTO top_artists_snapshots VALUES (?,?,?)", (artist_id, "long_term", rank))
    db.execute("INSERT INTO top_artists_snapshots VALUES (?,?,?)", ("ar_unplayed", "long_term", 99))
    db.execute("INSERT INTO artists VALUES (?,?,?)", ("ar_unplayed", "Never Played", 10))

    for rank, (track_id, *_rest) in enumerate(TRACKS, start=1):
        db.execute("INSERT INTO top_tracks_snapshots VALUES (?,?,?)", (track_id, "long_term", rank))

    db.execute(
        "INSERT INTO analytics_cache VALUES (?,?)",
        ("full_intelligence", json.dumps(FULL_INTELLIGENCE)),
    )

    db.commit()
    db.close()
    return path
