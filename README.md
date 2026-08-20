# Spotify Intelligence

Your personal Spotify listening intelligence platform — a complete picture of you as a music listener.

## What it shows

- **Overview** — now-playing, stats, top artists/tracks, genre cloud, listener archetype
- **Taste** — diversity score, discovery meter, genre families, Music DNA (9 audio dimensions)
- **Evolution** — listening timeline, month-by-month genre shifts
- **Listening** — daily music clock, weekday/weekend patterns, sessions
- **Library** — tracks, albums, playlists (segmented tabs)
- **Intelligence** — archetype deep-dive, AI insights, anomalies, recommendations
- **Live** — current now-playing card with audio features grid

## Setup

```bash
cd spotify-intelligence
cp .env.example .env
# Fill in SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI
# and NGROK_AUTHTOKEN
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python dashboard.py
```

Then open `http://localhost:5000` and click **Connect Spotify**.

## Data

- `spotify_data.db` — SQLite warehouse (ingested by `ingest.py`)
- `analytics.py` — 30+ metrics, reproducible from stored data
- Dashboard reads from the DB; no Spotify calls needed for analytics

## Deployment

```bash
ngrok http 5000
```

The tunnel URL becomes your live dashboard. No new accounts, no payment.

## API

| Endpoint | Description |
|---|---|
| `/api/summary` | Total plays, artists, tracks, albums, time range |
| `/api/analytics` | Archetype, diversity, audio profile, top artists/tracks, genre families, top genres |
| `/api/genres` | Genre list with counts, families |
| `/api/top-artists` | Top 15 artists by play count |
| `/api/top-tracks` | Top 15 tracks by play count |
| `/api/taste-evolution` | Genre counts by month |
| `/api/time-of-day` | Play counts by hour of day |
| `/api/sessions` | Listening sessions |
| `/api/library` | Saved tracks, albums, playlists |
| `/api/currently-playing` | Current Spotify track (if playing) |
| `/api/listening-patterns` | Hourly/daily pattern summary with peaks |
| `/api/mood` | Valence, energy, acousticness, danceability averages |
| `/api/archetype` | Listener archetype and its supporting signals |
| `/api/evolution` | Taste timeline (cached analytics view) |
| `/api/playlist` | Playlists from the warehouse |
| `/api/timezone` | Inferred timezone and peak listening hour |
| `/api/insights` | Generated listening insights |
| `/api/anomalies` | Detected listening anomalies |
| `/health` | Liveness probe |

## Tests

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
```

The suite runs against a seeded fixture warehouse (`tests/fixture_db.py`), so it
needs neither `spotify_data.db` nor Spotify credentials. It covers every API
endpoint's status and response schema, every page template rendering, static
asset serving, the top-artists/top-tracks play-count aggregation, and a static
check that `dashboard.js` calls no undefined methods during init. GitHub Actions
runs it on every push and pull request (`.github/workflows/ci.yml`).

## Credentials

Spotify credentials go in `.env` (gitignored). See `.env.example`.

## Built for

CaptainL — Ismail Hossain. Dhaka. BSc CSE NSU 2023.

---

*No morty. No rick. Just the data.*
