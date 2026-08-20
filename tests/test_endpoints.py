"""Smoke tests: every endpoint answers 200 with the schema the client expects.

Modelled on the manual `verify_chain.py` sweep — same checks, no live server.
"""

import pytest

# (path, top-level keys the dashboard.js handlers read)
API_ENDPOINTS = [
    ("/health", ["status", "timestamp"]),
    ("/api/summary", ["total_plays", "unique_artists", "unique_tracks", "playlists"]),
    ("/api/genres", ["genres", "families", "total_genres"]),
    ("/api/top-artists", ["artists"]),
    ("/api/top-tracks", ["tracks"]),
    ("/api/taste-evolution", ["timeline"]),
    ("/api/time-of-day", ["hourly", "daily"]),
    ("/api/sessions", ["sessions"]),
    ("/api/library", ["saved_tracks", "saved_albums", "playlists"]),
    ("/api/analytics", ["findings"]),
    ("/api/listening-patterns", ["hourly", "daily", "peak_hour", "peak_day"]),
    ("/api/mood", ["overall_mood", "valence_avg", "energy_avg"]),
    ("/api/archetype", ["archetype", "archetype_key"]),
    ("/api/evolution", ["timeline"]),
    ("/api/playlist", ["playlists"]),
    ("/api/timezone", ["timezone", "utc_offset", "peak_hour"]),
    ("/api/insights", ["insights"]),
    ("/api/anomalies", ["findings"]),
]

PAGES = [
    "/",
    "/Overview.dc.html",
    "/Taste.dc.html",
    "/Listening.dc.html",
    "/Library.dc.html",
    "/Live.dc.html",
    "/Intelligence.dc.html",
    "/Evolution.dc.html",
    "/Settings.dc.html",
]


@pytest.mark.parametrize("path,keys", API_ENDPOINTS, ids=[e[0] for e in API_ENDPOINTS])
def test_endpoint_returns_expected_schema(client, path, keys):
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} returned {resp.status_code}: {resp.data[:200]}"
    payload = resp.get_json()
    assert payload is not None, f"{path} did not return JSON"
    for key in keys:
        assert key in payload, f"{path} response missing key {key!r}"


def test_currently_playing_degrades_cleanly(client):
    """Needs the Spotify client, which CI does not have — it must still answer JSON."""
    resp = client.get("/api/currently-playing")
    assert resp.status_code in (200, 500)
    assert "playing" in resp.get_json()


@pytest.mark.parametrize("path", PAGES)
def test_page_renders(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} returned {resp.status_code}"
    assert b"<html" in resp.data.lower()


def test_unknown_page_is_404(client):
    assert client.get("/does-not-exist").status_code == 404


@pytest.mark.parametrize("path", ["/static/js/dashboard.js", "/static/css/dashboard.css"])
def test_static_assets_serve(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.data
