#!/usr/bin/env python3
"""
Spotify Analytics Engine
Computes listener intelligence metrics from the data warehouse.
All metrics are reproducible from stored data — no fabrication.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent
DB_PATH = REPO_ROOT / "spotify_data.db"


def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


# ---------------------------------------------------------------------------
# Genre normalization — map raw Spotify genres to genre families
# ---------------------------------------------------------------------------

GENRE_FAMILIES = {
    # Rock sub-genres
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
    "psychedelic rock": "Rock",
    "classic rock": "Rock",
    "new wave": "Rock",
    "garage rock": "Rock",
    "synth-rock": "Rock",
    "emo": "Rock",
    "emo punk": "Rock",
    "melodic metal": "Rock",
    "hardcore": "Rock",
    "post-hardcore": "Rock",
    "emo pop": "Rock",
    "dance-punk": "Rock",
    "noise rock": "Rock",
    
    # Folk / Acoustic
    "folk": "Folk/Acoustic",
    "indie folk": "Folk/Acoustic",
    "singer-songwriter": "Folk/Acoustic",
    "americana": "Folk/Acoustic",
    "folk pop": "Folk/Acoustic",
    "acoustic": "Folk/Acoustic",
    "bluegrass": "Folk/Acoustic",
    "celtic": "Folk/Acoustic",
    "world folk": "Folk/Acoustic",
    "malaysian folk": "Folk/Acoustic",
    "bangla folk": "Folk/Acoustic",
    
    # Electronic
    "electronic": "Electronic",
    "house": "Electronic",
    "electro house": "Electronic",
    "progressive house": "Electronic",
    "dance": "Electronic",
    "dance pop": "Electronic",
    "electropop": "Electronic",
    "synth-pop": "Electronic",
    "dubstep": "Electronic",
    "drum and bass": "Electronic",
    "techno": "Electronic",
    "trance": "Electronic",
    "ambient": "Electronic",
    "experimental": "Electronic",
    "big beat": "Electronic",
    "breakbeat": "Electronic",
    "downtempo": "Electronic",
    "idm": "Electronic",
    "chillout": "Electronic",
    "tropical house": "Electronic",
    "deep house": "Electronic",
    "trap": "Electronic",
    "rage": "Electronic",
    "future bass": "Electronic",
    "bedroom pop": "Electronic",
    
    # Pop
    "pop": "Pop",
    "country pop": "Pop",
    "asian pop": "Pop",
    "bangla pop": "Pop",
    "k-pop": "Pop",
    "j-pop": "Pop",
    "disco": "Pop",
    "funk": "Pop",
    "soul": "Pop",
    "r&b": "Pop",
    "alternative r&b": "Pop",
    "indie r&b": "Pop",
    "neo soul": "Pop",
    "funk pop": "Pop",
    "pop rap": "Pop",
    
    # Rap / Hip-Hop
    "hip hop": "Hip-Hop",
    "rap": "Hip-Hop",
    "rap metal": "Hip-Hop",
    "alternative hip hop": "Hip-Hop",
    "conscious hip hop": "Hip-Hop",
    "canadian hip hop": "Hip-Hop",
    "east coast hip hop": "Hip-Hop",
    "rap rock": "Hip-Hop",
    "trap": "Hip-Hop",
    
    # Metal (heavy)
    "thrash metal": "Metal",
    "groove metal": "Metal",
    "death metal": "Metal",
    "black metal": "Metal",
    "power metal": "Metal",
    "symphonic metal": "Metal",
    "gothic metal": "Metal",
    "doom metal": "Metal",
    "progressive metal": "Metal",
    "metalcore": "Metal",
    "deathcore": "Metal",
    "melodic death metal": "Metal",
    "djent": "Metal",
    
    # Indie / Alternative umbrella
    "indie": "Indie/Alternative",
    "indie pop": "Indie/Alternative",
    "indie rock": "Indie/Alternative",
    "indie folk": "Indie/Alternative",
    "alternative": "Indie/Alternative",
    "indie soul": "Indie/Alternative",
    "indie gospel": "Indie/Alternative",
    "indie country": "Indie/Alternative",
    "chamber pop": "Indie/Alternative",
    
    # Rock-specific labels
    "post-grunge": "Rock",
    "grunge": "Rock",
    "britpop": "Rock",
    
    # Soundtrack / Score
    "soundtrack": "Soundtrack/Score",
    "film score": "Soundtrack/Score",
    "video game soundtrack": "Soundtrack/Score",
    
    # Latin / World
    "latin": "Latin/World",
    "reggaeton": "Latin/World",
    "reggae": "Latin/World",
    "dancehall": "Latin/World",
    "world music": "Latin/World",
    "afrobeat": "Latin/World",
    "enka": "Latin/World",
    "bangla rock": "Latin/World",
    
    # Jazz
    "jazz": "Jazz",
    "bebop": "Jazz",
    "smooth jazz": "Jazz",
    "fusion": "Jazz",
    "jazz fusion": "Jazz",
    
    # Classical / Piano
    "classical": "Classical/Instrumental",
    "piano": "Classical/Instrumental",
    "orchestral": "Classical/Instrumental",
    "chamber music": "Classical/Instrumental",
    "ambient": "Classical/Instrumental",
    "contemporary classical": "Classical/Instrumental",
    
    # Country
    "country": "Country",
    "country rock": "Country",
    "outlaw country": "Country",
    "hank williams": "Country",
    
    # Comedy / Spoken
    "comedy": "Comedy/Spoken",
    "spoken word": "Comedy/Spoken",
    "parody": "Comedy/Spoken",
    
    # 기타 / uncategorized — map to closest
    "noise": "Experimental",
    "art pop": "Indie/Alternative",
    "art rock": "Rock",
    "experimental pop": "Experimental",
    "chill": "Electronic",
    "chillhop": "Electronic",
    "lo-fi": "Electronic",
    "gong": "Experimental",
    "ballad": "Pop",
    "power ballad": "Rock",
    "post-rock": "Rock",
    "slowcore": "Indie/Alternative",
    "sadcore": "Indie/Alternative",
    "twee pop": "Indie/Alternative",
    "queercore": "Rock",
    "riot grrrl": "Rock",
    "jangle pop": "Rock",
    "madchester": "Rock",
    "shoegaze": "Rock",
    "space rock": "Rock",
    "stoner rock": "Rock",
    "stoner metal": "Metal",
    "sludge metal": "Metal",
    "crust punk": "Rock",
    "anime": "Pop",
    "vocal trance": "Electronic",
    "vocal house": "Electronic",
    "minimal": "Electronic",
    "minimal techno": "Electronic",
    "german metal": "Metal",
    "industrial": "Rock",
    "industrial rock": "Rock",
    "industrial metal": "Metal",
    "ebm": "Electronic",
    "future garage": "Electronic",
    "generic trance": "Electronic",
    "bouncy techno": "Electronic",
    "uk hard house": "Electronic",
    "garage": "Electronic",
    "uk garage": "Electronic",
    "2 tone ska": "Rock",
    "ska": "Rock",
    "ska core": "Rock",
    "ska punk": "Rock",
    "popska": "Rock",
    "nintendocore": "Rock",
    "cello":"Classical/Instrumental",
    "banjo":"Folk/Acoustic",
}


def normalize_genre(genre: str) -> str:
    """Map a raw Spotify genre to a genre family."""
    g = genre.lower().strip()
    if g in GENRE_FAMILIES:
        return GENRE_FAMILIES[g]
    # Try partial match
    for key, family in GENRE_FAMILIES.items():
        if key in g or g in key:
            return family
    # Default: use first word as family
    return g.split("-")[0].split()[0].title()


def get_genre_families() -> Dict[str, List[str]]:
    """Return the genre → family mapping."""
    families = defaultdict(list)
    for genre, family in GENRE_FAMILIES.items():
        families[family].append(genre)
    return dict(families)


# ---------------------------------------------------------------------------
# Core analytics
# ---------------------------------------------------------------------------

def compute_total_listening(db) -> Dict[str, Any]:
    """Total listening metrics."""
    row = db.execute(
        """SELECT 
           COUNT(*) as total_plays,
           COUNT(DISTINCT track_id) as unique_tracks,
           COUNT(DISTINCT artist_id) as unique_artists,
           COUNT(DISTINCT album_id) as unique_albums,
           MIN(played_at) as first_play,
           MAX(played_at) as last_play
           FROM listening_events"""
    ).fetchone()
    
    total_ms = db.execute(
        "SELECT SUM(t.duration_ms) FROM listening_events le JOIN tracks t ON le.track_id = t.id"
    ).fetchone()[0] or 0
    
    return {
        "total_plays": row["total_plays"],
        "unique_tracks": row["unique_tracks"],
        "unique_artists": row["unique_artists"],
        "unique_albums": row["unique_albums"],
        "total_listening_ms": total_ms,
        "total_listening_hours": round(total_ms / 3600000, 2),
        "first_play": datetime.fromtimestamp(row["first_play"], tz=timezone.utc).isoformat() if row["first_play"] else None,
        "last_play": datetime.fromtimestamp(row["last_play"], tz=timezone.utc).isoformat() if row["last_play"] else None,
        "date_range_days": (
            (row["last_play"] - row["first_play"]) / 86400
            if row["first_play"] and row["last_play"]
            else 0
        ),
    }


def compute_listening_frequency(db) -> Dict[str, Any]:
    """Listening frequency and patterns."""
    row = db.execute(
        """SELECT 
           COUNT(*) as total_plays,
           COUNT(DISTINCT DATE(timestamp, 'unixepoch')) as active_days
           FROM listening_events"""
    ).fetchone()
    
    total = row["total_plays"]
    days = row["active_days"] or 1
    
    return {
        "plays_per_day": round(total / days, 2),
        "active_days": days,
        "average_play_length_ms": (
            db.execute(
                "SELECT AVG(t.duration_ms) FROM listening_events le JOIN tracks t ON le.track_id = t.id"
            ).fetchone()[0] or 0
        ),
        "average_play_length_min": round((db.execute(
            "SELECT AVG(t.duration_ms) FROM listening_events le JOIN tracks t ON le.track_id = t.id"
        ).fetchone()[0] or 0) / 60000, 2),
    }


def compute_repeat_rate(db) -> Dict[str, Any]:
    """How often does the listener replay tracks/artists/albums?"""
    track_plays = db.execute(
        "SELECT track_id, COUNT(*) as plays FROM listening_events GROUP BY track_id HAVING plays > 1"
    ).fetchall()
    
    artist_plays = db.execute(
        "SELECT artist_id, COUNT(*) as plays FROM listening_events GROUP BY artist_id HAVING plays > 1"
    ).fetchall()
    
    total_tracks = db.execute("SELECT COUNT(DISTINCT track_id) FROM listening_events").fetchone()[0]
    total_artists = db.execute("SELECT COUNT(DISTINCT artist_id) FROM listening_events").fetchone()[0]
    
    repeated_tracks = len(track_plays)
    repeated_artists = len(artist_plays)
    
    # Average repeat count for repeated tracks
    avg_repeat = mean([r["plays"] for r in track_plays]) if track_plays else 0
    
    return {
        "repeat_rate_tracks": round(repeated_tracks / total_tracks * 100, 1) if total_tracks else 0,
        "repeat_rate_artists": round(repeated_artists / total_artists * 100, 1) if total_artists else 0,
        "repeated_tracks_count": repeated_tracks,
        "repeated_artists_count": repeated_artists,
        "avg_repeat_count": round(avg_repeat, 2),
        "most_repeated_track_id": track_plays[0]["track_id"] if track_plays else None,
        "most_repeated_track_count": track_plays[0]["plays"] if track_plays else 0,
        "most_repeated_artist_id": artist_plays[0]["artist_id"] if artist_plays else None,
        "most_repeated_artist_count": artist_plays[0]["plays"] if artist_plays else 0,
    }


def compute_discovery_rate(db) -> Dict[str, Any]:
    """Discovery vs comfort metrics."""
    # Tracks listened to only once
    once_tracks = db.execute(
        "SELECT COUNT(*) FROM (SELECT track_id FROM listening_events GROUP BY track_id HAVING COUNT(*) = 1)"
    ).fetchone()[0]
    
    total_tracks = db.execute("SELECT COUNT(DISTINCT track_id) FROM listening_events").fetchone()[0]
    
    return {
        "discovery_rate": round(once_tracks / total_tracks * 100, 1) if total_tracks else 0,
        "one_time_tracks": once_tracks,
        "total_unique_tracks": total_tracks,
        "discovery_score": round((once_tracks / total_tracks * 100) if total_tracks else 0, 1),
        "comfort_score": round(100 - (once_tracks / total_tracks * 100) if total_tracks else 0, 1),
    }


def compute_artist_loyalty(db) -> Dict[str, Any]:
    """Artist loyalty metrics."""
    artist_track_counts = db.execute(
        """SELECT artist_id, COUNT(DISTINCT track_id) as track_count, COUNT(*) as play_count
           FROM listening_events GROUP BY artist_id ORDER BY play_count DESC"""
    ).fetchall()
    
    if not artist_track_counts:
        return {"loyalty_score": 0, "top_loyal_artists": []}
    
    # Loyalty = plays per unique track (higher = more loyal to an artist's catalog)
    loyalty_data = []
    for a in artist_track_counts[:20]:
        loyalty = a["play_count"] / a["track_count"] if a["track_count"] > 0 else 0
        loyalty_data.append({
            "artist_id": a["artist_id"],
            "track_count": a["track_count"],
            "play_count": a["play_count"],
            "loyalty_ratio": round(loyalty, 2),
        })
    
    return {
        "loyalty_score": round(mean([l["loyalty_ratio"] for l in loyalty_data]), 2),
        "top_loyal_artists": loyalty_data[:10],
        "avg_artist_play_depth": round(mean([l["play_count"] for l in loyalty_data]), 1),
    }


def compute_genre_diversity(db) -> Dict[str, Any]:
    """Genre diversity metrics."""
    # Get genre counts from artist_genres joined through listening events
    genre_counts = db.execute(
        """SELECT ag.genre, COUNT(DISTINCT le.track_id) as track_count, COUNT(*) as play_count
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           JOIN artist_genres ag ON t.artist_id = ag.artist_id
           GROUP BY ag.genre
           ORDER BY play_count DESC"""
    ).fetchall()
    
    if not genre_counts:
        return {"diversity_score": 0, "top_genres": [], "genre_count": 0}
    
    total_plays = sum(r["play_count"] for r in genre_counts)
    
    # Shannon diversity index
    proportions = [r["play_count"] / total_plays for r in genre_counts]
    shannon = -sum(p * math.log(p) for p in proportions if p > 0)
    max_shannon = math.log(len(genre_counts))
    normalized_diversity = round(shannon / max_shannon * 100, 1) if max_shannon > 0 else 0
    
    return {
        "diversity_score": normalized_diversity,
        "shannon_index": round(shannon, 3),
        "genre_count": len(genre_counts),
        "top_genres": [
            {"genre": r["genre"], "play_count": r["play_count"], "track_count": r["track_count"],
             "share_pct": round(r["play_count"] / total_plays * 100, 1)}
            for r in genre_counts[:15]
        ],
        "total_plays_with_genre": total_plays,
    }


def compute_genre_loyalty(db) -> Dict[str, Any]:
    """Genre loyalty — does the listener stick to specific genres?"""
    top_genres = db.execute(
        """SELECT ag.genre, COUNT(*) as play_count
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           JOIN artist_genres ag ON t.artist_id = ag.artist_id
           GROUP BY ag.genre
           ORDER BY play_count DESC
           LIMIT 5"""
    ).fetchall()
    
    if not top_genres:
        return {"genre_loyalty_score": 0, "dominant_genres": []}
    
    total = sum(r["play_count"] for r in top_genres)
    top5_share = round(top_genres[0]["play_count"] / total * 100, 1) if total > 0 else 0
    
    return {
        "genre_loyalty_score": top5_share,
        "dominant_genres": [
            {"genre": r["genre"], "play_count": r["play_count"], "share_pct": round(r["play_count"]/total*100, 1)}
            for r in top_genres
        ],
        "concentration_index": round(top5_share, 1),
    }


def compute_album_loyalty(db) -> Dict[str, Any]:
    """Album loyalty — deep listening vs track sampling."""
    album_depth = db.execute(
        """SELECT al.name as album_name, COUNT(DISTINCT le.track_id) as unique_tracks, COUNT(*) as play_count
           FROM listening_events le
           JOIN albums al ON le.album_id = al.id
           GROUP BY al.id, al.name
           ORDER BY play_count DESC
           LIMIT 20"""
    ).fetchall()
    
    if not album_depth:
        return {"album_loyalty_score": 0, "deep_albums": []}
    
    # Album depth score: ratio of plays to unique tracks
    depth_data = []
    for a in album_depth:
        # Get album_id from the albums table
        album_id = db.execute("SELECT id FROM albums WHERE name=? LIMIT 1", (a["album_name"],)).fetchone()
        depth_data.append({
            "album_id": album_id["id"] if album_id else a["album_name"],
            "album_name": a["album_name"],
            "unique_tracks": a["unique_tracks"],
            "play_count": a["play_count"],
            "depth_score": round(a["play_count"] / a["unique_tracks"], 2) if a["unique_tracks"] > 0 else 0,
        })
    
    avg_depth = mean([d["depth_score"] for d in depth_data])
    
    return {
        "album_loyalty_score": round(avg_depth, 2),
        "deep_albums": depth_data[:10],
        "avg_album_plays": round(mean([d["play_count"] for d in depth_data]), 1),
    }


def compute_mainstream_vs_obscure(db) -> Dict[str, Any]:
    """Mainstream vs obscure preference based on artist popularity."""
    popular_artists = db.execute(
        """SELECT AVG(a.popularity) as avg_popularity
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           JOIN artists a ON t.artist_id = a.id
           WHERE a.popularity IS NOT NULL"""
    ).fetchone()
    
    avg_pop = popular_artists["avg_popularity"] or 0
    
    # Spotify popularity ranges 0-100, median ~50
    if avg_pop > 60:
        tendency = "mainstream"
    elif avg_pop > 40:
        tendency = "balanced"
    else:
        tendency = "obscure/underground"
    
    return {
        "average_artist_popularity": round(avg_pop, 1),
        "tendency": tendency,
        "mainstream_score": round(avg_pop, 1),
        "obscure_score": round(100 - avg_pop, 1),
    }


def compute_new_music_affinity(db) -> Dict[str, Any]:
    """New vs catalog music preference based on release dates."""
    # Join tracks with albums for release dates
    release_data = db.execute(
        """SELECT a.release_date, COUNT(*) as play_count
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           JOIN albums a ON t.album_id = a.id
           WHERE a.release_date IS NOT NULL
           GROUP BY a.release_date
           ORDER BY a.release_date"""
    ).fetchall()
    
    if not release_data:
        return {"new_music_affinity": 0, "catalog_affinity": 0, "mostly_recent": True}
    
    # Parse release years and group
    year_counts = defaultdict(int)
    for r in release_data:
        try:
            year = int(r["release_date"][:4])
            year_counts[year] += r["play_count"]
        except (ValueError, IndexError):
            pass
    
    if not year_counts:
        return {"new_music_affinity": 0, "catalog_affinity": 0, "mostly_recent": True}
    
    current_year = datetime.now().year
    recent_years = sum(count for yr, count in year_counts.items() if yr >= current_year - 5)
    total = sum(year_counts.values())
    
    recent_share = round(recent_years / total * 100, 1) if total > 0 else 0
    
    return {
        "new_music_affinity": recent_share,
        "catalog_affinity": round(100 - recent_share, 1),
        "mostly_recent": recent_share > 50,
        "release_year_distribution": dict(sorted(year_counts.items())),
        "peak_year": max(year_counts, key=year_counts.get) if year_counts else None,
        "peak_year_plays": year_counts.get(max(year_counts, key=year_counts.get), 0) if year_counts else 0,
    }


def compute_explicit_content_tendency(db) -> Dict[str, Any]:
    """Explicit content analysis."""
    explicit_count = db.execute(
        "SELECT COUNT(*) FROM listening_events le JOIN tracks t ON le.track_id = t.id WHERE t.explicit = 1"
    ).fetchone()[0]
    
    total = db.execute("SELECT COUNT(*) FROM listening_events").fetchone()[0]
    
    return {
        "explicit_percentage": round(explicit_count / total * 100, 1) if total > 0 else 0,
        "explicit_plays": explicit_count,
        "total_plays": total,
        "explicit_tendency": "high" if explicit_count / total > 0.3 else ("moderate" if explicit_count / total > 0.1 else "low"),
    }


def compute_audio_characteristics(db) -> Dict[str, Any]:
    """Aggregate audio feature analysis."""
    features = db.execute(
        """SELECT 
           AVG(af.danceability) as avg_danceability,
           AVG(af.energy) as avg_energy,
           AVG(af.valence) as avg_valence,
           AVG(af.acousticness) as avg_acousticness,
           AVG(af.instrumentalness) as avg_instrumentalness,
           AVG(af.speechiness) as avg_speechiness,
           AVG(af.tempo) as avg_tempo,
           AVG(af.loudness) as avg_loudness
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           JOIN audio_features af ON t.id = af.track_id"""
    ).fetchone()
    
    if not features or features["avg_danceability"] is None:
        return {"audio_characteristics": {}, "interpretation": "Insufficient audio feature data"}
    
    def interpret(val, label, high_desc, low_desc):
        if val > 0.6:
            return f"High {label} ({high_desc})"
        elif val < 0.3:
            return f"Low {label} ({low_desc})"
        return f"Moderate {label}"
    
    return {
        "audio_characteristics": {
            "danceability": round(features["avg_danceability"], 3),
            "energy": round(features["avg_energy"], 3),
            "valence": round(features["avg_valence"], 3),
            "acousticness": round(features["avg_acousticness"], 3),
            "instrumentalness": round(features["avg_instrumentalness"], 3),
            "speechiness": round(features["avg_speechiness"], 3),
            "tempo": round(features["avg_tempo"], 1),
            "loudness": round(features["avg_loudness"], 2),
        },
        "interpretation": {
            "danceability": interpret(features["avg_danceability"], "danceability", "your music is highly danceable", "your music is not very danceable"),
            "energy": interpret(features["avg_energy"], "energy", "your listening is high-energy", "your listening is low-energy / chill"),
            "valence": interpret(features["avg_valence"], "valence (positivity)", "your music tends positive/uplifting", "your music tends melancholic/dark"),
            "acousticness": interpret(features["avg_acousticness"], "acousticness", "your music is predominantly acoustic", "your music is predominantly electronic/produced"),
            "tempo": f"Average tempo ~{round(features['avg_tempo'])} BPM" if features['avg_tempo'] else "Tempo data unavailable",
        },
    }


def compute_top_n(db, table: str, column: str, n: int = 20, where: str = "") -> List[Dict]:
    """Generic top-N from a snapshot table."""
    query = f"SELECT * FROM {table} WHERE 1=1"
    if where:
        query += f" AND {where}"
    query += f" ORDER BY rank LIMIT {n}"
    
    rows = db.execute(query).fetchall()
    return [dict(r) for r in rows]


def compute_taste_evolution(db, period: str = "month") -> Dict[str, Any]:
    """Taste evolution over time periods."""
    if period == "month":
        group_by = "strftime('%Y-%m', timestamp, 'unixepoch')"
        label = "Month"
    else:
        group_by = "strftime('%Y', timestamp, 'unixepoch')"
        label = "Year"
    
    # Genre evolution
    genre_evolution = db.execute(
        f"""SELECT {group_by} as period, ag.genre, COUNT(*) as play_count
            FROM listening_events le
            JOIN tracks t ON le.track_id = t.id
            JOIN artist_genres ag ON t.artist_id = ag.artist_id
            GROUP BY period, ag.genre
            ORDER BY period, play_count DESC"""
    ).fetchall()
    
    # Artist evolution  
    artist_evolution = db.execute(
        f"""SELECT {group_by} as period, t.artist_name, COUNT(*) as play_count, COUNT(DISTINCT le.track_id) as unique_tracks
            FROM listening_events le
            JOIN tracks t ON le.track_id = t.id
            GROUP BY period, t.artist_name
            ORDER BY period, play_count DESC"""
    ).fetchall()
    
    # Play totals come from the events alone.  The genre query fans out one
    # row per genre and the artist query repeats the same plays again, so
    # summing either (let alone both) inflates the total.
    play_totals = db.execute(
        f"""SELECT {group_by} as period,
                   COUNT(*) as plays,
                   COUNT(DISTINCT le.track_id) as unique_tracks,
                   COUNT(DISTINCT le.artist_id) as unique_artists
            FROM listening_events le
            GROUP BY period"""
    ).fetchall()

    # Aggregate per period
    periods = defaultdict(
        lambda: {
            "genres": Counter(),
            "artists": Counter(),
            "plays": 0,
            "unique_tracks": 0,
            "unique_artists": 0,
        }
    )

    for r in play_totals:
        periods[r["period"]]["plays"] = r["plays"]
        periods[r["period"]]["unique_tracks"] = r["unique_tracks"]
        periods[r["period"]]["unique_artists"] = r["unique_artists"]

    for r in genre_evolution:
        periods[r["period"]]["genres"][r["genre"]] += r["play_count"]

    for r in artist_evolution:
        periods[r["period"]]["artists"][r["artist_name"]] += r["play_count"]
    
    # Build evolution timeline
    timeline = []
    sorted_periods = sorted(periods.keys())
    for p in sorted_periods:
        data = periods[p]
        top_genres = data["genres"].most_common(5)
        top_artists = data["artists"].most_common(5)
        
        # Diversity metrics.  A play carries every genre its artist is tagged
        # with, so the genre distribution is normalised by the genre-play
        # total rather than the play count — otherwise the shares sum past
        # 100% and the Shannon index is scaled by the tagging density.
        genre_plays = sum(data["genres"].values())
        shannon = -sum(
            (c / genre_plays) * math.log(c / genre_plays)
            for c in data["genres"].values() if c > 0
        ) if genre_plays > 0 else 0
        
        timeline.append({
            "period": p,
            "total_plays": data["plays"],
            "unique_artists": data["unique_artists"],
            "unique_tracks": data["unique_tracks"],
            "top_genres": [
                {"genre": g, "plays": c, "share": round(c / genre_plays * 100, 1) if genre_plays else 0}
                for g, c in top_genres
            ],
            "top_artists": [{"artist": a, "plays": c} for a, c in top_artists],
            "genre_diversity": round(shannon, 3),
        })
    
    # Detect significant shifts
    shifts = []
    if len(timeline) >= 2:
        for i in range(1, len(timeline)):
            prev = timeline[i-1]
            curr = timeline[i]
            # Genre shift: top genre changed
            prev_top = prev["top_genres"][0]["genre"] if prev["top_genres"] else None
            curr_top = curr["top_genres"][0]["genre"] if curr["top_genres"] else None
            if prev_top != curr_top and prev_top and curr_top:
                shifts.append({
                    "type": "genre_shift",
                    "from_period": prev["period"],
                    "to_period": curr["period"],
                    "from_genre": prev_top,
                    "to_genre": curr_top,
                })
            
            # Diversity shift > 20%
            if prev["genre_diversity"] > 0:
                diversity_change = abs(curr["genre_diversity"] - prev["genre_diversity"]) / prev["genre_diversity"]
                if diversity_change > 0.2:
                    shifts.append({
                        "type": "diversity_shift",
                        "from_period": prev["period"],
                        "to_period": curr["period"],
                        "change": round(diversity_change * 100, 1),
                        "direction": "increased" if curr["genre_diversity"] > prev["genre_diversity"] else "decreased",
                    })
    
    return {
        "period": period,
        "timeline": timeline,
        "shifts": shifts,
        "total_periods": len(timeline),
        "earliest_period": sorted_periods[0] if sorted_periods else None,
        "latest_period": sorted_periods[-1] if sorted_periods else None,
    }


def compute_music_dna(db) -> Dict[str, Any]:
    """Calculate Music DNA dimensions (bipolar scales 0-100)."""
    results = {}
    
    # Get listening events with audio features
    data = db.execute(
        """SELECT 
           af.danceability, af.energy, af.valence, af.acousticness, af.instrumentalness,
           t.explicit, a.name as artist_name, ag.genre, t.duration_ms
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           JOIN artists a ON t.artist_id = a.id
           LEFT JOIN audio_features af ON t.id = af.track_id
           LEFT JOIN artist_genres ag ON a.id = ag.artist_id"""
    ).fetchall()
    
    if not data:
        return {"dna": {}, "note": "Insufficient data for DNA analysis"}
    
    # Convert rows to dicts
    data = [dict(row) for row in data]
    
    # 1. Indie ↔ Mainstream (based on artist popularity)
    indie_score = 0
    mainstream_score = 0
    for row in data:
        artist_pop = db.execute(
            "SELECT popularity FROM artists WHERE id=?", (row["artist_name"],)
        ).fetchone()
        if artist_pop and artist_pop["popularity"]:
            pop = artist_pop["popularity"]
            if pop < 40:
                indie_score += 1
            elif pop > 60:
                mainstream_score += 1
    
    total = indie_score + mainstream_score
    if total > 0:
        results["indie_vs_mainstream"] = {
            "indie": round(indie_score / total * 100, 1),
            "mainstream": round(mainstream_score / total * 100, 1),
            "label": "Indie-leaning" if indie_score > mainstream_score else ("Mainstream-leaning" if mainstream_score > indie_score else "Balanced"),
        }
    else:
        results["indie_vs_mainstream"] = {"indie": 50, "mainstream": 50, "label": "Unknown"}
    
    # 2. Discovery ↔ Familiarity
    track_counts = Counter(row["artist_name"] for row in data)
    unique_tracks = len(set(row["artist_name"] for row in data))
    repeated = sum(1 for c in track_counts.values() if c > 1)
    total_artist_plays = len(data)
    
    if total_artist_plays > 0:
        discovery_pct = round((unique_tracks / total_artist_plays) * 100, 1)
        results["discovery_vs_familiarity"] = {
            "discovery": discovery_pct,
            "familiarity": round(100 - discovery_pct, 1),
            "label": "Exploratory" if discovery_pct > 60 else ("Habitual" if discovery_pct < 30 else "Balanced"),
        }
    else:
        results["discovery_vs_familiarity"] = {"discovery": 50, "familiarity": 50, "label": "Unknown"}
    
    # 3. Old ↔ New (based on album release dates)
    # Use top tracks snapshot date ranges as proxy
    recent_tracks = db.execute(
        "SELECT COUNT(*) FROM top_tracks_snapshots WHERE time_range='short_term'"
    ).fetchone()[0]
    long_tracks = db.execute(
        "SELECT COUNT(*) FROM top_tracks_snapshots WHERE time_range='long_term'"
    ).fetchone()[0]
    
    total_top = recent_tracks + long_tracks
    if total_top > 0:
        results["old_vs_new"] = {
            "new": round(recent_tracks / total_top * 100, 1),
            "old": round(long_tracks / total_top * 100, 1),
            "label": "Current-focused" if recent_tracks > long_tracks else ("Catalog-focused" if long_tracks > recent_tracks else "Balanced"),
        }
    else:
        results["old_vs_new"] = {"new": 50, "old": 50, "label": "Unknown"}
    
    # 4. Genre-focused ↔ Genre-diverse
    genre_counts = Counter(row["genre"] for row in data if row["genre"])
    if genre_counts:
        top_genre_share = genre_counts.most_common(1)[0][1] / len(data) * 100
        results["genre_focused_vs_diverse"] = {
            "focused": round(top_genre_share, 1),
            "diverse": round(100 - top_genre_share, 1),
            "label": "Genre-focused" if top_genre_share > 40 else ("Genre-diverse" if top_genre_share < 20 else "Balanced"),
            "top_genre": genre_counts.most_common(1)[0][0],
        }
    else:
        results["genre_focused_vs_diverse"] = {"focused": 50, "diverse": 50, "label": "Unknown"}
    
    # 5. Artist-loyal ↔ Artist-exploratory
    artist_play_counts = Counter(row["artist_name"] for row in data)
    top_artist_plays = artist_play_counts.most_common(1)[0][1] if artist_play_counts else 0
    artist_concentration = round(top_artist_plays / len(data) * 100, 1) if len(data) > 0 else 0
    
    results["artist_loyal_vs_exploratory"] = {
        "loyal": artist_concentration,
        "exploratory": round(100 - artist_concentration, 1),
        "label": "Artist-loyal" if artist_concentration > 30 else ("Artist-exploratory" if artist_concentration < 10 else "Balanced"),
        "top_artist": artist_play_counts.most_common(1)[0][0] if artist_play_counts else None,
    }
    
    # 6. Album listener ↔ Singles listener
    # Check if the listener plays full albums (track_number sequence)
    album_tracks = db.execute(
        """SELECT COUNT(DISTINCT le.track_id) as tracks, COUNT(*) as plays
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           WHERE t.disc_number IS NOT NULL AND t.track_number IS NOT NULL"""
    ).fetchone()
    
    total_tracks = db.execute("SELECT COUNT(DISTINCT track_id) FROM listening_events").fetchone()[0]
    if total_tracks > 0 and album_tracks:
        album_track_pct = round(album_tracks["tracks"] / total_tracks * 100, 1)
        results["album_listener_vs_singles"] = {
            "album_leaning": album_track_pct,
            "singles_leaning": round(100 - album_track_pct, 1),
            "label": "Album-oriented" if album_track_pct > 60 else ("Singles-oriented" if album_track_pct < 30 else "Mixed"),
        }
    else:
        results["album_listener_vs_singles"] = {"album_leaning": 50, "singles_leaning": 50, "label": "Unknown"}
    
    # 7. High-energy ↔ Low-energy
    energies = [row["energy"] for row in data if row["energy"] is not None]
    if energies:
        avg_energy = sum(energies) / len(energies)
        results["high_energy_vs_low_energy"] = {
            "high_energy": round(avg_energy * 100, 1),
            "low_energy": round((1 - avg_energy) * 100, 1),
            "label": "High-energy listener" if avg_energy > 0.6 else ("Low-energy/chill listener" if avg_energy < 0.35 else "Balanced energy"),
            "average_energy": round(avg_energy, 3),
        }
    else:
        results["high_energy_vs_low_energy"] = {"high_energy": 50, "low_energy": 50, "label": "Unknown"}
    
    # 8. Acoustic ↔ Electronic
    acousticness_values = [row["acousticness"] for row in data if row["acousticness"] is not None]
    if acousticness_values:
        avg_acoustic = sum(acousticness_values) / len(acousticness_values)
        results["acoustic_vs_electronic"] = {
            "acoustic": round(avg_acoustic * 100, 1),
            "electronic": round((1 - avg_acoustic) * 100, 1),
            "label": "Acoustic-leaning" if avg_acoustic > 0.5 else ("Electronic-leaning" if avg_acoustic < 0.2 else "Balanced"),
            "average_acousticness": round(avg_acoustic, 3),
        }
    else:
        results["acoustic_vs_electronic"] = {"acoustic": 50, "electronic": 50, "label": "Unknown (no audio features)"}
    
    # 9. Positive ↔ Melancholic (valence)
    valence_values = [row["valence"] for row in data if row["valence"] is not None]
    if valence_values:
        avg_valence = sum(valence_values) / len(valence_values)
        results["positive_vs_melancholic"] = {
            "positive": round(avg_valence * 100, 1),
            "melancholic": round((1 - avg_valence) * 100, 1),
            "label": "Positive/uplifting" if avg_valence > 0.6 else ("Melancholic/introspective" if avg_valence < 0.35 else "Balanced mood"),
            "average_valence": round(avg_valence, 3),
        }
    else:
        results["positive_vs_melancholic"] = {"positive": 50, "melancholic": 50, "label": "Unknown (no audio features)"}
    
    return {"dna": results, "total_data_points": len(data)}


def compute_time_of_day_analysis(db) -> Dict[str, Any]:
    """Time-of-day and day-of-week listening patterns."""
    # Hour of day analysis
    hour_data = db.execute(
        """SELECT strftime('%H', timestamp, 'unixepoch') as hour, COUNT(*) as plays,
           COUNT(DISTINCT track_id) as unique_tracks
           FROM listening_events
           GROUP BY hour
           ORDER BY hour"""
    ).fetchall()
    
    hours = {}
    for h in hour_data:
        hours[h["hour"]] = {"plays": h["plays"], "unique_tracks": h["unique_tracks"]}
    
    # Day of week
    dow_data = db.execute(
        """SELECT strftime('%w', timestamp, 'unixepoch') as dow, COUNT(*) as plays,
           COUNT(DISTINCT track_id) as unique_tracks
           FROM listening_events
           GROUP BY dow
           ORDER BY dow"""
    ).fetchall()
    
    days = {
        "0": "Sunday", "1": "Monday", "2": "Tuesday", "3": "Wednesday",
        "4": "Thursday", "5": "Friday", "6": "Saturday"
    }
    dow = {}
    for d in dow_data:
        dow[days.get(d["dow"], "Unknown")] = {"plays": d["plays"], "unique_tracks": d["unique_tracks"]}
    
    # Time-of-day classification
    morning = sum(hours.get(h, {}).get("plays", 0) for h in [6,7,8,9,10,11])
    afternoon = sum(hours.get(h, {}).get("plays", 0) for h in [12,13,14,15,16,17])
    evening = sum(hours.get(h, {}).get("plays", 0) for h in [18,19,20,21,22])
    late_night = sum(hours.get(h, {}).get("plays", 0) for h in [23,0,1,2,3,4,5])
    
    total = morning + afternoon + evening + late_night
    
    # Genre by time of day
    def genre_by_hour_range(hour_range):
        result = db.execute(
            f"""SELECT ag.genre, COUNT(*) as plays
                FROM listening_events le
                JOIN tracks t ON le.track_id = t.id
                JOIN artist_genres ag ON t.artist_id = ag.artist_id
                WHERE strftime('%H', le.timestamp, 'unixepoch') IN ({','.join('?' for _ in hour_range)})
                GROUP BY ag.genre
                ORDER BY plays DESC
                LIMIT 5""",
            hour_range,
        ).fetchall()
        return [{"genre": r["genre"], "plays": r["plays"]} for r in result]
    
    return {
        "hourly_breakdown": hours,
        "daily_breakdown": dow,
        "time_of_day": {
            "morning": {"plays": morning, "share": round(morning/total*100, 1) if total else 0},
            "afternoon": {"plays": afternoon, "share": round(afternoon/total*100, 1) if total else 0},
            "evening": {"plays": evening, "share": round(evening/total*100, 1) if total else 0},
            "late_night": {"plays": late_night, "share": round(late_night/total*100, 1) if total else 0},
        },
        "peak_hour": max(hours, key=lambda h: hours[h]["plays"]) if hours else None,
        "peak_day": max(dow, key=lambda d: dow[d]["plays"]) if dow else None,
        "morning_genres": genre_by_hour_range([6,7,8,9,10,11]),
        "evening_genres": genre_by_hour_range([18,19,20,21,22]),
        "late_night_genres": genre_by_hour_range([23,0,1,2,3,4,5]),
    }


def compute_session_analysis(db) -> Dict[str, Any]:
    """Inferred listening sessions from playback timestamps."""
    events = db.execute(
        """SELECT played_at, track_id, artist_id, album_id
           FROM listening_events
           ORDER BY played_at"""
    ).fetchall()
    
    if not events:
        return {"sessions": [], "total_sessions": 0, "note": "No listening events"}
    
    # Infer sessions: gap > 30 minutes = new session
    SESSION_GAP_SECONDS = 1800
    
    sessions = []
    current_session = {
        "start": events[0]["played_at"],
        "end": events[0]["played_at"],
        "tracks": [events[0]["track_id"]],
        "artists": {events[0]["artist_id"]},
        "albums": {events[0]["album_id"]},
    }
    
    for i in range(1, len(events)):
        e = events[i]
        gap = e["played_at"] - current_session["end"]
        
        if gap > SESSION_GAP_SECONDS:
            # Close current session
            sessions.append(current_session)
            current_session = {
                "start": e["played_at"],
                "end": e["played_at"],
                "tracks": [e["track_id"]],
                "artists": {e["artist_id"]},
                "albums": {e["album_id"]},
            }
        else:
            current_session["end"] = e["played_at"]
            current_session["tracks"].append(e["track_id"])
            if e["artist_id"]:
                current_session["artists"].add(e["artist_id"])
            if e["album_id"]:
                current_session["albums"].add(e["album_id"])
    
    # Don't forget the last session
    sessions.append(current_session)
    
    # Compute session metrics
    session_metrics = []
    for s in sessions:
        duration = s["end"] - s["start"]
        session_metrics.append({
            "start": datetime.fromtimestamp(s["start"], tz=timezone.utc).isoformat(),
            "end": datetime.fromtimestamp(s["end"], tz=timezone.utc).isoformat(),
            "duration_sec": duration,
            "duration_min": round(duration / 60, 1),
            "track_count": len(s["tracks"]),
            "unique_artists": len(s["artists"]),
            "unique_albums": len(s["albums"]),
        })
    
    # Convert to list of dicts with explicit keys
    sessions_output = []
    for s in session_metrics:
        sessions_output.append({
            "start": s["start"],
            "end": s["end"],
            "duration_sec": s["duration_sec"],
            "duration_min": s["duration_min"],
            "track_count": s["track_count"],
            "unique_artists": s["unique_artists"],
            "unique_albums": s["unique_albums"],
        })
    
    # Aggregate stats
    durations = [s["duration_sec"] for s in sessions_output]
    track_counts = [s["track_count"] for s in sessions_output]
    
    return {
        "total_sessions": len(sessions),
        "avg_session_duration_min": round(mean(durations) / 60, 1) if durations else 0,
        "median_session_duration_min": round(median(durations) / 60, 1) if durations else 0,
        "longest_session_min": round(max(durations) / 60, 1) if durations else 0,
        "shortest_session_min": round(min(durations) / 60, 1) if durations else 0,
        "avg_tracks_per_session": round(mean(track_counts), 1) if track_counts else 0,
        "max_tracks_in_session": max(track_counts) if track_counts else 0,
        "sessions": session_metrics[-20:],  # Last 20 sessions
        "session_gap_minutes": SESSION_GAP_SECONDS / 60,
    }


def compute_listener_archetype(db) -> Dict[str, Any]:
    """Generate a listener archetype from measurable characteristics."""
    dna = compute_music_dna(db)
    total = compute_total_listening(db)
    repeat = compute_repeat_rate(db)
    discovery = compute_discovery_rate(db)
    genre_div = compute_genre_diversity(db)
    loyalty = compute_artist_loyalty(db)
    audio = compute_audio_characteristics(db)
    
    archetype_signals = []
    
    # Signal 1: High repeat rate + high artist loyalty = "Loyalist"
    if repeat["repeat_rate_artists"] > 50 and loyalty["loyalty_score"] > 2:
        archetype_signals.append(("loyalist", "High artist loyalty with frequent replays"))
    
    # Signal 2: High genre diversity + low concentration = "Genre Nomad"
    if genre_div["diversity_score"] > 60 and genre_div["genre_count"] > 10:
        archetype_signals.append(("genre_nomad", f"Wide genre diversity across {genre_div['genre_count']} genres"))
    
    # Signal 3: High discovery rate = "Explorer"
    if discovery["discovery_rate"] > 40:
        archetype_signals.append(("explorer", f"Discovers new tracks at {discovery['discovery_rate']}% rate"))
    
    # Signal 4: High album depth = "Album Diver"
    album = compute_album_loyalty(db)
    if album["album_loyalty_score"] > 1.5:
        archetype_signals.append(("album_diver", f"Deep album listening (avg depth {album['album_loyalty_score']}x)"))
    
    # Signal 5: High energy + high valence = "Energetic Optimist"
    if audio["audio_characteristics"].get("energy", 0) and audio["audio_characteristics"].get("valence", 0):
        if audio["audio_characteristics"]["energy"] > 0.6 and audio["audio_characteristics"]["valence"] > 0.5:
            archetype_signals.append(("energetic_optimist", "High-energy, positive-leaning listening"))
    
    # Signal 6: Low valence + high acousticness = "Melancholic Acoustic"
    if audio["audio_characteristics"].get("valence", 0) and audio["audio_characteristics"].get("acousticness", 0):
        if audio["audio_characteristics"]["valence"] < 0.4 and audio["audio_characteristics"]["acousticness"] > 0.3:
            archetype_signals.append(("melancholic_acoustic", "Introspective, acoustic-leaning listening"))
    
    # Signal 7: High mainstream score = "Pop Connoisseur"
    mainstream = compute_mainstream_vs_obscure(db)
    if mainstream["tendency"] == "mainstream":
        archetype_signals.append(("pop_connoisseur", f"leans towards popular artists (avg popularity {mainstream['average_artist_popularity']})"))
    
    # Signal 8: New music affinity > 50% = "Trend Follower"
    new_music = compute_new_music_affinity(db)
    if new_music["new_music_affinity"] > 50:
        archetype_signals.append(("trend_follower", f"Listens to recent music ({new_music['new_music_affinity']}% from last 5 years)"))
    
    # Determine primary archetype
    archetype_counts = Counter(signal[0] for signal in archetype_signals)
    primary = archetype_counts.most_common(1)[0][0] if archetype_counts else "listener"
    
    # Build archetype label
    archetype_labels = {
        "loyalist": "The Loyalist",
        "genre_nomad": "The Genre Nomad",
        "explorer": "The Explorer",
        "album_diver": "The Album Diver",
        "energetic_optimist": "The Energetic Optimist",
        "melancholic_acoustic": "The Melancholic Acoustic",
        "pop_connoisseur": "The Pop Connoisseur",
        "trend_follower": "The Trend Follower",
    }
    
    label = archetype_labels.get(primary, "The Listener")
    
    # Supporting evidence
    evidence = []
    for signal_type, signal_desc in archetype_signals:
        evidence.append({
            "signal": signal_type,
            "description": signal_desc,
        })
    
    return {
        "archetype": label,
        "archetype_key": primary,
        "archetype_signals": evidence,
        "supporting_metrics": {
            "total_plays": total["total_plays"],
            "unique_artists": total["unique_artists"],
            "unique_tracks": total["unique_tracks"],
            "genre_count": genre_div["genre_count"],
            "repeat_rate": repeat["repeat_rate_artists"],
            "discovery_rate": discovery["discovery_rate"],
            "avg_artist_popularity": mainstream["average_artist_popularity"],
        },
        "all_signals": archetype_signals,
    }


def compute_anomalies(db) -> Dict[str, Any]:
    """Detect interesting anomalies and patterns."""
    findings = []
    
    # 1. Most replayed tracks (potential obsessions)
    obsessed_tracks = db.execute(
        """SELECT t.name, t.artist_name, COUNT(*) as plays, 
                GROUP_CONCAT(DISTINCT strftime('%Y-%m', le.timestamp, 'unixepoch')) as months_active
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           GROUP BY le.track_id
           HAVING COUNT(*) >= 5
           ORDER BY plays DESC
           LIMIT 5"""
    ).fetchall()
    
    for t in obsessed_tracks:
        findings.append({
            "type": "obsessive_replay",
            "entity_type": "track",
            "entity": t["name"],
            "artist": t["artist_name"],
            "plays": t["plays"],
            "months_active": t["months_active"],
            "description": f"'{t['name']}' by {t['artist_name']} replayed {t['plays']} times across {t['months_active']} months",
        })
    
    # 2. Most replayed artists
    obsessed_artists = db.execute(
        """SELECT a.name, COUNT(*) as plays, COUNT(DISTINCT le.track_id) as unique_tracks,
                GROUP_CONCAT(DISTINCT strftime('%Y-%m', le.timestamp, 'unixepoch')) as months_active
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           JOIN artists a ON t.artist_id = a.id
           GROUP BY a.id
           HAVING COUNT(*) >= 10
           ORDER BY plays DESC
           LIMIT 5"""
    ).fetchall()
    
    for a in obsessed_artists:
        findings.append({
            "type": "artist_dominance",
            "entity_type": "artist",
            "entity": a["name"],
            "plays": a["plays"],
            "unique_tracks": a["unique_tracks"],
            "months_active": a["months_active"],
            "description": f"'{a['name']}' dominates your listening with {a['plays']} plays across {a['unique_tracks']} tracks over {a['months_active']} months",
        })
    
    # 3. Genre spikes (unexpected genre combinations)
    genre_pairs = db.execute(
        """SELECT ag1.genre as genre1, ag2.genre as genre2, COUNT(*) as co_plays
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           JOIN artist_genres ag1 ON t.artist_id = ag1.artist_id
           JOIN artist_genres ag2 ON t.artist_id = ag2.artist_id
           WHERE ag1.genre < ag2.genre
           GROUP BY ag1.genre, ag2.genre
           ORDER BY co_plays DESC
           LIMIT 5"""
    ).fetchall()
    
    for gp in genre_pairs:
        findings.append({
            "type": "genre_combination",
            "genres": [gp["genre1"], gp["genre2"]],
            "co_plays": gp["co_plays"],
            "description": f"Unusual genre pairing: {gp['genre1']} + {gp['genre2']} ({gp['co_plays']} plays together)",
        })
    
    # 4. Long sessions
    sessions = db.execute(
        """SELECT 
           MIN(played_at) as start, MAX(played_at) as end, 
           COUNT(*) as tracks, COUNT(DISTINCT track_id) as unique_tracks,
           GROUP_CONCAT(DISTINCT strftime('%H:%M', timestamp, 'unixepoch')) as times,
           GROUP_CONCAT(DISTINCT ag.genre) as genres
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           LEFT JOIN artist_genres ag ON t.artist_id = ag.artist_id
           GROUP BY 
             CAST(played_at / {gap} AS INTEGER)
           HAVING COUNT(*) >= 10
           ORDER BY COUNT(*) DESC
           LIMIT 3""".format(gap=1800)
    ).fetchall()
    
    for s in sessions:
        duration_min = (s["end"] - s["start"]) / 60
        findings.append({
            "type": "long_session",
            "duration_min": round(duration_min, 1),
            "tracks": s["tracks"],
            "unique_tracks": s["unique_tracks"],
            "times": s["times"],
            "genres": s["genres"],
            "description": f"Extended listening session: {round(duration_min, 1)} minutes, {s['tracks']} tracks ({s['unique_tracks']} unique), genres: {s['genres']}",
        })
    
    # 5. Forgotten artists returning
    artist_months = db.execute(
        """SELECT a.name, strftime('%Y-%m', le.timestamp, 'unixepoch') as month, COUNT(*) as plays
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           JOIN artists a ON t.artist_id = a.id
           GROUP BY a.id, month
           ORDER BY a.name, month"""
    ).fetchall()
    
    # Find artists with gaps
    artist_month_map = defaultdict(list)
    for am in artist_months:
        artist_month_map[am["name"]].append(am["month"])
    
    for artist, months in artist_month_map.items():
        if len(months) >= 3:
            sorted_months = sorted(set(months))
            for i in range(1, len(sorted_months)):
                prev = sorted_months[i-1]
                curr = sorted_months[i]
                try:
                    prev_dt = datetime.strptime(prev, "%Y-%m")
                    curr_dt = datetime.strptime(curr, "%Y-%m")
                    gap_months = (curr_dt.year - prev_dt.year) * 12 + (curr_dt.month - prev_dt.month)
                    if gap_months >= 6:
                        findings.append({
                            "type": "returning_artist",
                            "artist": artist,
                            "gap_months": gap_months,
                            "last_seen": prev,
                            "returned": curr,
                            "description": f"'{artist}' returned after {gap_months} months (last heard {prev}, back in {curr})",
                        })
                except ValueError:
                    pass
    
    # 6. Tracks spanning multiple years
    long_lived = db.execute(
        """SELECT t.name, t.artist_name, 
                MIN(strftime('%Y', le.timestamp, 'unixepoch')) as first_year,
                MAX(strftime('%Y', le.timestamp, 'unixepoch')) as last_year,
                COUNT(*) as plays, COUNT(DISTINCT strftime('%Y', le.timestamp, 'unixepoch')) as years_active
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           GROUP BY le.track_id
           HAVING years_active >= 2
           ORDER BY years_active DESC
           LIMIT 5"""
    ).fetchall()
    
    for ll in long_lived:
        findings.append({
            "type": "long_lived_track",
            "entity": ll["name"],
            "artist": ll["artist_name"],
            "years_active": ll["years_active"],
            "first_year": ll["first_year"],
            "last_year": ll["last_year"],
            "plays": ll["plays"],
            "description": f"'{ll['name']}' by {ll['artist_name']} has been in your rotation for {ll['years_active']} years ({ll['first_year']}-{ll['last_year']}), with {ll['plays']} total plays",
        })
    
    return {"findings": findings, "total_findings": len(findings)}


def compute_recommendations(db) -> Dict[str, Any]:
    """Generate recommendations based on the listening graph."""
    recs = []
    
    # 1. Artists adjacent to top artists (same genres, not yet listened)
    top_artist_ids = db.execute(
        "SELECT artist_id FROM top_artists_snapshots WHERE time_range='long_term' AND rank <= 10"
    ).fetchall()
    
    if top_artist_ids:
        artist_id_list = [a["artist_id"] for a in top_artist_ids]
        
        # Find genres of top artists
        top_genres = db.execute(
            f"SELECT DISTINCT genre FROM artist_genres WHERE artist_id IN ({','.join('?' for _ in artist_id_list)})",
            artist_id_list,
        ).fetchall()
        
        if top_genres:
            genre_list = [g["genre"] for g in top_genres]
            
            # Find artists in those genres NOT in top artists
            adjacent = db.execute(
                f"""SELECT a.id, a.name, a.genres, a.popularity, COUNT(ag.genre) as genre_overlap
                    FROM artists a
                    JOIN artist_genres ag ON a.id = ag.artist_id
                    WHERE ag.genre IN ({','.join('?' for _ in genre_list)})
                    AND a.id NOT IN ({','.join('?' for _ in artist_id_list)})
                    AND a.id NOT IN (SELECT DISTINCT artist_id FROM listening_events)
                    GROUP BY a.id
                    HAVING genre_overlap >= 2
                    ORDER BY a.popularity DESC
                    LIMIT 10""",
                genre_list + artist_id_list,
            ).fetchall()
            
            for a in adjacent:
                recs.append({
                    "type": "adjacent_artist",
                    "artist": a["name"],
                    "genres": a["genres"],
                    "popularity": a["popularity"],
                    "genre_overlap": a["genre_overlap"],
                    "reason": f"Shares {a['genre_overlap']} genres with your top artists but isn't in your library yet",
                })
    
    # 2. Deep-cut recommendations from saved tracks' artists
    saved_artist_ids = db.execute(
        """SELECT DISTINCT t.artist_id
           FROM saved_tracks st
           JOIN tracks t ON st.track_id = t.id"""
    ).fetchall()
    
    if saved_artist_ids:
        sa_ids = [a["artist_id"] for a in saved_artist_ids]
        
        deep_cuts = db.execute(
            f"""SELECT t.id, t.name, t.artist_name, t.album_name, t.popularity, t.duration_ms
                FROM tracks t
                WHERE t.artist_id IN ({','.join('?' for _ in sa_ids)})
                AND t.id NOT IN (SELECT track_id FROM listening_events)
                AND t.popularity IS NOT NULL
                ORDER BY t.popularity DESC
                LIMIT 10""",
            sa_ids,
        ).fetchall()
        
        for t in deep_cuts:
            recs.append({
                "type": "deep_cut",
                "track": t["name"],
                "artist": t["artist_name"],
                "album": t["album_name"],
                "popularity": t["popularity"],
                "reason": f"From an artist you've saved but haven't played — '{t['album_name']}'",
            })
    
    # 3. Genre expansion recommendations
    dominant_genres = db.execute(
        """SELECT ag.genre, COUNT(*) as plays
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           JOIN artist_genres ag ON t.artist_id = ag.artist_id
           GROUP BY ag.genre
           ORDER BY plays DESC
           LIMIT 3"""
    ).fetchall()
    
    if dominant_genres:
        for dg in dominant_genres:
            # Find related genres (same family, different specific genre)
            family = normalize_genre(dg["genre"])
            related = db.execute(
                f"""SELECT ag.genre, COUNT(DISTINCT a.id) as artist_count
                    FROM artist_genres ag
                    JOIN artists a ON ag.artist_id = a.id
                    WHERE ag.genre != ? AND ag.genre IN (
                        SELECT genre FROM artist_genres WHERE artist_id IN (
                            SELECT artist_id FROM listening_events
                        )
                    )
                    AND ? != ag.genre
                    GROUP BY ag.genre
                    ORDER BY artist_count DESC
                    LIMIT 3""",
                (dg["genre"], dg["genre"]),
            ).fetchall()
            
            for r in related:
                recs.append({
                    "type": "genre_expansion",
                    "from_genre": dg["genre"],
                    "to_genre": r["genre"],
                    "artist_count": r["artist_count"],
                    "reason": f"You listen to {dg['genre']} — consider exploring {r['genre']} (shared listener base)",
                })
    
    return {"recommendations": recs, "total_recommendations": len(recs)}


def compute_discovery_events(db) -> Dict[str, Any]:
    """Identify new discoveries (first time listening to an artist/track)."""
    discoveries = []
    
    # New artists (first appearance)
    new_artists = db.execute(
        """SELECT DISTINCT a.id, a.name, MIN(le.played_at) as first_listen,
                GROUP_CONCAT(DISTINCT ag.genre) as genres
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           JOIN artists a ON t.artist_id = a.id
           LEFT JOIN artist_genres ag ON a.id = ag.artist_id
           GROUP BY a.id
           ORDER BY first_listen DESC
           LIMIT 20"""
    ).fetchall()
    
    for na in new_artists:
        discoveries.append({
            "type": "artist_discovery",
            "entity_id": na["id"],
            "entity_name": na["name"],
            "first_listened": datetime.fromtimestamp(na["first_listen"], tz=timezone.utc).isoformat(),
            "genres": na["genres"].split(",") if na["genres"] else [],
        })
    
    # New tracks
    new_tracks = db.execute(
        """SELECT DISTINCT t.id, t.name, t.artist_name, MIN(le.played_at) as first_listen,
                t.album_name
           FROM listening_events le
           JOIN tracks t ON le.track_id = t.id
           GROUP BY t.id
           ORDER BY first_listen DESC
           LIMIT 20"""
    ).fetchall()
    
    for nt in new_tracks:
        discoveries.append({
            "type": "track_discovery",
            "entity_id": nt["id"],
            "entity_name": nt["name"],
            "artist": nt["artist_name"],
            "album": nt["album_name"],
            "first_listened": datetime.fromtimestamp(nt["first_listen"], tz=timezone.utc).isoformat(),
        })
    
    return {"discoveries": discoveries, "total_discoveries": len(discoveries)}


def run_all_analytics() -> Dict[str, Any]:
    """Run all analytics and return a complete intelligence package."""
    print("[analytics] Computing listener intelligence...")
    db = get_db()
    
    results = {}
    
    # Core metrics
    print("[analytics]   total listening...")
    results["total_listening"] = compute_total_listening(db)
    
    print("[analytics]   listening frequency...")
    results["listening_frequency"] = compute_listening_frequency(db)
    
    print("[analytics]   repeat rate...")
    results["repeat_rate"] = compute_repeat_rate(db)
    
    print("[analytics]   discovery rate...")
    results["discovery_rate"] = compute_discovery_rate(db)
    
    print("[analytics]   artist loyalty...")
    results["artist_loyalty"] = compute_artist_loyalty(db)
    
    print("[analytics]   genre diversity...")
    results["genre_diversity"] = compute_genre_diversity(db)
    
    print("[analytics]   genre loyalty...")
    results["genre_loyalty"] = compute_genre_loyalty(db)
    
    print("[analytics]   album loyalty...")
    results["album_loyalty"] = compute_album_loyalty(db)
    
    print("[analytics]   mainstream vs obscure...")
    results["mainstream_vs_obscure"] = compute_mainstream_vs_obscure(db)
    
    print("[analytics]   new music affinity...")
    results["new_music_affinity"] = compute_new_music_affinity(db)
    
    print("[analytics]   explicit content...")
    results["explicit_content"] = compute_explicit_content_tendency(db)
    
    print("[analytics]   audio characteristics...")
    results["audio_characteristics"] = compute_audio_characteristics(db)
    
    print("[analytics]   music DNA...")
    results["music_dna"] = compute_music_dna(db)
    
    print("[analytics]   taste evolution...")
    results["taste_evolution"] = compute_taste_evolution(db, "month")
    results["taste_evolution_yearly"] = compute_taste_evolution(db, "year")
    
    print("[analytics]   time of day...")
    results["time_of_day"] = compute_time_of_day_analysis(db)
    
    print("[analytics]   session analysis...")
    results["sessions"] = compute_session_analysis(db)
    
    print("[analytics]   listener archetype...")
    results["listener_archetype"] = compute_listener_archetype(db)
    
    print("[analytics]   anomalies...")
    results["anomalies"] = compute_anomalies(db)
    
    print("[analytics]   recommendations...")
    results["recommendations"] = compute_recommendations(db)
    
    print("[analytics]   discoveries...")
    results["discoveries"] = compute_discovery_events(db)
    
    # Top N lists
    print("[analytics]   top artists...")
    results["top_artists_long"] = compute_top_n(db, "top_artists_snapshots", "artist_id", 20, "time_range='long_term'")
    results["top_artists_medium"] = compute_top_n(db, "top_artists_snapshots", "artist_id", 20, "time_range='medium_term'")
    results["top_artists_short"] = compute_top_n(db, "top_artists_snapshots", "artist_id", 20, "time_range='short_term'")
    
    print("[analytics]   top tracks...")
    results["top_tracks_long"] = compute_top_n(db, "top_tracks_snapshots", "track_id", 20, "time_range='long_term'")
    results["top_tracks_medium"] = compute_top_n(db, "top_tracks_snapshots", "track_id", 20, "time_range='medium_term'")
    results["top_tracks_short"] = compute_top_n(db, "top_tracks_snapshots", "track_id", 20, "time_range='short_term'")
    
    # Saved library
    print("[analytics]   library...")
    results["saved_tracks_count"] = db.execute("SELECT COUNT(*) FROM saved_tracks").fetchone()[0]
    results["saved_albums_count"] = db.execute("SELECT COUNT(*) FROM saved_albums").fetchone()[0]
    results["playlists"] = db.execute(
        "SELECT id, name, description, tracks_total, public, collaborative FROM playlists ORDER BY name"
    ).fetchall()
    
    db.close()
    
    print(f"[analytics] Complete — {len(results)} metric groups computed")
    return results


def save_analytics_cache(results: Dict[str, Any]) -> None:
    """Save analytics results to cache table for dashboard consumption."""
    db = get_db()
    cache_key = "full_intelligence"
    existing = db.execute(
        "SELECT key FROM analytics_cache WHERE key=?", (cache_key,)
    ).fetchone()
    
    db.execute(
        """INSERT OR REPLACE INTO analytics_cache (key, value, computed_at)
           VALUES (?, ?, ?)""",
        (cache_key, json.dumps(results, ensure_ascii=False, default=str), os.path.getmtime(__file__)),
    )
    db.commit()
    db.close()
    print(f"[analytics] Cached intelligence to analytics_cache")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Spotify analytics engine")
    parser.add_argument("--cache", action="store_true", help="Save results to analytics cache")
    args = parser.parse_args()
    
    results = run_all_analytics()
    
    # Print summary
    print("\n" + "="*60)
    print("SPOTIFY LISTENER INTELLIGENCE SUMMARY")
    print("="*60)
    
    tl = results["total_listening"]
    print(f"\nTotal Listening: {tl['total_plays']} plays, {tl['unique_artists']} artists, {tl['unique_tracks']} tracks")
    print(f"  {tl['total_listening_hours']} hours over {tl['date_range_days']:.0f} days")
    
    rr = results["repeat_rate"]
    print(f"\nRepeat Rate: {rr['repeat_rate_tracks']}% of tracks replayed, {rr['repeat_rate_artists']}% of artists")
    
    dr = results["discovery_rate"]
    print(f"\nDiscovery: {dr['discovery_rate']}% one-time tracks ({dr['one_time_tracks']} discoveries)")
    
    gd = results["genre_diversity"]
    print(f"\nGenre Diversity: {gd['diversity_score']}% (Shannon), {gd['genre_count']} genres")
    print(f"  Top: {', '.join(g['genre'] for g in gd['top_genres'][:5])}")
    
    dna = results["music_dna"]
    print(f"\nMusic DNA:")
    for dim, data in dna["dna"].items():
        if "label" in data:
            print(f"  {dim.replace('_', ' ').title()}: {data['label']}")
    
    arch = results["listener_archetype"]
    print(f"\nListener Archetype: {arch['archetype']}")
    print(f"  Signals: {len(arch['archetype_signals'])}")
    
    ao = results["anomalies"]
    print(f"\nInteresting Findings: {ao['total_findings']} anomalies detected")
    
    recs = results["recommendations"]
    print(f"\nRecommendations: {recs['total_recommendations']} suggestions")
    
    if args.cache:
        save_analytics_cache(results)
        print("\n[analytics] Results cached for dashboard")
    
    # Save to file for dashboard
    output_path = REPO_ROOT / "analytics_results.json"
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    print(f"[analytics] Full results saved to {output_path}")
