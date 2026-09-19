"""Spotify concerts (Spotify's live-events listings, sourced from ticketing
partners): one concert's full details, upcoming concerts near a location
and the location lookup that turns a city name into the geohash Spotify
uses."""
import re

from spotify import parsers as P
from spotify.fetch import SpotifyNotFound
from spotify.shared import ref, require, run

_GEOHASH_RE = re.compile(r"^[0-9b-hjkmnp-z]{5,12}$")


def details(concert):
    """Date and doors time, venue with coordinates, line-up, genres,
    ticket offers (seller, link, sale window, price range), festival flag,
    age restriction and related concerts."""
    cid, uri = ref("concert", concert)
    data = run("concert", {"uri": uri, "authenticated": False})
    obj = require(P.dig(data, "concert"), "concert", cid)
    if obj.get("message") and not obj.get("title"):
        raise SpotifyNotFound(f"concert {cid} not found")
    location = obj.get("location") or {}
    coords = location.get("coordinates") or {}
    offers = []
    for o in P.items_of(obj.get("offers")):
        if not isinstance(o, dict):
            continue
        offers.append({
            "seller": P.clean(o.get("providerName")),
            "link": P.clean(o.get("url")),
            "sale_type": P.lower(o.get("saleType")),
            "availability": P.lower(o.get("availability")),
            "min_price": P.to_float(o.get("minPrice"), 2),
            "max_price": P.to_float(o.get("maxPrice"), 2),
            "currency": P.clean(o.get("currency")),
            "is_first_party": o.get("firstParty") if isinstance(o.get("firstParty"), bool) else None,
            "has_promo_codes": o.get("hasPromoCodes") if isinstance(o.get("hasPromoCodes"), bool) else None,
            "sale_starts_at": P.iso_datetime(P.dig(o, "dates", "startDateIsoString")),
            "sale_ends_at": P.iso_datetime(P.dig(o, "dates", "endDateIsoString")),
        })
    genres = [P.clean(P.dig(c, "data", "name")) for c in P.items_of(obj.get("concepts"))]
    return {
        "id": cid,
        "title": P.clean(obj.get("title")),
        "link": P.entity_link("concert", cid),
        "starts_at": P.local_datetime(obj.get("startDateIsoString")),
        "doors_open_at": P.local_datetime(obj.get("doorsOpenTimeIsoString")),
        "status": P.lower(obj.get("status")),
        "is_festival": obj.get("festival") if isinstance(obj.get("festival"), bool) else None,
        "age_restriction": P.clean(obj.get("ageRestriction")),
        "venue": {
            "name": P.clean(location.get("name")),
            "city": P.clean(location.get("city")),
            "region": P.clean(location.get("region")),
            "country": P.clean(location.get("country")),
            "latitude": P.to_float(coords.get("latitude")),
            "longitude": P.to_float(coords.get("longitude")),
        },
        "artists": [x for x in (P.artist(a) for a in P.items_of(obj.get("artists"))) if x] or None,
        "genres": [g for g in genres if g] or None,
        "tickets": offers or None,
        "related_concerts": [x for x in (P.concert_summary(c) for c in P.items_of(obj.get("relatedConcerts")))
                             if x] or None,
    }


def _locations(query):
    data = run("searchConcertLocations", {"query": query})
    out = []
    for loc in P.items_of(P.dig(data, "concertLocations")):
        if isinstance(loc, dict) and loc.get("geoHash"):
            out.append({"name": P.clean(loc.get("name")), "full_name": P.clean(loc.get("fullName")),
                        "country": P.clean(loc.get("country")), "geohash": loc["geoHash"],
                        "geoname_id": P.to_int(loc.get("geonameId"))})
    return out


def locations(query):
    """Cities matching `query`, each with the geohash /concerts/nearby takes."""
    return {"query": query, "results": _locations(query)}


def nearby(location):
    """Popular upcoming concerts near a city (name or geohash)."""
    if _GEOHASH_RE.match(location.lower()):
        where = {"name": None, "geohash": location.lower()}
    else:
        found = _locations(location)
        if not found:
            raise SpotifyNotFound(f"no concert location matches {location!r}")
        where = {"name": found[0]["full_name"], "geohash": found[0]["geohash"]}
    data = run("concertFeed", {"geoHash": where["geohash"]})
    concerts, seen = [], set()
    for sec in P.dig(data, "liveEventsFeed", "sections") or []:
        for row in (sec or {}).get("concerts") or []:
            group = row.get("concerts") if isinstance(row, dict) and "concerts" in row else [row]
            for c in group or []:
                parsed = P.concert_summary(c)
                if parsed and parsed["id"] not in seen:
                    seen.add(parsed["id"])
                    concerts.append(parsed)
    concerts.sort(key=lambda c: c.get("starts_at") or "")
    return {"location": where, "count": len(concerts), "results": concerts}
