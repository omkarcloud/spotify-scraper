"""Spotify public user profiles and their public playlists.

pathfinder queryUser returns at most 10 playlists per call whatever
`limit` says, so pages larger than 10 fan out in parallel 10-item windows.
(The spclient follower / following views refuse the anonymous token.)
"""
from spotify import fetch
from spotify import parsers as P
from spotify.shared import chunked_offsets, paged_result, ref, require, run

UPSTREAM_PAGE = 10


def _query(uid, offset, limit):
    data = run("queryUser", {"uri": f"spotify:user:{uid}", "offset": offset, "limit": limit})
    return require(P.dig(data, "user"), "user", uid)


def _playlists(obj):
    return P.parse_list(P.dig(obj, "publicPlaylistsV2"), P.playlist)


def details(user):
    """Display name, avatar, verification, public playlist count and the
    first 10 public playlists (with follower counts)."""
    uid, _ = ref("user", user)
    obj = _query(uid, 0, UPSTREAM_PAGE)
    return {
        "id": P.clean(obj.get("id")) or uid,
        "name": P.clean(obj.get("name")),
        "link": P.entity_link("user", uid),
        "is_verified": obj.get("verified") if isinstance(obj.get("verified"), bool) else None,
        "total_public_playlists": P.total_of(obj.get("publicPlaylistsV2")),
        "images": P.image_sources(obj, "avatar"),
        "public_playlists": _playlists(obj) or None,
    }


def playlists(user, page=1, limit=50):
    """One page of a user's public playlists."""
    uid, _ = ref("user", user)
    windows = chunked_offsets(P.offset_of(page, limit), limit, UPSTREAM_PAGE)
    pages = fetch.run_parallel([lambda o=o, s=s: _query(uid, o, s) for o, s in windows])
    results = []
    for obj, (_, size) in zip(pages, windows):
        results.extend(_playlists(obj)[:size])   # upstream returns 10 whatever the limit
    total = P.total_of(P.dig(pages[0], "publicPlaylistsV2")) if pages else None
    return paged_result("results", results, page, limit, total,
                        user={"id": uid, "name": P.clean(pages[0].get("name")) if pages else None,
                              "link": P.entity_link("user", uid)})
