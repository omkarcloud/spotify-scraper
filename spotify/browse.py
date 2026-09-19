"""Spotify browse surfaces: the Browse-all category grid, one category
(genre / mood) page with its shelves, one shelf paginated, the anonymous
home feed and a country's hub (its charts, popular artists and albums,
trending songs)."""
from spotify import ops
from spotify import parsers as P
from spotify.fetch import SpotifyBadRequest
from spotify.shared import paged_result, ref, require, run

HUB_SHELVES = {"CHARTS": "charts", "POPULAR_ARTISTS": "popular_artists",
               "POPULAR_ALBUMS": "popular_albums", "TRENDING_SONGS": "trending_songs"}


def _label(block):
    if isinstance(block, dict):
        return P.clean(block.get("transformedLabel") or block.get("translatedBaseText"))
    return P.clean(block)


def _card(row):
    """Browse-all grid cell -> category."""
    uri = (row or {}).get("uri")
    card = P.dig(P.unwrap((row or {}).get("content")), "data", "cardRepresentation") \
        or P.dig(row, "content", "data", "data", "cardRepresentation") or {}
    if not uri:
        return None
    return {"id": P.id_of(uri), "name": _label(card.get("title")),
            "link": P.link_of(uri) if P.kind_of(uri) == "page" else None,
            "images": P.images(P.dig(card, "artwork", "sources"))}


def _section(sec, items_key="sectionItems"):
    uri = (sec or {}).get("uri")
    data = (sec or {}).get("data") or {}
    block = (sec or {}).get(items_key) or {}
    results = [x for x in (P.item((r or {}).get("content")) for r in P.items_of(block)) if x]
    return {"id": P.id_of(uri), "title": _label(data.get("title")),
            "subtitle": _label(data.get("subtitle")),
            "total_count": P.total_of(block), "results": results}


def categories():
    """Every Browse-all category (genres, moods, charts, podcasts, …)."""
    data = run("browseAll", {"pagePagination": {"offset": 0, "limit": 10},
                             "sectionPagination": {"offset": 0, "limit": 99},
                             "browseEndUserIntegration": ops.WEB_PLAYER_INTEGRATION})
    out = []
    for sec in P.items_of(P.dig(data, "browseStart", "sections")):
        for row in P.items_of((sec or {}).get("sectionItems")):
            card = _card(row)
            if card and card["name"]:
                out.append(card)
    return {"count": len(out), "results": out}


def category(category, section_limit=20):
    """One category page (e.g. Pop): header and each shelf with its first
    `section_limit` items; a shelf's `id` pages further via /browse/section."""
    cid, uri = ref("category", category)
    data = run("browsePage", {"uri": uri, "pagePagination": {"offset": 0, "limit": 50},
                              "sectionPagination": {"offset": 0, "limit": section_limit},
                              "browseEndUserIntegration": ops.WEB_PLAYER_INTEGRATION,
                              "includeEpisodeContentRatingsV2": False})
    obj = require(P.dig(data, "browse"), "category", cid)
    header = obj.get("header") or {}
    sections = [s for s in (_section(x) for x in P.items_of(obj.get("sections"))) if s["results"]]
    return {"id": cid, "name": _label(header.get("title")), "link": P.entity_link("genre", cid),
            "images": P.image_sources(header, "backgroundImage"), "sections": sections}


def section(section, page=1, limit=50):
    """One browse shelf, paginated."""
    sid, uri = ref("section", section)
    data = run("browseSection", {"uri": uri, "pagination": {"offset": P.offset_of(page, limit),
                                                            "limit": limit},
                                 "browseEndUserIntegration": ops.WEB_PLAYER_INTEGRATION,
                                 "includeEpisodeContentRatingsV2": False})
    obj = require(P.dig(data, "browseSection"), "section", sid)
    parsed = _section(dict(obj, uri=uri))
    if not parsed["results"] and page == 1:
        raise SpotifyBadRequest(f"section {sid} is empty or not a browse shelf "
                                "(take a section id from /spotify/browse/category)")
    return paged_result("results", parsed["results"], page, limit, parsed["total_count"],
                        section={"id": sid, "title": parsed["title"]})


def home(section_limit=20, timezone="UTC"):
    """The home feed Spotify shows logged-out visitors (trending songs,
    popular artists / albums / radio, featured charts)."""
    data = run("home", {"timeZone": timezone, "sp_t": "", "facet": "",
                        "sectionItemsLimit": section_limit,
                        "homeEndUserIntegration": ops.WEB_PLAYER_INTEGRATION})
    sections = P.items_of(P.dig(data, "home", "sectionContainer", "sections"))
    out = [s for s in (_section(x) for x in sections) if s["results"]]
    return {"sections": out}


def country_hub(country):
    """A country's music hub: its chart playlists, popular artists, popular
    albums and trending songs."""
    data = run("countryHubsPage", {"countryCode": country})
    hub = P.dig(data, "countryHub") or {}
    out = {"country": P.dig(hub, "country", "isoCountryCode") or country}
    for shelf in hub.get("shelves") or []:
        key = HUB_SHELVES.get((shelf or {}).get("contentId"))
        if key:
            out[key] = [x for x in (P.item(r) for r in P.items_of(shelf.get("items"))) if x] or None
    for key in HUB_SHELVES.values():
        out.setdefault(key, None)
    return out
