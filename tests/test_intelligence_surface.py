"""The Figma-surface endpoints must return real analytics, not their defaults.

Each of these read a key the analytics engine never emitted, so they answered
200 with placeholder values — mood was a flat 50/50, insights was an empty
list, evolution's top genre was always null. A status-code smoke test cannot
tell that apart from working, so these assert the values.
"""

import pytest


def test_mood_reflects_the_audio_features(client):
    mood = client.get("/api/mood").get_json()

    # Fixture averages: valence .443, energy .566, acousticness .393,
    # danceability .531 — none of which are the 50/50/0/50 defaults.
    assert mood["valence_avg"] == 44
    assert mood["energy_avg"] == 57
    assert mood["acoustic_avg"] == 39
    assert mood["danceable_avg"] == 53
    assert mood["explicit_pct"] == pytest.approx(13.3, abs=0.1)
    assert mood["overall_mood"] == "balanced"
    assert mood["top_moods"], "interpretation labels should be surfaced"


def test_insights_are_not_empty(client):
    insights = client.get("/api/insights").get_json()["insights"]

    assert len(insights) >= 4, insights
    assert all(isinstance(i, str) and i.strip() for i in insights)
    joined = " ".join(insights)
    assert "archetype" in joined.lower()
    assert "genres" in joined.lower()
    assert "still forming" not in joined, "fixture has data; this is the empty fallback"


def test_anomalies_come_through(client):
    findings = client.get("/api/anomalies").get_json()["findings"]
    assert findings
    assert all(f.get("description") for f in findings)


def test_evolution_names_its_top_genre(client):
    payload = client.get("/api/evolution").get_json()
    timeline = payload["timeline"]

    assert timeline
    assert all(t["top_genre"] for t in timeline), "top_genres[0].genre must be surfaced"
    # Every play is counted once, across however many periods the fixture spans.
    assert sum(t["total_plays"] for t in timeline) == 15
    assert max(t["unique_tracks"] for t in timeline) > 1
    assert "shifts" in payload


def test_listening_patterns_are_flat_counts(client):
    patterns = client.get("/api/listening-patterns").get_json()

    assert len(patterns["hourly"]) == 24
    assert sorted(patterns["hourly"]) == [f"{h:02d}" for h in range(24)]
    assert all(isinstance(v, int) for v in patterns["hourly"].values())
    assert sum(patterns["hourly"].values()) == 15
    assert sum(patterns["daily"].values()) == 15
    assert patterns["peak_hour"] is not None


def test_timezone_reports_counts_and_day_names(client):
    tz = client.get("/api/timezone").get_json()

    assert isinstance(tz["active_days"], int)
    assert tz["active_days"] > 0
    assert all(isinstance(d, str) for d in tz["listening_days"])
    assert tz["listening_days"], "day names come from the daily breakdown"


def test_archetype_carries_signals(client):
    arch = client.get("/api/archetype").get_json()

    assert arch["archetype"] != "The Listener", "fixture should classify"
    assert arch["archetype_signals"]
    assert all(s.get("description") for s in arch["archetype_signals"])
    assert arch["supporting_metrics"]["total_plays"] == 15


def test_recent_plays_are_newest_first(client):
    payload = client.get("/api/recent?limit=5").get_json()
    plays = payload["plays"]

    assert payload["count"] == len(plays) == 5
    assert [p["tracks_ago"] for p in plays] == [0, 1, 2, 3, 4]
    stamps = [p["played_at"] for p in plays]
    assert all(stamps)
    assert stamps == sorted(stamps, reverse=True)
    assert all(p["track"] and p["artist"] for p in plays)


def test_recent_limit_is_clamped(client):
    assert client.get("/api/recent?limit=0").status_code == 200
    assert len(client.get("/api/recent?limit=0").get_json()["plays"]) == 1
    assert len(client.get("/api/recent?limit=9999").get_json()["plays"]) == 15
    assert len(client.get("/api/recent?limit=abc").get_json()["plays"]) == 15
