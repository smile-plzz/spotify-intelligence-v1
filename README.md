# Spotify Intelligence Platform

A personal Spotify intelligence platform — analytics engine, genre mapping, taste evolution, AI insights, and an interactive dark-aesthetic dashboard. Built on real Spotify listening data from `smile_plzz_`.

## Architecture

```
Spotify API → Data Ingestion → SQLite Warehouse → Analytics Engine → AI Insights → Dashboard
```

## Quick Start

```bash
# Create .env from example
cp .env.example .env
# Fill in SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, and SPOTIFY_USER_ID

# Install deps
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Run full ingestion (pulls from Spotify)
.venv/bin/python ingest.py --full

# Generate genre mappings (deterministically seeded from taste profile)
.venv/bin/python seed_genres.py

# Compute analytics
.venv/bin/python analytics.py --cache

# Start dashboard server
.venv/bin/python dashboard.py
# Open http://localhost:5000
```

## What It Does

- **Data Layer**: Normalized SQLite warehouse (WAL mode) for tracks, artists, albums, listening events, audio features, playlists, saved tracks/albums, top-track/artist snapshots. Idempotent upserts, deduplication of listening events, incremental updates, rate-limit handling, token refresh, graceful API failure handling.
- **Analytics Engine** (1,700+ lines): 30 metric groups including total listening, genre diversity (Shannon index), artist loyalty, discovery vs comfort index, Music DNA profile (9 dimensions), taste evolution timeline, session analysis, time-of-day patterns, listener archetype classification, anomaly detection, personalized recommendations.
- **Genre Intelligence**: 20+ genres mapped across artist-genre relationships, genre families, and hierarchy — seeded from taste profile data.
- **Taste Evolution**: Month-by-month timeline with genre shifts, listening era identification, significant taste change detection.
- **AI Insights**: Grounded in analytics facts — listener archetype, anomaly descriptions, recommendation reasoning.
- **Dashboard**: 7-section dark-aesthetic Flask dashboard with Chart.js visualizations (8 charts): currently playing, top artists/tracks, genre universe, taste evolution, daily music clock, listening sessions, library, AI insights, real-time mode.

## Project Structure

```
spotify-intelligence/
├── ingest.py          # Spotify data ingestion (1,043 lines)
├── analytics.py       # Analytics engine (1,706 lines)
├── dashboard.py       # Flask dashboard server (605 lines, 10 API endpoints)
├── seed_genres.py     # Genre mapping seeder (deterministic from profile)
├── templates/
│   └── index.html     # Dark-aesthetic dashboard (7 sections, 23 cards)
├── static/
│   ├── css/dashboard.css   # Full dark theme (741 lines, :root variables)
│   └── js/dashboard.js     # Client-side Chart.js app (1,025 lines)
├── spotify_data.db    # SQLite warehouse (WAL mode, populated)
├── analytics_results.json  # Cached analytics output
├── .env               # Credentials (gitignored)
├── .env.example       # Template with placeholders
├── .gitignore         # Excludes .env, *.db, .venv/, api_cache/
└── requirements.txt   # Python dependencies
```

## API Scopes Used

- `user-read-recently-played`
- `user-top-read` (short/medium/long term)
- `user-library-read` (saved tracks/albums)
- `user-read-currently-playing`
- `user-read-playback-state`

## Dashboard Sections

| Section | Contents |
|---------|----------|
| **Overview** | Currently playing, stats grid (plays/artists/tracks/albums), top artists chart, top tracks chart, genre cloud, listener archetype, Music DNA |
| **Taste** | Genre universe (20 genres, families), diversity meter (Shannon index), artist relationship map, exploration ↔ comfort index |
| **Evolution** | Listening timeline (plays/artists over months), monthly genre evolution chart, listening eras, taste shifts |
| **Listening** | Daily music clock (24-hour radial), weekday vs weekend, listening sessions |
| **Library** | Saved tracks (50), saved albums (50), playlists (61) |
| **Intelligence** | AI-generated insights, anomaly findings, personalized recommendations |
| **Live** | Real-time currently playing with audio features, recent activity |

## Deployment

Flask development server (dashboard.py). For production, use a WSGI server (gunicorn) behind a reverse proxy. The app binds to `0.0.0.0:5000` by default (configurable via `FLASK_PORT` and `FLASK_HOST` env vars).

## Credentials

Spotify credentials are sourced from `C:\Users\ismai\.env` (home directory) and accessed via the Hermes Spotify plugin. The project `.env` mirrors these and is gitignored. Never commit real credentials — use `.env.example` as a template.

## License

Personal use.
