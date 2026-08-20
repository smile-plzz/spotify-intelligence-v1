"""Every page must carry the hooks its renderer looks for.

The renderers query by selector and silently no-op when a selector is absent,
so a page whose markup drifted from the JS shows its Figma placeholder values
and looks merely 'stale' rather than broken.
"""

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

# page -> selectors its renderers write into
REQUIRED_HOOKS = {
    "Overview.dc.html": [
        "now-playing-artist", "top-artists-list", "top-tracks-list",
        "genre-cloud", "archetype-name", "archetype-description", "dna-item",
    ],
    "Taste.dc.html": [
        "genre-families", "diversity-value", "diversity-bar", "diversity-badge",
        "discovery-caption", "discovery-comfort", "dna-item",
    ],
    "Evolution.dc.html": [
        "evolution-chart", "evolution-bar", "evolution-bar-fill",
        "evolution-bar-label", "evolution-axis", "evolution-caption",
        "genre-families",
    ],
    "Listening.dc.html": [
        "music-clock", "clock-bar", "day-bars", "day-bar", "sessions-table",
        "music-clock-caption",
    ],
    "Library.dc.html": [
        "tab-btn", "lib-tracks", "lib-albums", "lib-playlists",
        "album-grid", "album-item", "album-name", "album-meta",
        "playlist-grid", "playlist-card", "playlist-name", "playlist-track-count",
    ],
    "Intelligence.dc.html": [
        "archetype-name", "archetype-description", "insights-list", "insight-card",
        "anomalies-list", "anomaly-title", "anomaly-description",
        "recommendations-list", "recommendation-name", "recommendation-reason",
    ],
    "Live.dc.html": [
        "live-track-name", "live-status-text", "live-artist", "live-dot",
        "live-progress-fill", "audio-features-grid",
        "activity-list", "activity-item", "activity-track", "activity-artist",
        "activity-time", "activity-ago",
    ],
    "Settings.dc.html": [
        "settings-status", "status-plays", "status-artists", "status-tracks",
        "status-saved", "status-playlists", "status-db-size",
        "status-last-play", "status-analytics",
    ],
}


@pytest.mark.parametrize("page,hooks", REQUIRED_HOOKS.items(), ids=list(REQUIRED_HOOKS))
def test_page_carries_its_render_hooks(page, hooks):
    markup = (TEMPLATES / page).read_text(encoding="utf-8")
    missing = [h for h in hooks if f'"{h}' not in markup and f' {h}"' not in markup and h not in markup]
    assert not missing, f"{page} is missing render hooks: {missing}"


def test_every_page_loads_the_client():
    for page in REQUIRED_HOOKS:
        markup = (TEMPLATES / page).read_text(encoding="utf-8")
        assert "/static/js/dashboard.js" in markup, f"{page} does not load dashboard.js"


def test_settings_does_not_offer_unimplemented_actions():
    """Clear-data and disconnect are not wired to anything; they must not look live."""
    markup = (TEMPLATES / "Settings.dc.html").read_text(encoding="utf-8")
    for label in ("Clear synced data", "Disconnect Spotify"):
        button = re.search(r"<button[^>]*>(?:(?!</button>).)*" + re.escape(label), markup, re.S)
        assert button, f"{label} button not found"
        assert "disabled" in button.group(0), f"{label} is not disabled but has no handler"


def test_settings_status_does_not_collide_with_the_overview_stat_grid():
    """`renderStats` claims `.stat-grid` on every page it can find one.

    Reusing those classes on Settings let the Overview renderer overwrite the
    data-status labels and values with its own.
    """
    markup = (TEMPLATES / "Settings.dc.html").read_text(encoding="utf-8")
    assert "stat-grid" not in markup
    assert "stat-card" not in markup
