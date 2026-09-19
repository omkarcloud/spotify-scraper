"""Spotify artists: full profile (stats, biography, links, gallery, latest
and popular releases, top tracks with playcount, related content,
concerts), lean stats, top tracks, discography by type, related artists,
appears-on albums, playlists that discovered / feature the artist, the
artist's own playlists, concerts and the artist radio."""
from spotify import fetch
from spotify import parsers as P
from spotify.shared import paged_result, ref, require, run

DISCOGRAPHY_OPS = {
    "all": ("queryArtistDiscographyAll", "all"),
    "albums": ("queryArtistDiscographyAlbums", "albums"),
    "singles": ("queryArtistDiscographySingles", "singles"),
    "compilations": ("queryArtistDiscographyCompilations", "compilations"),
}
SORTS = {"newest": "DATE_DESC", "oldest": "DATE_ASC"}


def _overview(aid):
    data = run("queryArtistOverview", {"uri": f"spotify:artist:{aid}", "locale": "",
                                       "includePrerelease": True})
    return require(P.dig(data, "artistUnion"), "artist", aid)


def _head(obj, aid):
    return {"id": aid, "name": P.clean(P.dig(obj, "profile", "name")),
            "link": P.entity_link("artist", aid)}


def stats_block(stats):
    stats = stats or {}
    cities = []
    for c in P.items_of(stats.get("topCities")):
        if isinstance(c, dict) and c.get("city"):
            cities.append({"city": P.clean(c.get("city")), "region": P.clean(c.get("region")),
                           "country": P.clean(c.get("country")),
                           "listeners": P.to_int(c.get("numberOfListeners"))})
    return {
        "followers": P.to_int(stats.get("followers")),
        "monthly_listeners": P.to_int(stats.get("monthlyListeners")),
        "world_rank": P.to_int(stats.get("worldRank")) or None,
        "top_cities": cities or None,
    }


def _external_links(profile):
    out = []
    for link in P.items_of(P.dig(profile, "externalLinks")):
        if isinstance(link, dict) and link.get("url"):
            out.append({"name": P.lower(link.get("name")), "link": link["url"]})
    return out or None


def _gallery(visuals):
    out = []
    for g in P.items_of(P.dig(visuals, "gallery")):
        imgs = P.images((g or {}).get("sources"))
        if imgs:
            out.append(imgs[0])
    return out or None


def _biography(profile):
    bio = P.dig(profile, "biography") or {}
    text = P.strip_html(bio.get("text"))
    return {"text": text, "type": P.lower(bio.get("type"))} if text else None


def _top_tracks(obj):
    out = []
    for row in P.items_of(P.dig(obj, "discography", "topTracks")):
        parsed = P.track((row or {}).get("track") or row)
        if parsed:
            parsed.pop("type", None)
            out.append(parsed)
    return out or None


def _releases(block):
    return [x for x in (P.release_group(r) for r in P.items_of(block)) if x] or None


def _pinned(profile):
    pinned = P.dig(profile, "pinnedItem")
    if not isinstance(pinned, dict) or not pinned.get("uri"):
        return None
    return {"type": P.lower(pinned.get("type")), "name": P.clean(pinned.get("title")),
            "link": P.link_of(pinned.get("uri")), "comment": P.clean(pinned.get("comment"))}


def _merch(goods):
    out = []
    for m in P.items_of(P.dig(goods, "merch")):
        m = P.unwrap(m)
        if not isinstance(m, dict):
            continue
        name = P.clean(m.get("nameV2") or m.get("name"))
        link = P.clean(m.get("url"))
        if name or link:
            out.append({"name": name, "link": link, "price": P.clean(m.get("price")),
                        "images": P.image_sources(m, "image")})
    return out or None


def _playlist_list(block):
    return [x for x in (P.playlist(r) for r in P.items_of(block)) if x] or None


def details(artist):
    """The artist page in one call: verification, biography, stats
    (followers, monthly listeners, world rank, top cities), external links,
    images + gallery, pinned item, latest / popular releases, top tracks
    with playcount, discography counts, related artists, appears-on,
    featuring playlists, upcoming concerts and merch."""
    aid, _ = ref("artist", artist)
    obj = _overview(aid)
    profile = obj.get("profile") or {}
    visuals = obj.get("visuals") or {}
    disco = obj.get("discography") or {}
    related = obj.get("relatedContent") or {}
    goods = obj.get("goods") or {}
    concerts = [x for x in (P.concert_summary(c) for c in P.items_of(P.dig(goods, "concerts"))) if x]
    return {
        "id": aid,
        "name": P.clean(profile.get("name")),
        "link": P.entity_link("artist", aid),
        "is_verified": profile.get("verified") if isinstance(profile.get("verified"), bool) else None,
        "biography": _biography(profile),
        "stats": stats_block(obj.get("stats")),
        "external_links": _external_links(profile),
        "images": P.image_sources(visuals, "avatarImage"),
        "header_images": P.image_sources(obj, "headerImage"),
        "gallery": _gallery(visuals),
        "pinned_item": _pinned(profile),
        "latest_release": P.album(disco.get("latest") or {}),
        "popular_releases": P.parse_list(disco.get("popularReleasesAlbums"), P.album) or None,
        "top_tracks": _top_tracks(obj),
        "discography_counts": {
            "albums": P.total_of(disco.get("albums")),
            "singles": P.total_of(disco.get("singles")),
            "compilations": P.total_of(disco.get("compilations")),
            "appears_on": P.total_of(related.get("appearsOn")),
            "music_videos": P.total_of(obj.get("relatedMusicVideos")),
        },
        "related_artists": P.parse_list(related.get("relatedArtists"), P.artist) or None,
        "appears_on": _releases(related.get("appearsOn")),
        "featuring_playlists": _playlist_list(related.get("featuringV2")),
        "artist_playlists": _playlist_list(profile.get("playlistsV2")),
        "upcoming_concerts": {"total_count": P.total_of(P.dig(goods, "concerts")),
                              "results": concerts} if concerts else None,
        "merch": _merch(goods),
    }


def stats(artist):
    """Just the numbers: followers, monthly listeners, world rank and the
    top listening cities, plus verification and biography."""
    aid, _ = ref("artist", artist)
    data = run("queryArtistAboutModal", {"artistUri": f"spotify:artist:{aid}", "locale": ""})
    obj = require(P.dig(data, "artistUnion"), "artist", aid)
    verification = P.dig(obj, "onPlatformReputationTrait", "verification") or {}
    profile = obj.get("profile") or {}
    return {
        "id": aid,
        "name": P.clean(profile.get("name")),
        "link": P.entity_link("artist", aid),
        "is_verified": verification.get("isVerified") if isinstance(verification.get("isVerified"), bool) else None,
        "is_registered": verification.get("isRegistered") if isinstance(verification.get("isRegistered"), bool) else None,
        **stats_block(obj.get("stats")),
        "biography": _biography(profile),
        "external_links": _external_links(profile),
        "images": P.image_sources(obj.get("visuals") or {}, "avatarImage"),
        "gallery": _gallery(obj.get("visuals") or {}),
    }


def top_tracks(artist):
    """The artist's 10 most popular tracks with playcount."""
    aid, _ = ref("artist", artist)
    obj = _overview(aid)
    return {"artist": _head(obj, aid), "results": _top_tracks(obj) or []}


def albums(artist, type="all", sort="newest", page=1, limit=50):
    """One page of the discography: all releases, or only albums / singles
    / compilations, newest or oldest first."""
    aid, _ = ref("artist", artist)
    operation, key = DISCOGRAPHY_OPS[type]
    data = run(operation, {"uri": f"spotify:artist:{aid}", "offset": P.offset_of(page, limit),
                           "limit": limit, "order": SORTS[sort]})
    obj = require(P.dig(data, "artistUnion"), "artist", aid)
    block = P.dig(obj, "discography", key) or {}
    results = _releases(block) or []
    return paged_result("results", results, page, limit, P.total_of(block),
                        artist={"id": aid, "link": P.entity_link("artist", aid)}, type=type, sort=sort)


def _related_list(operation, aid, path, parse):
    data = run(operation, {"uri": f"spotify:artist:{aid}"})
    obj = require(P.dig(data, "artistUnion"), "artist", aid)
    block = P.dig(obj, *path) or {}
    return {"artist": _head(obj, aid), "total_count": P.total_of(block),
            "results": [x for x in (parse(r) for r in P.items_of(block)) if x]}


def related(artist):
    """Up to 40 artists fans also like."""
    aid, _ = ref("artist", artist)
    return _related_list("queryArtistRelated", aid, ("relatedContent", "relatedArtists"), P.artist)


def appears_on(artist):
    """Albums by other artists this artist appears on (up to 50)."""
    aid, _ = ref("artist", artist)
    return _related_list("queryArtistAppearsOn", aid, ("relatedContent", "appearsOn"), P.release_group)


def discovered_on(artist):
    """Playlists where listeners discovered this artist (entries Spotify
    hides from anonymous viewers are skipped)."""
    aid, _ = ref("artist", artist)
    return _related_list("queryArtistDiscoveredOn", aid, ("relatedContent", "discoveredOnV2"), P.playlist)


def featuring(artist):
    """Spotify playlists featuring the artist (This Is …, Radio, …)."""
    aid, _ = ref("artist", artist)
    return _related_list("queryArtistFeaturing", aid, ("relatedContent", "featuringV2"), P.playlist)


def playlists(artist):
    """Public playlists the artist curates on their own profile."""
    aid, _ = ref("artist", artist)
    return _related_list("queryArtistPlaylists", aid, ("profile", "playlistsV2"), P.playlist)


def concerts(artist):
    """The artist's upcoming concerts (date, venue city, line-up)."""
    aid, _ = ref("artist", artist)
    data = run("ArtistConcerts", {"artistUri": f"spotify:artist:{aid}", "geoHash": None,
                                  "includeNearby": False})
    obj = require(P.dig(data, "artistUnion"), "artist", aid)
    block = P.dig(data, "concerts", "concerts") or {}
    results = [x for x in (P.concert_summary(c) for c in P.items_of(block)) if x]
    return {"artist": _head(obj, aid), "total_count": len(results), "results": results}


def radio(artist, page=1, limit=50):
    """The artist's radio (Spotify's auto-generated "<artist> Radio" playlist)."""
    from spotify import playlists as pl
    aid, uri = ref("artist", artist)
    return pl.radio_for(uri, page, limit)


def batch(artists):
    """Stats (followers, monthly listeners, world rank, top cities) for up
    to 20 artists in one request; unknown ids are listed in `not_found`."""
    def one(aid):
        try:
            return stats(aid)
        except fetch.SpotifyNotFound:
            return None

    results = fetch.run_parallel([lambda a=a: one(a) for a in artists])
    found = [r for r in results if r]
    missing = [aid for aid, r in zip(artists, results) if not r]
    return {"count": len(found), "results": found, "not_found": missing or None}
