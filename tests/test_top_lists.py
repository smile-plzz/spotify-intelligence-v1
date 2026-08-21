"""Regression tests for the top-artists / top-tracks play-count aggregation.

Both endpoints used to rank off the Spotify snapshot tables and join plays in,
which reported 0 plays for every artist the snapshots listed but the warehouse
had never seen.
"""


def test_top_artists_report_real_play_counts(client):
    artists = client.get("/api/top-artists").get_json()["artists"]
    by_name = {a["name"]: a for a in artists}

    assert by_name["Bob Dylan"]["play_count"] == 5
    assert by_name["Taylor Swift"]["play_count"] == 4
    assert by_name["Death Cab for Cutie"]["play_count"] == 3

    played = [a["play_count"] for a in artists if a["time_range"] == "warehouse"]
    assert played == sorted(played, reverse=True), "played artists must be rank-ordered"
    assert all(count > 0 for count in played)


def test_top_artists_carry_genres_and_unique_tracks(client):
    artists = client.get("/api/top-artists").get_json()["artists"]
    dylan = next(a for a in artists if a["name"] == "Bob Dylan")
    assert dylan["unique_tracks"] == 2
    assert "folk rock" in dylan["genres"]


def test_top_artists_pad_from_snapshots_when_warehouse_is_thin(client):
    """Only 5 artists have plays, so the snapshot-only artist fills the list."""
    artists = client.get("/api/top-artists").get_json()["artists"]
    padded = [a for a in artists if a["time_range"] == "long_term"]
    assert any(a["name"] == "Never Played" for a in padded)
    assert all(a["play_count"] == 0 for a in padded)


def test_top_tracks_report_real_play_counts(client):
    tracks = client.get("/api/top-tracks").get_json()["tracks"]
    by_name = {t["name"]: t for t in tracks}

    assert by_name["All Too Well"]["play_count"] == 4
    assert by_name["Soul Meets Body"]["play_count"] == 3
    assert by_name["Soul Meets Body"]["artist"] == "Death Cab for Cutie"

    counts = [t["play_count"] for t in tracks]
    assert counts == sorted(counts, reverse=True)


def test_top_tracks_format_durations(client):
    tracks = client.get("/api/top-tracks").get_json()["tracks"]
    assert tracks[0]["duration_formatted"] == "3:35"
