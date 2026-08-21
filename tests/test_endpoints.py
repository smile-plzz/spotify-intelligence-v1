"""Smoke tests: every endpoint answers 200 with the schema the client expects.

Modelled on the manual `verify_chain.py` sweep — same checks, no live server.
"""

import pytest

# (path, top-level keys the dashboard.js handlers read)
API_ENDPOINTS = [
    ("/health", ["status", "timestamp"]),
    ("/api/status", ["counts", "last_play", "analytics_cached", "database_bytes"]),
    ("/api/recent", ["plays", "count"]),
    ("/api/summary", ["total_plays", "unique_artists", "unique_tracks", "playlists"]),
    ("/api/genres", ["genres", "families", "total_genres"]),
    ("/api/top-artists", ["artists"]),
    ("/api/top-tracks", ["tracks"]),
    ("/api/taste-evolution", ["timeline"]),
    ("/api/time-of-day", ["hourly", "daily"]),
    ("/api/sessions", ["sessions"]),
    ("/api/library", ["saved_tracks", "saved_albums", "playlists"]),
    ("/api/analytics", ["total_listening", "genre_diversity", "music_dna", "listener_archetype"]),
    ("/api/listening-patterns", ["hourly", "daily", "peak_hour", "peak_day"]),
    ("/api/mood", ["overall_mood", "valence_avg", "energy_avg", "acoustic_avg", "danceable_avg"]),
    ("/api/archetype", ["archetype", "archetype_key"]),
    ("/api/evolution", ["timeline"]),
    ("/api/playlist", ["playlists"]),
    ("/api/timezone", ["timezone", "utc_offset", "peak_hour", "active_days", "listening_days"]),
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


def test_currently_playing_reports_a_missing_client_as_a_state(client):
    """No Spotify client on the host is a 'not connected' state, not a 5xx.

    Returning 500 made every page log a console error on each 5-second poll
    and threw in fetchJSON, so the Live card never rendered its idle state.
    """
    resp = client.get("/api/currently-playing")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["playing"] is False
    assert payload["connected"] is False
    assert payload["message"]


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
