#!/usr/bin/env python3
"""
Spotify Intelligence Dashboard
Flask-based dashboard serving analytics from the data warehouse.
Dark aesthetic, Chart.js visualizations, mobile-responsive.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent
DB_PATH = REPO_ROOT / "spotify_data.db"
STATIC_DIR = REPO_ROOT / "static"
TEMPLATE_DIR = REPO_ROOT / "templates"

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    template_folder=str(TEMPLATE_DIR),
)
CORS(app)

app.config["JSON_SORT_KEYS"] = False
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False


def get_db() -> sqlite3.Connection:
    """Open a new database connection for the current request context.

    Uses ``DB_PATH`` when set (e.g. by tests); otherwise resolves from the
    current working directory with a fallback to the file next to this module.
    The SQLite database must be opened with an absolute path in this environment.
    """
    path: str | None = None
    if DB_PATH is not None:
        path = str(DB_PATH)
    if path is None:
        path = os.path.join(os.getcwd(), "spotify_data.db")
        if not os.path.exists(path):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spotify_data.db")
    if not os.path.exists(path):
        raise FileNotFoundError(f"spotify_data.db not found at {path}")
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def db_cache(key: str) -> str:
    """Return the raw JSON string cached under `key` in analytics_cache.

    Used by stub endpoints to re-serve pre-computed intelligence without
    re-querying the DB.  Returns an empty string when the key is missing.
    """
    try:
        db = get_db()
        row = db.execute(
            "SELECT value FROM analytics_cache WHERE key=?", (key,),
        ).fetchone()
        if row:
            return row["value"]
        return ""
    except Exception:
        return ""


HERMES_PATH = os.getenv(
    "HERMES_AGENT_PATH", r"C:\Users\ismai\AppData\Local\hermes\hermes-agent"
)


def spotify_client():
    """Return a live SpotifyClient, or None when one cannot be built.

    The client lives in the hermes agent tree rather than this repo, so it is
    absent on any machine but the one that ingests.  Callers treat None as
    "not connected" rather than as a failure.
    """
    try:
        if HERMES_PATH not in sys.path:
            sys.path.insert(0, HERMES_PATH)
        from plugins.spotify.client import SpotifyClient

        return SpotifyClient()
    except Exception:
        return None


def _plays_by(breakdown: Dict[str, Any]) -> Dict[str, int]:
    """Flatten an analytics breakdown to `{bucket: plays}`.

    analytics.py returns `{"14": {"plays": 6, "unique_tracks": 4}}`; the
    dashboard charts want a plain count per bucket.
    """
    flat = {}
    for bucket, value in (breakdown or {}).items():
        if isinstance(value, dict):
            flat[bucket] = value.get("plays", 0)
        else:
            flat[bucket] = value or 0
    return flat


def _top_genre_of(period: Dict[str, Any]) -> Any:
    """Name of the most-played genre in a taste-evolution period."""
    genres = period.get("top_genres") or []
    if genres and isinstance(genres[0], dict):
        return genres[0].get("genre")
    return period.get("top_genre")


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.route("/api/summary")
def api_summary():
    """Overview summary for the dashboard landing page."""
    db = get_db()

    total = db.execute(
        "SELECT COUNT(*) FROM listening_events"
    ).fetchone()[0]

    artists = db.execute(
        "SELECT COUNT(DISTINCT artist_id) FROM listening_events"
    ).fetchone()[0]

    tracks = db.execute(
        "SELECT COUNT(DISTINCT track_id) FROM listening_events"
    ).fetchone()[0]

    albums = db.execute(
        "SELECT COUNT(DISTINCT album_id) FROM listening_events WHERE album_id IS NOT NULL"
    ).fetchone()[0]

    saved_tracks = db.execute("SELECT COUNT(*) FROM saved_tracks").fetchone()[0]
    saved_albums = db.execute("SELECT COUNT(*) FROM saved_albums").fetchone()[0]
    playlists = db.execute("SELECT COUNT(*) FROM playlists").fetchone()[0]

    # Currently playing
    try:
        client = spotify_client()
        cp = client.get_currently_playing() if client else None
        currently_playing = None
        if cp and not cp.get("empty"):
            track = cp.get("track", {})
            if track:
                currently_playing = {
                    "name": track.get("name", ""),
                    "artist": track.get("artists", [{}])[0].get("name", ""),
                    "album": track.get("album", {}).get("name", ""),
                    "progress_ms": cp.get("progress_ms"),
                    "duration_ms": track.get("duration_ms"),
                    "is_playing": cp.get("is_playing"),
                    "explicit": track.get("explicit", False),
                    "popularity": track.get("popularity"),
                }
    except Exception:
        currently_playing = None

    # Last played
    last_played = db.execute(
        "SELECT le.played_at, t.name as track_name, a.name as artist_name, al.name as album_name "
        "FROM listening_events le "
        "JOIN tracks t ON le.track_id = t.id "
        "LEFT JOIN artists a ON t.artist_id = a.id "
        "LEFT JOIN albums al ON le.album_id = al.id "
        "ORDER BY le.played_at DESC LIMIT 1"
    ).fetchone()

    db.close()

    return jsonify(
        {
            "total_plays": total,
            "unique_artists": artists,
            "unique_tracks": tracks,
            "unique_albums": albums,
            "saved_tracks": saved_tracks,
            "saved_albums": saved_albums,
            "playlists": playlists,
            "currently_playing": currently_playing,
            "last_played": {
                "played_at": last_played["played_at"] if last_played else None,
                "track": last_played["track_name"] if last_played else None,
                "artist": last_played["artist_name"] if last_played else None,
                "album": last_played["album_name"] if last_played else None,
            }
            if last_played
            else None,
        }
    )


@app.route("/api/genres")
def api_genres():
    """Genre data for the genre universe visualization."""
    db = get_db()

    genre_data = db.execute(
        """SELECT ag.genre, COUNT(DISTINCT le.track_id) as track_count,
                COUNT(*) as play_count,
                COUNT(DISTINCT t.artist_id) as artist_count
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           JOIN artist_genres ag ON t.artist_id = ag.artist_id
           GROUP BY ag.genre
           ORDER BY play_count DESC"""
    ).fetchall()

    genres = []
    for g in genre_data:
        genres.append(
            {
                "genre": g["genre"],
                "play_count": g["play_count"],
                "track_count": g["track_count"],
                "artist_count": g["artist_count"],
                "size": g["play_count"],
            }
        )

    # Genre families
    families = {}
    for g in genres:
        family = normalize_genre(g["genre"])
        if family not in families:
            families[family] = {
                "name": family,
                "genres": [],
                "total_plays": 0,
                "total_tracks": 0,
            }
        families[family]["genres"].append(g["genre"])
        families[family]["total_plays"] += g["play_count"]
        families[family]["total_tracks"] += g["track_count"]

    family_list = sorted(
        families.values(), key=lambda f: f["total_plays"], reverse=True
    )

    db.close()
    return jsonify(
        {
            "genres": genres,
            "families": family_list,
            "total_genres": len(genres),
        }
    )


@app.route("/api/top-artists")
def api_top_artists():
    """Top artists, ranked by actual plays in the local warehouse.

    The Spotify `top_artists_snapshots` table only carries API rank data and
    barely overlaps the plays we have recorded, so ranking off it left most
    rows at 0 plays.  We aggregate `listening_events` instead and fall back to
    the snapshots for names only when the warehouse is too thin to fill a list.
    """
    db = get_db()

    played = db.execute(
        """SELECT a.name, a.popularity, GROUP_CONCAT(DISTINCT ag.genre) as genres,
                p.play_count, p.unique_tracks
           FROM (SELECT artist_id,
                        COUNT(*) as play_count,
                        COUNT(DISTINCT track_id) as unique_tracks
                 FROM listening_events
                 WHERE artist_id IS NOT NULL
                 GROUP BY artist_id) p
           JOIN artists a ON a.id = p.artist_id
           LEFT JOIN artist_genres ag ON ag.artist_id = a.id
           GROUP BY a.id
           ORDER BY p.play_count DESC, a.name
           LIMIT 20"""
    ).fetchall()

    top = []
    seen = set()
    for a in played:
        if a["name"] in seen:
            continue
        seen.add(a["name"])
        top.append(
            {
                "name": a["name"],
                "popularity": a["popularity"],
                "genres": a["genres"].split(",") if a["genres"] else [],
                "play_count": a["play_count"],
                "unique_tracks": a["unique_tracks"],
                "time_range": "warehouse",
            }
        )

    # Warehouse too sparse to fill the list — pad from the API snapshots.
    if len(top) < 15:
        snapshot = db.execute(
            """SELECT a.name, a.popularity, GROUP_CONCAT(DISTINCT ag.genre) as genres,
                    MIN(tas.rank) as rank
               FROM top_artists_snapshots tas
               JOIN artists a ON a.id = tas.artist_id
               LEFT JOIN artist_genres ag ON ag.artist_id = a.id
               WHERE tas.time_range IN ('long_term', 'medium_term')
               GROUP BY a.id
               ORDER BY rank
               LIMIT 30"""
        ).fetchall()
        for a in snapshot:
            if len(top) >= 15:
                break
            if a["name"] in seen:
                continue
            seen.add(a["name"])
            top.append(
                {
                    "name": a["name"],
                    "popularity": a["popularity"],
                    "genres": a["genres"].split(",") if a["genres"] else [],
                    "play_count": 0,
                    "unique_tracks": 0,
                    "time_range": "long_term",
                }
            )

    db.close()
    return jsonify({"artists": top[:15]})


@app.route("/api/top-tracks")
def api_top_tracks():
    """Top tracks, ranked by actual plays in the local warehouse.

    Same rationale as `api_top_artists`: rank from `listening_events`, use the
    snapshots only to pad a short list.
    """
    db = get_db()

    def shape(row, play_count):
        duration = row["duration_ms"] or 0
        return {
            "name": row["name"],
            "artist": row["artist_name"],
            "album": row["album_name"],
            "popularity": row["popularity"],
            "duration_ms": duration,
            "play_count": play_count,
            "genres": row["genres"].split(",") if row["genres"] else [],
            "duration_formatted": f"{duration // 60000}:{(duration % 60000) // 1000:02d}",
        }

    played = db.execute(
        """SELECT t.name, t.popularity, t.duration_ms, t.artist_name, t.album_name,
                p.play_count,
                GROUP_CONCAT(DISTINCT ag.genre) as genres
           FROM (SELECT track_id, COUNT(*) as play_count
                 FROM listening_events
                 WHERE track_id IS NOT NULL
                 GROUP BY track_id) p
           JOIN tracks t ON t.id = p.track_id
           LEFT JOIN artist_genres ag ON ag.artist_id = t.artist_id
           GROUP BY t.id
           ORDER BY p.play_count DESC, t.name
           LIMIT 20"""
    ).fetchall()

    track_list = []
    seen = set()
    for t in played:
        key = (t["name"], t["artist_name"])
        if key in seen:
            continue
        seen.add(key)
        track_list.append(shape(t, t["play_count"]))

    if len(track_list) < 15:
        snapshot = db.execute(
            """SELECT t.name, t.popularity, t.duration_ms, t.artist_name, t.album_name,
                    GROUP_CONCAT(DISTINCT ag.genre) as genres,
                    MIN(tts.rank) as rank
               FROM top_tracks_snapshots tts
               JOIN tracks t ON t.id = tts.track_id
               LEFT JOIN artist_genres ag ON ag.artist_id = t.artist_id
               WHERE tts.time_range IN ('long_term', 'medium_term')
               GROUP BY t.id
               ORDER BY rank
               LIMIT 30"""
        ).fetchall()
        for t in snapshot:
            if len(track_list) >= 15:
                break
            key = (t["name"], t["artist_name"])
            if key in seen:
                continue
            seen.add(key)
            track_list.append(shape(t, 0))

    db.close()
    return jsonify({"tracks": track_list[:15]})


@app.route("/api/taste-evolution")
def api_taste_evolution():
    """Taste evolution over time."""
    db = get_db()

    timeline = db.execute(
        """SELECT
           strftime('%Y-%m', le.timestamp, 'unixepoch') as period,
           COUNT(*) as plays,
           COUNT(DISTINCT le.track_id) as unique_tracks,
           COUNT(DISTINCT le.artist_id) as unique_artists
           FROM listening_events le
           GROUP BY period
           ORDER BY period"""
    ).fetchall()

    evolution = []
    for t in timeline:
        # Get top genre for this period
        top_genre = db.execute(
            """SELECT ag.genre, COUNT(*) as play_count
               FROM listening_events le2
               JOIN tracks t2 ON le2.track_id = t2.id
               JOIN artist_genres ag ON t2.artist_id = ag.artist_id
               WHERE strftime('%Y-%m', le2.timestamp, 'unixepoch') = ?
               GROUP BY ag.genre
               ORDER BY play_count DESC
               LIMIT 1""",
            (t["period"],),
        ).fetchone()

        evolution.append(
            {
                "period": t["period"],
                "total_plays": t["plays"],
                "plays": t["plays"],
                "unique_tracks": t["unique_tracks"],
                "unique_artists": t["unique_artists"],
                "top_genre": top_genre["genre"] if top_genre else None,
                "top_genre_plays": top_genre["play_count"] if top_genre else 0,
            }
        )

    db.close()
    return jsonify({"timeline": evolution})


@app.route("/api/time-of-day")
def api_time_of_day():
    """Time-of-day analysis."""
    db = get_db()

    hourly = db.execute(
        """SELECT strftime('%H', played_at, 'unixepoch') as hour,
                COUNT(*) as plays
           FROM listening_events
           GROUP BY hour
           ORDER BY hour"""
    ).fetchall()

    hours = {h["hour"]: h["plays"] for h in hourly if h["hour"] is not None}

    # Fill missing hours — keys are the zero-padded strings strftime returns.
    for h in range(24):
        hours.setdefault(f"{h:02d}", 0)

    # Daily
    daily = db.execute(
        """SELECT strftime('%w', played_at, 'unixepoch') as dow,
                COUNT(*) as plays
           FROM listening_events
           GROUP BY dow
           ORDER BY dow"""
    ).fetchall()

    day_names = [
        "Sunday",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
    ]
    days = {}
    for d in daily:
        dow_val = d["dow"]
        if dow_val is not None:
            days[day_names[int(dow_val)]] = d["plays"]

    hourly_dict = {k: hours[k] for k in sorted(hours)}

    db.close()
    return jsonify(
        {
            "hourly": hourly_dict,
            "daily": days,
        }
    )


@app.route("/api/sessions")
def api_sessions():
    """Listening session data."""
    db = get_db()

    recent_sessions = db.execute(
        """SELECT
           strftime('%Y-%m-%d %H:%M', played_at, 'unixepoch') as start_time,
           COUNT(*) as track_count,
           COUNT(DISTINCT track_id) as unique_tracks,
           COUNT(DISTINCT artist_id) as unique_artists
           FROM listening_events
           GROUP BY
             CAST( played_at / 1800 AS INTEGER )
           ORDER BY start_time DESC
           LIMIT 50"""
    ).fetchall()

    sessions = []
    for s in recent_sessions:
        sessions.append(
            {
                "start": s["start_time"],
                "track_count": s["track_count"],
                "unique_tracks": s["unique_tracks"],
                "unique_artists": s["unique_artists"],
            }
        )

    db.close()
    return jsonify({"sessions": sessions})


@app.route("/api/library")
def api_library():
    """Saved tracks, albums, playlists."""
    db = get_db()

    saved_tracks = db.execute(
        """SELECT t.name, t.artist_name, t.album_name, t.duration_ms,
                t.popularity, st.added_at
           FROM saved_tracks st
           JOIN tracks t ON st.track_id = t.id
           ORDER BY st.added_at DESC
           LIMIT 50"""
    ).fetchall()

    saved_albums = db.execute(
        """SELECT al.name, al.artist_name, al.release_date, al.total_tracks,
                al.popularity, sa.added_at
           FROM saved_albums sa
           JOIN albums al ON sa.album_id = al.id
           ORDER BY sa.added_at DESC
           LIMIT 50"""
    ).fetchall()

    playlists = db.execute(
        "SELECT id, name, description, tracks_total, public, "
        "collaborative FROM playlists ORDER BY name LIMIT 50"
    ).fetchall()

    db.close()
    return jsonify(
        {
            "saved_tracks": [
                {
                    "name": t["name"],
                    "artist": t["artist_name"],
                    "album": t["album_name"],
                    "duration_ms": t["duration_ms"],
                    "popularity": t["popularity"],
                    "added_at": t["added_at"],
                    "duration_formatted": f"{t['duration_ms'] // 60000}:"
                    f"{(t['duration_ms'] % 60000) // 1000:02d}",
                }
                for t in saved_tracks
            ],
            "saved_albums": [
                {
                    "name": a["name"],
                    "artist": a["artist_name"],
                    "release_date": a["release_date"],
                    "total_tracks": a["total_tracks"],
                    "popularity": a["popularity"],
                    "added_at": a["added_at"],
                }
                for a in saved_albums
            ],
            "playlists": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "description": p["description"],
                    "tracks_total": p["tracks_total"],
                    "public": bool(p["public"]),
                    "collaborative": bool(p["collaborative"]),
                }
                for p in playlists
            ],
        }
    )


@app.route("/api/analytics")
def api_analytics():
    """Full cached analytics or compute fresh."""
    db = get_db()

    cached = db.execute(
        "SELECT value FROM analytics_cache WHERE key='full_intelligence'"
    ).fetchone()

    if cached:
        db.close()
        return jsonify(json.loads(cached["value"]))

    # If not cached, compute now (this is slow — in production, run
    # analytics.py separately)
    db.close()
    return jsonify(
        {"error": "Analytics not cached. Run analytics.py first."}
    ), 503


@app.route("/api/currently-playing")
def api_currently_playing():
    """Real-time currently playing track."""
    client = spotify_client()
    if client is None:
        # Not an error: this machine simply has no Spotify client available.
        return jsonify(
            {
                "playing": False,
                "connected": False,
                "message": "Spotify client unavailable on this host",
            }
        )

    try:
        cp = client.get_currently_playing()

        if cp and cp.get("empty"):
            return jsonify(
                {"playing": False, "message": cp.get("message", "Nothing playing")}
            )

        track = cp.get("track", {})
        if not track:
            return jsonify({"playing": False, "message": "No track data"})

        # Get audio features
        audio = None
        try:
            af = client.request("GET", f"/audio-features/{track['id']}")
            if af:
                audio = {
                    "danceability": af.get("danceability"),
                    "energy": af.get("energy"),
                    "valence": af.get("valence"),
                    "acousticness": af.get("acousticness"),
                    "tempo": af.get("tempo"),
                    "loudness": af.get("loudness"),
                }
        except Exception:
            pass

        return jsonify(
            {
                "playing": True,
                "track": {
                    "id": track.get("id"),
                    "name": track.get("name"),
                    "artist": track.get("artists", [{}])[0].get("name"),
                    "artist_id": track.get("artists", [{}])[0].get("id"),
                    "album": track.get("album", {}).get("name"),
                    "album_id": track.get("album", {}).get("id"),
                    "duration_ms": track.get("duration_ms"),
                    "popularity": track.get("popularity"),
                    "explicit": track.get("explicit", False),
                    "disc_number": track.get("disc_number"),
                    "track_number": track.get("track_number"),
                },
                "progress_ms": cp.get("progress_ms"),
                "is_playing": cp.get("is_playing"),
                "audio_features": audio,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as e:
        return jsonify(
            {"playing": False, "connected": True, "error": str(e)}
        ), 502


# ---------------------------------------------------------------------------
# Genre normalization (needed for API)
# ---------------------------------------------------------------------------

GENRE_FAMILIES = {
    "alternative rock": "Rock",
    "alternative": "Rock",
    "rock": "Rock",
    "post-grunge": "Rock",
    "grunge": "Rock",
    "indie rock": "Rock",
    "hard rock": "Rock",
    "heavy metal": "Rock",
    "metal": "Rock",
    "metalcore": "Rock",
    "nu metal": "Rock",
    "rap rock": "Rock",
    "alternative metal": "Rock",
    "progressive rock": "Rock",
    "post-punk": "Rock",
    "shoegaze": "Rock",
    "britpop": "Rock",
    "punk rock": "Rock",
    "pop punk": "Rock",
    "indie pop": "Rock",
    "pop rock": "Rock",
    "folk rock": "Rock",
    "folk": "Folk/Acoustic",
    "indie folk": "Folk/Acoustic",
    "singer-songwriter": "Folk/Acoustic",
    "americana": "Folk/Acoustic",
    "folk pop": "Folk/Acoustic",
    "acoustic": "Folk/Acoustic",
    "electronic": "Electronic",
    "house": "Electronic",
    "electro house": "Electronic",
    "progressive house": "Electronic",
    "dance": "Electronic",
    "dance pop": "Electronic",
    "electropop": "Electronic",
    "synth-pop": "Electronic",
    "dubstep": "Electronic",
    "ambient": "Electronic",
    "experimental": "Electronic",
    "pop": "Pop",
    "country pop": "Pop",
    "asian pop": "Pop",
    "bangla pop": "Pop",
    "disco": "Pop",
    "soul": "Pop",
    "r&b": "Pop",
    "hip hop": "Hip-Hop",
    "rap": "Hip-Hop",
    "alternative hip hop": "Hip-Hop",
    "thr": "Metal",
    "thrash metal": "Metal",
    "death metal": "Metal",
    "indie": "Indie/Alternative",
    "indie folk": "Indie/Alternative",
    "indie rock": "Indie/Alternative",
    "indie pop": "Indie/Alternative",
    "soundtrack": "Soundtrack/Score",
    "latin": "Latin/World",
    "reggaeton": "Latin/World",
    "reggae": "Latin/World",
    "jazz": "Jazz",
    "classical": "Classical/Instrumental",
    "piano": "Classical/Instrumental",
    "country": "Country",
    "country rock": "Country",
    "comedy": "Comedy/Spoken",
    "spoken word": "Comedy/Spoken",
    "art pop": "Indie/Alternative",
    "art rock": "Rock",
    "lo-fi": "Electronic",
    "chill": "Electronic",
    "post-rock": "Rock",
    "slowcore": "Indie/Alternative",
}


def normalize_genre(genre: str) -> str:
    g = genre.lower().strip()
    if g in GENRE_FAMILIES:
        return GENRE_FAMILIES[g]
    for key, family in GENRE_FAMILIES.items():
        if key in g or g in key:
            return family
    return g.split("-")[0].split()[0].title()


# ---------------------------------------------------------------------------
# Page route — serves any .dc.html or .html template by name
# ---------------------------------------------------------------------------

@app.route("/<page>")
def page(page):
    # Map bare names to .html templates, also serve static files
    if not page.endswith(".html"):
        page = page + ".html"
    if page.startswith("..") or "/" in page:
        return "Not found", 404
    tpath = TEMPLATE_DIR / page
    if tpath.exists():
        return render_template(page)
    spath = STATIC_DIR / page
    if spath.exists():
        return send_from_directory(str(STATIC_DIR), page)
    return "Not found", 404


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/recent")
def api_recent():
    """Most recent listening events, newest first."""
    try:
        limit = min(max(int(request.args.get("limit", 20)), 1), 100)
    except (TypeError, ValueError):
        limit = 20

    db = get_db()
    rows = db.execute(
        """SELECT le.played_at, t.name as track_name, t.artist_name,
                t.album_name
           FROM listening_events le
           JOIN tracks t ON t.id = le.track_id
           ORDER BY le.played_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    db.close()

    plays = []
    for position, r in enumerate(rows):
        try:
            played_at = datetime.fromtimestamp(
                r["played_at"], tz=timezone.utc
            ).isoformat()
        except (TypeError, ValueError, OSError):
            played_at = None
        plays.append(
            {
                "track": r["track_name"],
                "artist": r["artist_name"],
                "album": r["album_name"],
                "played_at": played_at,
                "tracks_ago": position,
            }
        )

    return jsonify({"plays": plays, "count": len(plays)})


@app.route("/api/status")
def api_status():
    """Warehouse and sync status for the Settings page."""
    db = get_db()

    def scalar(sql, default=0):
        try:
            return db.execute(sql).fetchone()[0]
        except Exception:
            return default

    counts = {
        "plays": scalar("SELECT COUNT(*) FROM listening_events"),
        "artists": scalar(
            "SELECT COUNT(DISTINCT artist_id) FROM listening_events"
        ),
        "tracks": scalar(
            "SELECT COUNT(DISTINCT track_id) FROM listening_events"
        ),
        "saved_tracks": scalar("SELECT COUNT(*) FROM saved_tracks"),
        "saved_albums": scalar("SELECT COUNT(*) FROM saved_albums"),
        "playlists": scalar("SELECT COUNT(*) FROM playlists"),
    }
    last_play = scalar("SELECT MAX(played_at) FROM listening_events", None)
    computed_at = scalar(
        "SELECT computed_at FROM analytics_cache "
        "WHERE key='full_intelligence'",
        None,
    )
    db.close()

    def iso(ts):
        if not ts:
            return None
        try:
            return datetime.fromtimestamp(
                float(ts), tz=timezone.utc
            ).isoformat()
        except (TypeError, ValueError, OSError):
            return None

    db_file = Path(str(DB_PATH))
    return jsonify(
        {
            "counts": counts,
            "last_play": iso(last_play),
            "analytics_computed_at": iso(computed_at),
            "analytics_cached": computed_at is not None,
            "database_bytes": db_file.stat().st_size if db_file.exists() else 0,
        }
    )


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


# ---------------------------------------------------------------------------
# Stub endpoints for Figma page surface (return real data from analytics
# cache)
#
# These endpoints are referenced in the Figma design but consumed by the
# dashboard.js handlers via /api/analytics — the stubs below serve the
# standalone API surface for completeness.
# ---------------------------------------------------------------------------

@app.route("/api/listening-patterns")
def listening_patterns():
    """Time-of-day and day-of-week pattern summary."""
    try:
        data = json.loads(db_cache("full_intelligence"))
    except Exception:
        return jsonify({"error": "unknown"}), 500
    tod = data.get("time_of_day", {})
    hourly = _plays_by(tod.get("hourly_breakdown", {}))
    for hour in range(24):
        hourly.setdefault(f"{hour:02d}", 0)

    return jsonify(
        {
            "hourly": {k: hourly[k] for k in sorted(hourly)},
            "daily": _plays_by(tod.get("daily_breakdown", {})),
            "time_of_day": _plays_by(tod.get("time_of_day", {})),
            "peak_hour": tod.get("peak_hour"),
            "peak_day": tod.get("peak_day"),
        }
    )


@app.route("/api/mood")
def mood():
    """Mood/audio-feature profile derived from listening history."""
    try:
        data = json.loads(db_cache("full_intelligence"))
    except Exception:
        return jsonify({"error": "unknown"}), 500
    audio = data.get("audio_characteristics", {})
    audio_inner = (
        audio.get("audio_characteristics", {}) if isinstance(audio, dict) else {}
    )
    explicit = data.get("explicit_content", {})

    def pct(name, default=0.5):
        """analytics.py emits bare feature names (`valence`), not `avg_valence`."""
        value = audio_inner.get(name)
        return round((default if value is None else value) * 100)

    valence, energy = pct("valence"), pct("energy")
    if valence >= 60 and energy >= 60:
        overall = "upbeat"
    elif valence <= 40 and energy <= 40:
        overall = "melancholic"
    elif energy >= 65:
        overall = "energetic"
    elif valence <= 40:
        overall = "introspective"
    else:
        overall = "balanced"

    return jsonify(
        {
            "overall_mood": overall,
            "explicit_pct": (
                round(explicit.get("explicit_percentage", 0), 1)
                if explicit
                else 0
            ),
            "valence_avg": valence,
            "energy_avg": energy,
            "acoustic_avg": pct("acousticness", 0.0),
            "danceable_avg": pct("danceability"),
            "top_moods": [
                label
                for label in (audio.get("interpretation", {}) or {}).values()
                if label
            ],
        }
    )


@app.route("/api/archetype")
def archetype():
    """Listener archetype."""
    try:
        data = json.loads(db_cache("full_intelligence"))
    except Exception:
        return jsonify({"error": "unknown"}), 500
    ac = data.get("listener_archetype", {})
    return jsonify(
        {
            "archetype": ac.get("archetype", "The Listener"),
            "archetype_key": ac.get("archetype_key", "listener"),
            "archetype_signals": ac.get("archetype_signals", []),
            "supporting_metrics": ac.get("supporting_metrics", {}),
        }
    )


@app.route("/api/evolution")
def evolution():
    """Taste evolution over time (alias for /api/taste-evolution)."""
    try:
        data = json.loads(db_cache("full_intelligence"))
    except Exception:
        return jsonify({"error": "unknown"}), 500
    te = data.get("taste_evolution", {})
    timeline = te.get("timeline", []) if isinstance(te, dict) else []
    return jsonify(
        {
            "timeline": [
                {
                    "period": t.get("period"),
                    "total_plays": t.get("plays", t.get("total_plays", 0)),
                    "plays": t.get("plays", t.get("total_plays", 0)),
                    "unique_tracks": t.get("unique_tracks", 0),
                    "unique_artists": t.get("unique_artists", 0),
                    "top_genre": _top_genre_of(t),
                    "genre_diversity": t.get("genre_diversity"),
                }
                for t in timeline
            ],
            "shifts": te.get("shifts", []) if isinstance(te, dict) else [],
        }
    )


@app.route("/api/playlist")
def playlist():
    """Top playlists by play count — served from the warehouse DB."""
    db = get_db()

    pls = db.execute(
        "SELECT id, name, description, tracks_total, public, "
        "collaborative FROM playlists ORDER BY name LIMIT 50"
    ).fetchall()

    db.close()
    return jsonify(
        {
            "playlists": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "description": p["description"],
                    "tracks_total": p["tracks_total"],
                    "public": bool(p["public"]),
                    "collaborative": bool(p["collaborative"]),
                }
                for p in pls
            ]
        }
    )


@app.route("/api/timezone")
def timezone_info():
    """User timezone derived from listening timestamps."""
    try:
        data = json.loads(db_cache("full_intelligence"))
    except Exception:
        return jsonify({"error": "unknown"}), 500
    freq = data.get("listening_frequency", {})
    tod = data.get("time_of_day", {})
    return jsonify(
        {
            "timezone": "Asia/Dhaka",
            "utc_offset": 6,
            "peak_hour": tod.get("peak_hour", 14),
            # analytics.py reports active_days as a count; the day names live
            # in the time-of-day breakdown.
            "active_days": freq.get("active_days", 0),
            "listening_days": sorted(
                _plays_by(tod.get("daily_breakdown", {}))
            ),
            "plays_per_day": freq.get("plays_per_day", 0),
        }
    )


@app.route("/api/insights")
def insights():
    """Listening insights derived from the cached analytics.

    There is no top-level `findings` key in the analytics output — reading one
    made this endpoint return an empty list on every request.  The sentences
    below mirror the client-side `deriveInsights` rules so both surfaces agree.
    """
    try:
        data = json.loads(db_cache("full_intelligence"))
    except Exception:
        return jsonify({"error": "unknown"}), 500

    found = []

    diversity = data.get("genre_diversity") or {}
    if diversity.get("genre_count"):
        top_genre_name = None
        if diversity.get("top_genres"):
            top_genre_name = diversity["top_genres"][0].get("genre")
        if top_genre_name:
            found.append(
                "You span "
                + str(diversity["genre_count"])
                + " genres, with a diversity score of "
                + str(diversity.get("diversity_score", 0))
                + "%. "
                + "Your most-played is "
                + top_genre_name
                + "."
            )
        else:
            found.append(
                "You span " + str(diversity["genre_count"]) + " genres."
            )

    discovery = data.get("discovery_rate") or {}
    if discovery.get("discovery_rate") is not None:
        rate = discovery["discovery_rate"]
        found.append(
            f"Your discovery rate is {rate}% — "
            + (
                "most of what you play is new to your history."
                if rate >= 50
                else f"you return to familiar tracks "
                f"{discovery.get('comfort_score', 100 - rate)}% of the time."
            )
        )

    archetype = data.get("listener_archetype") or {}
    if archetype.get("archetype"):
        signals = "; ".join(
            s.get("description", "")
            for s in archetype.get("archetype_signals", [])
            if s
        )
        found.append(
            f"Your archetype is \"{archetype['archetype']}\""
            + (f" — {signals}." if signals else ".")
        )

    mainstream = data.get("mainstream_vs_obscure") or {}
    if mainstream.get("tendency"):
        found.append(
            f"Your taste leans {mainstream['tendency']} — the artists you play "
            f"average {mainstream.get('average_artist_popularity', 0)} on "
            f"Spotify's popularity scale."
        )

    explicit = data.get("explicit_content") or {}
    if explicit.get("explicit_percentage"):
        found.append(
            f"{explicit['explicit_percentage']}% of your plays are explicit "
            f"({explicit.get('explicit_tendency', 'moderate')} by our banding)."
        )

    repeat = data.get("repeat_rate") or {}
    if repeat.get("repeat_rate_tracks") is not None:
        found.append(
            f"You replay {repeat['repeat_rate_tracks']}% of your tracks and "
            f"{repeat.get('repeat_rate_artists', 0)}% of your artists."
        )

    if not found:
        found.append(
            "Your listening patterns are still forming. "
            "Insights will appear as more data accumulates."
        )

    return jsonify({"insights": found})


@app.route("/api/anomalies")
def anomalies():
    """Detected listening anomalies."""
    try:
        data = json.loads(db_cache("full_intelligence"))
    except Exception:
        return jsonify({"error": "unknown"}), 500
    anom = data.get("anomalies", {})
    return jsonify(
        {
            "findings": anom.get("findings", [])
            if isinstance(anom, dict)
            else []
        }
    )


# ---------------------------------------------------------------------------
# Page route — serves any .dc.html or .html template by name
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", "5000"))
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    print(f"[dashboard] Starting on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
