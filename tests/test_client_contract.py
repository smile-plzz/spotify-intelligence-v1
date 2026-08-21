"""Value-level checks on what the client computes from the API payloads.

These mirror the arithmetic in dashboard.js so a change to either side has to
be deliberate. They read the endpoint payloads rather than running the DOM.
"""


def test_music_dna_inputs_are_present_in_the_analytics_payload(client):
    """The DNA bars read raw audio features, not the music_dna vs-pairs.

    Five of the eight bars read keys off music_dna that do not exist there and
    fell back to a flat 50.
    """
    analytics = client.get("/api/analytics").get_json()
    audio = analytics["audio_characteristics"]["audio_characteristics"]

    for feature in (
        "danceability", "energy", "valence", "acousticness",
        "instrumentalness", "speechiness", "tempo", "loudness",
    ):
        assert feature in audio, f"audio_characteristics is missing {feature}"

    dna = analytics["music_dna"]["dna"]
    for pair in (
        "high_energy_vs_low_energy", "acoustic_vs_electronic", "positive_vs_melancholic",
    ):
        assert pair in dna


def test_weekday_weekend_split_is_computable(client):
    """The weekend panel averages the daily breakdown by day name."""
    daily = client.get("/api/time-of-day").get_json()["daily"]

    assert daily
    assert all(
        day in {
            "Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday",
        }
        for day in daily
    )
    assert sum(daily.values()) == 15


def test_genre_payload_carries_families_for_the_taste_and_evolution_pages(client):
    genres = client.get("/api/genres").get_json()

    assert genres["families"]
    for family in genres["families"]:
        assert family["name"]
        assert family["genres"]
        assert family["total_plays"] > 0
    plays = [f["total_plays"] for f in genres["families"]]
    assert plays == sorted(plays, reverse=True)
