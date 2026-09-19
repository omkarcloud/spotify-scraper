"""Spotify albums: details (label, copyrights, discs, every track with its
playcount, other editions, more by the artist) and paginated tracks."""
from spotify import parsers as P
from spotify.shared import paged_result, ref, require, run

MAX_TRACKS = 300          # getAlbum honours large limits; 300 covers box sets


def _fetch(aid, offset, limit):
    data = run("getAlbum", {"uri": f"spotify:album:{aid}", "locale": "", "offset": offset,
                            "limit": limit})
    return require(P.dig(data, "albumUnion"), "album", aid)


def _album_tracks(obj):
    out = []
    for row in P.items_of(P.dig(obj, "tracksV2")):
        parsed = P.track((row or {}).get("track") or row, with_album=False)
        if parsed:
            parsed.pop("type", None)
            out.append(parsed)
    return out


def _more_by_artist(obj):
    rows = P.items_of(obj.get("moreAlbumsByArtist"))
    first = rows[0] if rows else {}
    block = P.dig(first, "discography", "popularReleasesAlbums")
    return P.parse_list(block, P.album) or None


def details(album):
    """Album metadata + every track (with playcount), other editions and
    more albums by the same artist."""
    aid, _ = ref("album", album)
    obj = _fetch(aid, 0, MAX_TRACKS)
    out = P.album(obj) or {}
    out.pop("type", None)
    out.update({
        "playability_reason": P.playability_reason(obj),
        "prerelease_ends_at": P.iso_datetime(P.dig(obj, "preReleaseEndDateTime", "isoString")),
        "courtesy_line": P.clean(obj.get("courtesyLine")),
        "total_discs": P.total_of(obj.get("discs")),
        "tracks": _album_tracks(obj),
        "other_editions": P.parse_list(obj.get("releases"), P.album) or None,
        "more_by_artist": _more_by_artist(obj),
    })
    return P.ordered(out, ("id", "name", "link", "album_type", "release_date",
                           "release_date_precision", "label", "total_tracks", "total_discs",
                           "is_playable", "playability_reason", "is_prerelease",
                           "prerelease_ends_at", "artists", "images", "copyrights",
                           "courtesy_line", "tracks"))


def tracks(album, page=1, limit=50):
    """One page of an album's tracks (with playcount)."""
    aid, _ = ref("album", album)
    obj = _fetch(aid, P.offset_of(page, limit), limit)
    head = {"id": aid, "name": P.clean(obj.get("name")), "link": P.entity_link("album", aid)}
    return paged_result("results", _album_tracks(obj), page, limit,
                        P.total_of(obj.get("tracksV2")), album=head)
