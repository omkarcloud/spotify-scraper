"""Configuration for the Spotify Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT           port the API listens on (default 8000)
    SPOTIFY_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                   (default: none — direct). Spotify runs no bot protection on
                   the surfaces this scraper uses, so you very likely don't
                   need it for rate limits. Spotify does pick the market from
                   your IP, and audiobooks are sold in the US only: outside
                   the US, set this to a US proxy if you want the audiobook
                   endpoints (everything else works from anywhere).

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# Market pinning. None = no separate exit: every request goes through
# SPOTIFY_PROXY (or direct when it is unset).
SPOTIFY_PROXY_COUNTRY = None
SPOTIFY_AUDIOBOOK_COUNTRY = None


def spotify_proxy(country=None):
    """Proxy URL for a new session (None = direct)."""
    return os.environ.get("SPOTIFY_PROXY") or None
