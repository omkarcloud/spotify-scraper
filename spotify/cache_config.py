"""Cache TTL per /spotify/* endpoint (cache.py, keyed on the validated
params — marshmallow fills the defaults, so `?page=1` and no `page` share a
row).

Tiers follow how fast each number moves: playcounts and monthly listeners
update about daily, playlists (editorial and chart) are re-cut often,
charts and the home feed change within the day, catalog metadata rarely.
"""
from datetime import timedelta

# --- catalog -----------------------------------------------------------------------
TRACK_CACHE = timedelta(hours=12)          # playcount moves daily
TRACK_META_CACHE = timedelta(days=3)       # credits, previews, related
ALBUM_CACHE = timedelta(hours=12)          # per-track playcounts
ARTIST_CACHE = timedelta(hours=6)          # monthly listeners / concerts
ARTIST_LIST_CACHE = timedelta(hours=12)
PLAYLIST_CACHE = timedelta(hours=3)
RADIO_CACHE = timedelta(hours=12)
PODCAST_CACHE = timedelta(hours=3)         # new episodes
EPISODE_CACHE = timedelta(days=1)
AUDIOBOOK_CACHE = timedelta(days=1)
USER_CACHE = timedelta(hours=12)

# --- search --------------------------------------------------------------------------
SUGGESTIONS_CACHE = timedelta(days=1)
SEARCH_CACHE = timedelta(hours=6)

# --- editorial / charts ------------------------------------------------------------------
BROWSE_CACHE = timedelta(hours=6)
HOME_CACHE = timedelta(hours=1)
CHART_CACHE = timedelta(hours=1)
CONCERT_CACHE = timedelta(hours=6)
LOCATIONS_CACHE = timedelta(days=7)
RESOLVE_CACHE = timedelta(days=7)
