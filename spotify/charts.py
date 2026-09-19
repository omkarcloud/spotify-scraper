"""Spotify charts.

  * Global weekly Top Songs / Top Albums / Top Artists from the public
    charts service (charts.spotify.com's anonymous endpoint): rank,
    previous and peak rank, weeks on chart, entry status. Per-country /
    daily / viral charts on that service need a charts.spotify.com login,
    so they are not offered there.
  * Per-country charts from the country hub: each country's "Top Songs -
    <country>" (weekly) and "Top 50 - <country>" (daily) chart playlists,
    served with position, previous position, movement and plays per row.
"""
from spotify import fetch, playlists
from spotify import parsers as P
from spotify.fetch import SpotifyNotFound
from spotify.shared import run

GLOBAL_CHARTS = {"tracks": "REGIONAL_GLOBAL_WEEKLY", "albums": "ALBUM_GLOBAL_WEEKLY",
                 "artists": "ARTIST_GLOBAL_WEEKLY"}
COUNTRY_CHARTS = {"top-songs": ("Top Songs - ", "weekly"), "top-50": ("Top 50 - ", "daily")}


def _people(values):
    return [P.clean(v.get("name")) if isinstance(v, dict) else P.clean(v) for v in values or []] or None


def _entry(e):
    data = e.get("chartEntryData") or {}
    out = {
        "rank": P.to_int(data.get("currentRank")),
        "previous_rank": P.to_int(data.get("previousRank")) or None,
        "peak_rank": P.to_int(data.get("peakRank")) or None,
        "peak_date": P.clean(data.get("peakDate")),
        "weeks_on_chart": P.to_int(data.get("appearancesOnChart")) or None,
        "consecutive_weeks_on_chart": P.to_int(data.get("consecutiveAppearancesOnChart")) or None,
        "entry_status": P.lower(data.get("entryStatus")),
    }
    track = e.get("trackMetadata")
    album = e.get("albumMetadata")
    artist = e.get("artistMetadata")
    image = lambda meta: [{"link": meta["displayImageUri"], "width": None, "height": None}] \
        if meta.get("displayImageUri") else None
    artists = lambda meta: [{"id": P.id_of(a.get("spotifyUri")), "name": P.clean(a.get("name")),
                             "link": P.link_of(a.get("spotifyUri"))}
                            for a in meta.get("artists") or [] if isinstance(a, dict)] or None
    if isinstance(track, dict):
        out["track"] = {"id": P.id_of(track.get("trackUri")), "name": P.clean(track.get("trackName")),
                        "link": P.link_of(track.get("trackUri")), "artists": artists(track),
                        "labels": _people(track.get("labels")),
                        "producers": _people(track.get("producers")),
                        "songwriters": _people(track.get("songWriters")),
                        "release_date": P.clean(track.get("releaseDate")), "images": image(track)}
    elif isinstance(album, dict):
        out["album"] = {"id": P.id_of(album.get("albumUri")), "name": P.clean(album.get("albumName")),
                        "link": P.link_of(album.get("albumUri")), "artists": artists(album),
                        "labels": _people(album.get("labels")),
                        "release_date": P.clean(album.get("releaseDate")), "images": image(album)}
    elif isinstance(artist, dict):
        out["artist"] = {"id": P.id_of(artist.get("artistUri")), "name": P.clean(artist.get("artistName")),
                         "link": P.link_of(artist.get("artistUri")), "images": image(artist)}
    return out


def _global(kind):
    body = fetch.charts_overview() or {}
    for chart in body.get("chartEntryViewResponses") or []:
        meta = P.dig(chart, "displayChart", "chartMetadata") or {}
        if meta.get("alias") != GLOBAL_CHARTS[kind]:
            continue
        dims = meta.get("dimensions") or {}
        return {
            "chart": {"name": P.clean(meta.get("readableTitle")),
                      "date": P.clean(P.dig(chart, "displayChart", "date")),
                      "period": P.lower(dims.get("recurrence")), "country": "global",
                      "earliest_date": P.clean(dims.get("earliestDate")),
                      "description": P.clean(P.dig(chart, "displayChart", "description"))},
            "highlights": [P.clean(h.get("text")) for h in chart.get("highlights") or []
                           if isinstance(h, dict) and h.get("text")] or None,
            "results": [_entry(e) for e in chart.get("entries") or [] if isinstance(e, dict)],
        }
    raise SpotifyNotFound(f"global {kind} chart missing from the charts service")


def top_tracks():
    """Weekly Top Songs: Global (50 entries)."""
    return _global("tracks")


def top_albums():
    """Weekly Top Albums: Global (50 entries)."""
    return _global("albums")


def top_artists():
    """Weekly Top Artists: Global (50 entries)."""
    return _global("artists")


def country_chart(country, chart="top-songs", limit=200):
    """A country's chart playlist — top-songs (weekly Top Songs, up to 200
    rows) or top-50 (daily Top 50) — with position, previous position,
    movement and plays per row. country=GLOBAL for the global lists."""
    prefix, period = COUNTRY_CHARTS[chart]
    hub_country = "US" if country == "GLOBAL" else country
    data = run("countryHubsPage", {"countryCode": hub_country})
    shelves = P.dig(data, "countryHub", "shelves") or []
    rows = next((P.items_of(s.get("items")) for s in shelves if (s or {}).get("contentId") == "CHARTS"), [])
    candidates = [P.playlist(r) for r in rows]
    candidates = [c for c in candidates if c and (c.get("name") or "").startswith(prefix)]
    is_global = lambda c: c["name"].endswith("Global")
    pick = next((c for c in candidates if is_global(c) == (country == "GLOBAL")), None)
    if not pick:
        raise SpotifyNotFound(f"Spotify has no {chart} chart for {country}")
    detail = playlists.details(pick["id"], limit=limit)
    return {
        "chart": {"name": detail.get("name"), "country": country.lower() if country != "GLOBAL" else "global",
                  "period": period, "updated_at": detail.get("updated_at"),
                  "new_entries": (detail.get("chart") or {}).get("new_entries"),
                  "playlist": {"id": detail.get("id"), "link": detail.get("link"),
                               "followers": detail.get("followers")}},
        "results": [{**(row.get("chart") or {}), "track": row.get("item")}
                    for row in detail.get("items") or []],
    }
