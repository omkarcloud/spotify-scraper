"""Helpers shared by the Spotify endpoint modules: NotFound checks on
GraphQL unions, entity refs, paged windows and the audiobook exit."""
import config
from spotify import fetch, refs
from spotify import parsers as P
from spotify.fetch import SpotifyNotFound

SEARCH_WINDOW = 1000       # pathfinder search: offset + limit must stay <= 1000


def require(obj, kind, rid):
    """The union object, or SpotifyNotFound for NotFound / GenericError /
    RestrictedContent (market-locked, e.g. audiobooks outside the US)."""
    if P.is_restricted(obj):
        raise SpotifyNotFound(f"{kind} {rid} is not available in this market")
    if P.is_missing(obj):
        raise SpotifyNotFound(f"{kind} {rid} not found")
    return obj


def ref(kind, value):
    """Validated ref (id or short link) -> (bare id, spotify URI)."""
    rid = refs.entity_id(kind, value)
    return rid, refs.uri(kind, rid)


def audiobook_country():
    return config.SPOTIFY_AUDIOBOOK_COUNTRY


def window(page, limit, cap=None):
    """(offset, limit) for a 1-based page; `cap` bounds offset + limit
    (search's 1000-result window)."""
    offset = P.offset_of(page, limit)
    if cap is not None and offset + limit > cap:
        raise ValueError(f"page * limit must be <= {cap} (Spotify only returns the first "
                         f"{cap} results of a search)")
    return offset, limit


def chunked_offsets(offset, limit, size):
    """[(offset, size), …] covering offset..offset+limit in `size` steps."""
    out, start = [], offset
    while start < offset + limit:
        out.append((start, min(size, offset + limit - start)))
        start += size
    return out


def paged_result(key, results, page, limit, total, has_more=None, **extra):
    """Endpoint result with a `pagination` block route_glue lifts."""
    if has_more is None:
        has_more = total is not None and P.offset_of(page, limit) + len(results) < total
    out = dict(extra)
    out[key] = results
    out["pagination"] = P.pagination(page, limit, total, has_more)
    return out


def run(operation, variables, country=None):
    return fetch.pathfinder(operation, variables, country=country)
