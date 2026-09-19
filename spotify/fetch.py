"""Spotify transport: plain curl_cffi with browser-impersonated TLS against
the JSON surfaces the open.spotify.com web player and its embed widget use.
No browser, no cookies, no login (validated 2026-09-19 from direct Indian
egress and a US proxy exit).

Access token: every public embed page (https://open.spotify.com/embed/
track/<id>) is a Next.js page whose __NEXT_DATA__ carries the anonymous
session the widget itself uses:
    props.pageProps.state.settings.session
        = {accessToken, accessTokenExpirationTimestampMs, isAnonymous: true}
This module reads that token (~1 h TTL), caches it per exit and re-reads the
page on a 401 or a minute before expiry. It never derives or mints tokens.

With that Bearer token (+ `app-platform: WebPlayer`):
  * PATHFINDER  https://api-partner.spotify.com/pathfinder/v1/query
    GraphQL persisted queries (ops.py): tracks with playcount, albums,
    artists with monthly listeners / followers / world rank / top cities,
    playlists with follower counts and chart positions, podcasts, episodes,
    audiobooks + chapters, search, browse, home, country hubs, concerts,
    users, 30 s previews, credits. A missing entity is 200 + a
    `NotFound` typename (parsers.require), not an HTTP error.
  * SPCLIENT    https://spclient.wg.spotify.com
    track credits (with sources), playlist popcount, seed-to-playlist radio.
    User followers / following / playlists views answer 403 "RBAC: access
    denied" to the embed token, so users are served from pathfinder.
No auth: the public charts service (3 global weekly charts) and
spotify.link short links (a 307 to the canonical URL).

Not reachable anonymously: lyrics (login), audio features / analysis (gone
from the web player), seeded recommendations (api.spotify.com answers 429
to web tokens), per-country charts on the charts service (charts login —
the country hub's chart playlists cover per-country Top Songs / Top 50).

Market: Spotify derives it from the exit IP. Only audiobooks care
(RestrictedContent outside the US), so `country` picks a proxy exit
pinned to that country (config.spotify_proxy); None = the pod's egress.

FALLBACK HOOK: if pathfinder ever starts refusing server IPs (403 / 429 on
every call), escalate the way g2 does: add a patchright pool with flag
"spotify" to config.CHROME_POOLS, open https://open.spotify.com/ in it and
run the same GETs through the in-page fetch (patchright_driver.FetchResponse)
so they carry the real browser's TLS and cookies. Not built: dead code
while plain HTTP works.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  SpotifyUpstreamError  transport failure / 5xx / GraphQL error  — retryable
  SpotifyBlocked        403 / 429 / non-JSON body                 — retryable
  SpotifyBadRequest     upstream rejected the variables            — never retried
  SpotifyNotFound       entity does not exist                      — never retried
"""
import base64
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from spotify import ops

SITE = "https://open.spotify.com"
PATHFINDER = "https://api-partner.spotify.com/pathfinder/v1/query"
SPCLIENT = "https://spclient.wg.spotify.com"
CHARTS_API = "https://charts-spotify-com-service.spotify.com/public/v0/charts"
IMPERSONATE = "chrome"
TIMEOUT = 30
FANOUT_WORKERS = 6
CLIENT_VERSION = "1.3.3.52.gba294495"
TOKEN_REFRESH_MARGIN = 60          # seconds before expiry a token is re-read
DISCOVERY_INTERVAL = 3600          # rescan the chunk manifest at most hourly per op

# Any long-lived public track: its embed page is only read for the session.
TOKEN_EMBED_URL = SITE + "/embed/track/4uLU6hMCjMI75M1A2tKUQC"

PAGE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
}
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
_MANIFEST_RE = re.compile(r'<script id="__CDN_FILE_URLS__" type="text/plain">([^<]+)</script>')


class SpotifyUpstreamError(UpstreamError):
    """Transport failure, 5xx or a GraphQL-level error — retryable."""


class SpotifyBlocked(SpotifyUpstreamError, Blocked):
    """403 / 429 or a non-JSON body where JSON was expected — retryable."""


class SpotifyBadRequest(BadRequest):
    """Upstream rejected the request (bad variables, invalid code) — never retried."""


class SpotifyNotFound(NotFound):
    """Entity does not exist — never retried."""


class _TokenRejected(SpotifyUpstreamError):
    """401: the anonymous token expired or was revoked — re-read once."""


class _HashRejected(SpotifyUpstreamError):
    """PersistedQueryNotFound: this operation's hash is stale."""


# ---- sessions (one per worker thread and exit) ---------------------------------

_local = threading.local()


def exit_key(country=None):
    return (country or config.SPOTIFY_PROXY_COUNTRY or "").lower()


def _sessions():
    sessions = getattr(_local, "sessions", None)
    if sessions is None:
        sessions = _local.sessions = {}
    return sessions


def _session(country=None):
    key = exit_key(country)
    sess = _sessions().get(key)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = config.spotify_proxy(key or None)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        _sessions()[key] = sess
    return sess


def _drop_session(country=None):
    sess = _sessions().pop(exit_key(country), None)
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def dump_debug(name, text):
    """Write a raw response to $SPOTIFY_DEBUG_DIR/<name>.txt."""
    dbg = os.environ.get("SPOTIFY_DEBUG_DIR", "")
    if dbg and text:
        try:
            os.makedirs(dbg, exist_ok=True)
            with open(os.path.join(dbg, name + ".txt"), "w") as f:
                f.write(text)
        except OSError:
            pass


# ---- anonymous access token (read from an embed page) -----------------------------

def next_data(html):
    """The __NEXT_DATA__ JSON of a Next.js page, {} when absent."""
    match = _NEXT_DATA_RE.search(html or "")
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except ValueError:
        return {}


def embed_session(html):
    """(token, expiry epoch seconds) from an embed page, (None, None) if absent."""
    state = ((next_data(html).get("props") or {}).get("pageProps") or {}).get("state") or {}
    session = (state.get("settings") or {}).get("session") or {}
    token = session.get("accessToken")
    exp_ms = session.get("accessTokenExpirationTimestampMs")
    if not token:
        return None, None
    return token, (int(exp_ms) / 1000 if exp_ms else time.time() + 1800)


_token_lock = threading.Lock()
_tokens = {}          # exit key -> {"value", "exp"}


def _read_token(country):
    sess = _session(country)
    try:
        page = sess.get(TOKEN_EMBED_URL, headers=PAGE_HEADERS, timeout=TIMEOUT)
    except Exception as e:
        raise SpotifyUpstreamError(f"embed page request failed: {type(e).__name__}: {e}")
    if page.status_code in (403, 429):
        dump_debug("embed_blocked", page.text)
        raise SpotifyBlocked(f"HTTP {page.status_code} on the embed page")
    token, exp = embed_session(page.text or "")
    if not token:
        dump_debug("embed", page.text)
        raise SpotifyUpstreamError(f"no session in the embed page (HTTP {page.status_code}; layout changed?)")
    return token, exp


def access_token(country=None, force=False):
    """Cached anonymous token for this exit; re-read when forced (after a
    401) or within a minute of its expiry."""
    key = exit_key(country)
    with _token_lock:
        entry = _tokens.get(key)
        if force or not entry or entry["exp"] - TOKEN_REFRESH_MARGIN < time.time():
            token, exp = _read_token(country)
            entry = _tokens[key] = {"value": token, "exp": exp}
        return entry["value"]


def _auth_headers(country=None):
    return {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "authorization": f"Bearer {access_token(country)}",
        "app-platform": "WebPlayer",
        "spotify-app-version": CLIENT_VERSION,
        "origin": SITE,
        "referer": SITE + "/",
    }


# ---- persisted-query hashes ------------------------------------------------------

_hash_lock = threading.Lock()
_hashes = {name: list(values) for name, values in ops.HASHES.items()}
_discovered_at = {}


def hashes_for(operation):
    with _hash_lock:
        return list(_hashes.get(operation) or [])


def find_hash(js_text, operation):
    """sha256 of `operation` in one web-player chunk, None if absent."""
    match = re.search(r'"%s","query","([0-9a-f]{64})"' % re.escape(operation), js_text or "")
    return match.group(1) if match else None


def discover_hash(operation, country=None):
    """Rescan the web player's chunk manifest for a fresh hash of
    `operation` (at most hourly per op). Returns the new hash or None."""
    now = time.time()
    with _hash_lock:
        if now - _discovered_at.get(operation, 0) < DISCOVERY_INTERVAL:
            return None
        _discovered_at[operation] = now
    sess = _session(country)
    try:
        shell = sess.get(SITE + "/", headers=PAGE_HEADERS, timeout=TIMEOUT).text or ""
        match = _MANIFEST_RE.search(shell)
        manifest = json.loads(base64.b64decode(match.group(1))) if match else {}
    except Exception:
        return None
    urls = [u for u in manifest.values() if isinstance(u, str) and u.endswith(".js")]

    def scan(url):
        try:
            return find_hash(sess.get(url, headers={"accept": "*/*"}, timeout=TIMEOUT).text, operation)
        except Exception:
            return None

    known = set(hashes_for(operation))
    for sha in run_parallel([lambda u=u: scan(u) for u in urls]):
        if sha and sha not in known:
            with _hash_lock:
                _hashes.setdefault(operation, []).insert(0, sha)
            return sha
    return None


# ---- requests ---------------------------------------------------------------------

def _classify(resp, label):
    status = resp.status_code
    if status == 200:
        return
    if status == 401:
        raise _TokenRejected(f"HTTP 401 on {label}")
    if status == 404:
        raise SpotifyNotFound(f"{label} not found")
    if status == 400:
        raise SpotifyBadRequest(f"upstream rejected {label}: {(resp.text or '')[:200]}")
    if status in (403, 429):
        dump_debug("blocked", resp.text)
        raise SpotifyBlocked(f"HTTP {status} on {label}")
    raise SpotifyUpstreamError(f"HTTP {status} on {label}")


def _json(resp, label):
    body = resp.text or ""
    if not body.lstrip().startswith(("{", "[")):
        dump_debug("nonjson", body)
        raise SpotifyBlocked(f"{label} returned a non-JSON body")
    try:
        return resp.json()
    except ValueError:
        raise SpotifyBlocked(f"{label} returned malformed JSON")


def _retrying(do, country, label):
    """Run do(headers) under the retry policy: transport errors / 5xx /
    blocks retry with backoff on a fresh session; a 401 re-reads the token
    once (not counted as an attempt); 400/404 raise immediately."""
    token_refreshed = False
    last = None
    attempt = 0
    while attempt < config.MAX_RETRIES:
        attempt += 1
        try:
            return do(_auth_headers(country))
        except _TokenRejected as e:
            last = e
            if token_refreshed:
                break
            token_refreshed = True
            access_token(country, force=True)
            attempt -= 1
            continue
        except _HashRejected:
            raise
        except SpotifyUpstreamError as e:
            last = e
            _drop_session(country)
        except Exception as e:  # curl transport errors
            if isinstance(e, (SpotifyBadRequest, SpotifyNotFound)):
                raise
            last = SpotifyUpstreamError(f"{label} request failed: {type(e).__name__}: {e}")
            _drop_session(country)
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def _graphql_errors(body, operation):
    """Map a GraphQL `errors` array (with no usable data) onto the taxonomy."""
    errors = body.get("errors") or []
    messages = [str((e or {}).get("message") or "") for e in errors if isinstance(e, dict)]
    text = "; ".join(m for m in messages if m) or "unknown error"
    if any("PersistedQueryNotFound" in m for m in messages):
        raise _HashRejected(f"{operation}: persisted query hash is stale")
    lowered = text.lower()
    if "not found" in lowered:
        raise SpotifyNotFound(text[:300])
    if "invalid" in lowered or "is not of type" in lowered or "variable" in lowered:
        raise SpotifyBadRequest(f"{operation}: {text[:300]}")
    raise SpotifyUpstreamError(f"{operation}: {text[:300]}")


def pathfinder(operation, variables, country=None):
    """Run one persisted query; returns the `data` object. Tries each known
    hash for the operation, then one manifest rescan, before giving up."""
    params = {"operationName": operation,
              "variables": json.dumps(variables, separators=(",", ":"))}

    def attempt_with(sha):
        def do(headers):
            query = dict(params, extensions=json.dumps(
                {"persistedQuery": {"version": 1, "sha256Hash": sha}}, separators=(",", ":")))
            resp = _session(country).get(PATHFINDER, params=query, headers=headers, timeout=TIMEOUT)
            _classify(resp, operation)
            body = _json(resp, operation)
            data = body.get("data") if isinstance(body, dict) else None
            if data is None:
                _graphql_errors(body if isinstance(body, dict) else {}, operation)
            return data
        return _retrying(do, country, operation)

    tried = []
    for sha in hashes_for(operation):
        tried.append(sha)
        try:
            return attempt_with(sha)
        except _HashRejected:
            continue
    fresh = discover_hash(operation, country)
    if fresh and fresh not in tried:
        return attempt_with(fresh)
    raise SpotifyUpstreamError(f"{operation}: no working persisted-query hash "
                               "(Spotify rotated it; update spotify/ops.py)")


def spclient(path, params=None, country=None):
    """GET one spclient REST path (JSON)."""
    label = path.split("?")[0]

    def do(headers):
        resp = _session(country).get(SPCLIENT + path, params=params or None, headers=headers,
                                     timeout=TIMEOUT)
        _classify(resp, label)
        return _json(resp, label)

    return _retrying(do, country, label)


def charts_overview():
    """The public charts service: the 3 global weekly charts (no auth)."""
    label = "charts overview"
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = _session().get(CHARTS_API, headers={"accept": "application/json"}, timeout=TIMEOUT)
            _classify(resp, label)
            return _json(resp, label)
        except (SpotifyBadRequest, SpotifyNotFound):
            raise
        except Exception as e:
            last = e if isinstance(e, SpotifyUpstreamError) else \
                SpotifyUpstreamError(f"{label} failed: {type(e).__name__}: {e}")
            _drop_session()
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def embed_entity(kind, rid):
    """The public embed widget's entity for one item (no auth): title,
    artists, release date, duration, 30 s audioPreview, playability. Used
    as the preview fallback when pathfinder has none for a track."""
    label = f"embed {kind}"
    try:
        resp = _session().get(f"{SITE}/embed/{kind}/{rid}", headers=PAGE_HEADERS, timeout=TIMEOUT)
    except Exception as e:
        raise SpotifyUpstreamError(f"{label} request failed: {type(e).__name__}: {e}")
    _classify(resp, label)
    state = ((next_data(resp.text).get("props") or {}).get("pageProps") or {}).get("state") or {}
    return ((state.get("data") or {}).get("entity")) or {}


def expand_short_link(link):
    """spotify.link / spotify.app.link short link -> the open.spotify.com
    URL it redirects to (one hop, no body). Unknown codes redirect to the
    home page, which is reported as not found."""
    try:
        resp = _session().get(link, headers=PAGE_HEADERS, allow_redirects=False, timeout=TIMEOUT)
    except Exception as e:
        raise SpotifyUpstreamError(f"short link request failed: {type(e).__name__}: {e}")
    target = resp.headers.get("location") or ""
    if resp.status_code not in (301, 302, 303, 307, 308) or not target:
        raise SpotifyNotFound(f"short link {link} did not redirect (HTTP {resp.status_code})")
    if "open.spotify.com/" not in target or target.rstrip("/").endswith("open.spotify.com"):
        raise SpotifyNotFound(f"short link {link} does not point at a Spotify item")
    return target


def run_parallel(fns, workers=FANOUT_WORKERS):
    """Run zero-arg callables in parallel; results align with `fns`.
    Exceptions propagate from the first failing call."""
    if not fns:
        return []
    if len(fns) == 1:
        return [fns[0]()]
    with ThreadPoolExecutor(max_workers=min(workers, len(fns))) as ex:
        futures = [ex.submit(fn) for fn in fns]
        return [f.result() for f in futures]


if __name__ == "__main__":
    # Smoke test: python spotify/fetch.py [track id]
    target = sys.argv[1] if len(sys.argv) > 1 else "11dFghVXANMlKmJXsNCbNl"
    data = pathfinder("getTrack", {"uri": f"spotify:track:{target}"})
    track = data.get("trackUnion") or {}
    print(track.get("name"), "- playcount", track.get("playcount"))
