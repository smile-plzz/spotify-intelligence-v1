"""Regression tests for the analytics engine's period aggregation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analytics  # noqa: E402


def _evolution(fixture_db, period="month"):
    original = analytics.DB_PATH
    analytics.DB_PATH = fixture_db
    try:
        db = analytics.get_db()
        try:
            return analytics.compute_taste_evolution(db, period)
        finally:
            db.close()
    finally:
        analytics.DB_PATH = original


def test_period_plays_are_not_double_counted(fixture_db):
    """Plays were summed from the genre rows and again from the artist rows.

    With two genres per artist that reported 45 plays for a 15-play warehouse.
    """
    timeline = _evolution(fixture_db)["timeline"]
    assert sum(p["total_plays"] for p in timeline) == 15


def test_unique_tracks_are_counted(fixture_db):
    """The artist query selects `unique_tracks`, not `track_id`.

    Reading a missing `track_id` added one empty string per period, so every
    period reported exactly one unique track.
    """
    timeline = _evolution(fixture_db)["timeline"]
    assert max(p["unique_tracks"] for p in timeline) == 6
    assert max(p["unique_artists"] for p in timeline) == 5


def test_genre_shares_sum_to_a_hundred(fixture_db):
    """Shares are a fraction of the genre distribution, not of the play count."""
    for period in _evolution(fixture_db)["timeline"]:
        genres = period["top_genres"]
        assert genres
        assert sum(g["share"] for g in genres) <= 100.5
        assert period["genre_diversity"] > 0


def test_yearly_grouping_matches_monthly_totals(fixture_db):
    monthly = _evolution(fixture_db, "month")["timeline"]
    yearly = _evolution(fixture_db, "year")["timeline"]
    assert sum(p["total_plays"] for p in monthly) == sum(p["total_plays"] for p in yearly)
