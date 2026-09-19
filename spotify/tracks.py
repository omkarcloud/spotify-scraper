"""Spotify tracks: full details (playcount, credits, 30 s preview, album
with copyrights), batch details, credits, previews, related tracks,
albums similar to a track and the track radio."""
from spotify import fetch
from spotify import parsers as P
from spotify.shared import ref, require, run

MAX_BATCH = 20            # batch = one getTrack per id, fanned out
MAX_PREVIEWS = 50


def _track_payload(rid):
    data = run("getTrack", {"uri": f"spotify:track:{rid}"})
    return require(P.dig(data, "trackUnion"), "track", rid)


def _credits(obj):
    """queryTrackCreditsGroupedModal trackUnion -> (contributors, sources)."""
    trait = (obj or {}).get("creditsTrait") or {}
    contributors = []
    for c in P.items_of(trait.get("contributors")):
        if not isinstance(c, dict) or not c.get("name"):
            continue
        uri = c.get("uri")
        contributors.append({
            "name": P.clean(c.get("name")),
            "role": P.clean(c.get("role")),
            "role_group": P.clean(P.dig(c, "roleGroup", "name")),
            "artist_id": P.id_of(uri) if P.kind_of(uri) == "artist" else None,
            "link": P.link_of(uri) if uri else P.clean(c.get("url")),
        })
    sources = [P.clean(s.get("name")) for s in P.items_of(trait.get("sources"))
               if isinstance(s, dict) and s.get("name")]
    return contributors or None, sources or None


def _previews(ids):
    data = run("trackPreview", {"uris": [f"spotify:track:{i}" for i in ids]})
    out = {}
    for row in P.dig(data, "lookup") or []:
        obj = P.unwrap(row)
        rid = P.id_of((obj or {}).get("uri"))
        urls = [p.get("url") for p in P.items_of(P.dig(obj, "previews", "audioPreviewsV2"))
                if isinstance(p, dict) and p.get("url")]
        if rid:
            out[rid] = urls[0] if urls else None
    missing = [rid for rid in ids if not out.get(rid)]
    if missing:   # the embed widget often has a preview pathfinder lacks
        def embed_preview(rid):
            try:
                return P.clean(P.dig(fetch.embed_entity("track", rid), "audioPreview", "url"))
            except (fetch.SpotifyUpstreamError, fetch.SpotifyNotFound, fetch.SpotifyBadRequest):
                return None
        for rid, link in zip(missing, fetch.run_parallel([lambda r=r: embed_preview(r) for r in missing])):
            out[rid] = link
    return out


def _full_album(obj):
    album = P.album(obj.get("albumOfTrack") or {})
    if album:
        album.pop("artists", None)          # getTrack's album carries no artists
        album.pop("type", None)
    return album


def details(track):
    """Everything about one track: identity, timing, playcount, explicit /
    playable flags, artists, album (type, label-free, copyrights), credits
    with roles and sources, and the public 30 s preview."""
    rid, uri = ref("track", track)
    obj, credits, previews = fetch.run_parallel([
        lambda: _track_payload(rid),
        lambda: run("queryTrackCreditsGroupedModal", {"trackUri": uri}),
        lambda: _previews([rid]),
    ])
    out = P.track(obj, with_album=False) or {}
    out.pop("type", None)
    contributors, sources = _credits(P.dig(credits, "trackUnion"))
    out.update({
        "playability_reason": P.playability_reason(obj),
        "preview_link": previews.get(rid),
        "album": _full_album(obj),
        "credits": {"contributors": contributors, "sources": sources} if (contributors or sources) else None,
    })
    return P.ordered(out, ("id", "name", "link", "track_number", "disc_number", "duration_ms",
                           "duration_text", "is_explicit", "is_playable", "playability_reason",
                           "has_video", "playcount", "preview_link", "artists", "album", "credits"))


def stream_count(track):
    """Just the play count (plus identity) of one track — the cheap call."""
    rid, _ = ref("track", track)
    obj = _track_payload(rid)
    parsed = P.track(obj, with_album=False) or {}
    return {"id": parsed.get("id"), "name": parsed.get("name"), "link": parsed.get("link"),
            "artists": parsed.get("artists"), "playcount": parsed.get("playcount")}


def batch(tracks):
    """Details (with playcount) for up to 20 tracks in one request, in the
    order given; ids that don't exist come back in `not_found`."""
    def one(rid):
        try:
            return P.track(_track_payload(rid))
        except fetch.SpotifyNotFound:
            return None

    results = fetch.run_parallel([lambda r=r: one(r) for r in tracks])
    found = [r for r in results if r]
    for r in found:
        r.pop("type", None)
    missing = [rid for rid, r in zip(tracks, results) if not r]
    return {"count": len(found), "results": found, "not_found": missing or None}


def credits(track):
    """Songwriters, producers, performers… with their roles, plus the
    labels/distributors credited as sources."""
    rid, uri = ref("track", track)
    data = run("queryTrackCreditsGroupedModal", {"trackUri": uri})
    obj = require(P.dig(data, "trackUnion"), "track", rid)
    contributors, sources = _credits(obj)
    return {"track": {"id": rid, "name": P.clean(obj.get("name")), "link": P.entity_link("track", rid)},
            "contributors": contributors, "sources": sources}


def previews(tracks):
    """30 s MP3 preview links for up to 50 tracks (null when a track has none)."""
    found = _previews(tracks)
    return {"results": [{"id": rid, "link": P.entity_link("track", rid), "preview_link": found.get(rid)}
                        for rid in tracks]}


def related(track):
    """Tracks Spotify recommends alongside this one (with playcount)."""
    rid, uri = ref("track", track)
    data = run("internalLinkRecommenderTrack", {"uri": uri, "strategy": "RELATED_TRACKS"})
    results = P.parse_list(P.dig(data, "seoRecommendedTrack"), P.track)
    return {"track": {"id": rid, "link": P.entity_link("track", rid)}, "results": results}


def similar_albums(track, limit=20):
    """Albums similar to the one this track is on."""
    rid, uri = ref("track", track)
    data = run("similarAlbumsBasedOnThisTrack", {"uri": uri, "limit": limit})
    block = P.dig(data, "seoRecommendedTrackAlbum") or {}
    return {"track": {"id": rid, "link": P.entity_link("track", rid)},
            "total_count": P.total_of(block), "results": P.parse_list(block, P.album)}


def radio(track, page=1, limit=50):
    """The track's radio (Spotify's auto-generated "<track> Radio" playlist)."""
    from spotify import playlists
    rid, uri = ref("track", track)
    return playlists.radio_for(uri, page, limit)
