"""Spotify payload normalizers: pathfinder GraphQL / spclient / charts JSON
-> one clean snake_case shape per entity type.

Conventions: `link` for web URLs (open.spotify.com), `images`
[{link, width, height}] largest first, `release_date` as YYYY-MM-DD /
YYYY-MM / YYYY with `release_date_precision`, UTC ISO datetimes for
timestamps, `duration_ms` + `duration_text` ("3:47"), counts as ints
(Spotify sends playcount as a string), `is_*` / `has_*` booleans, null for
anything missing. Mixed lists (search top results, browse/home shelves)
carry a `type` on every item.

Upstream fields dropped on purpose (and why):
  * __typename / *ResponseWrapper envelopes (GraphQL plumbing), `uri`
    (duplicates type + id), sharingInfo.shareId and the `?si=` share
    param (per-request tracking ids), `uid` / `_uri` (list-row ids),
    attributes like request_id / correlation-id (tracking).
  * visualIdentity / extractedColors / colour hex / backgroundColor
    (presentation only), headerImage `maxWidth` variants beyond the
    largest (kept as header_images), itemV3 (a duplicate of itemV2).
  * saved / following / playedState / currentUserCapabilities /
    basePermission / abuseReportingEnabled / canRate (the anonymous
    viewer's own state — always false/empty).
  * htmlDescription when a plain `description` exists (same text, HTML).
  * audio.items / defaultAudioFileObject on episodes and chapters (signed
    CDN stream URLs); only the public 30 s preview link is kept.
  * associationsV3 beyond the has_video flag, relinkingInformation
    (market relinking internals), watchFeedEntrypoint, accessInfo
    (paywall UI copy — is_paywalled is kept), meV2 (viewer timezone).
"""
import html as _html
import re
from datetime import datetime, timezone

SITE = "https://open.spotify.com"
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>|</p>\s*<p>", re.I)

# uri kind -> link path segment
_LINK_SEGMENT = {"track": "track", "album": "album", "artist": "artist", "playlist": "playlist",
                 "show": "show", "episode": "episode", "user": "user", "concert": "concert",
                 "genre": "genre", "page": "genre", "audiobook": "show", "chapter": "episode",
                 "prerelease": "prerelease", "author": None, "section": "section"}
_NOT_FOUND_TYPES = {"NotFound", "GenericError"}
_COPYRIGHT_TYPES = {"C": "copyright", "P": "phonogram"}


# ---- value helpers ----------------------------------------------------------

def clean(value):
    """'' / [] / {} -> None (uniform nulls); strings are stripped."""
    if isinstance(value, str):
        value = value.strip()
    return None if value in ("", [], {}, None) else value


def to_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def to_float(value, digits=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, digits) if digits is not None else number


def dig(obj, *path, default=None):
    """Nested .get() through dicts; a list step takes its first element."""
    for key in path:
        if isinstance(obj, list):
            obj = obj[0] if obj else None
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key)
    return default if obj is None else obj


def items_of(block):
    """{items: [...]} | [...] -> list (never None)."""
    if isinstance(block, list):
        return block
    if isinstance(block, dict):
        return block.get("items") or []
    return []


def total_of(block):
    return to_int(block.get("totalCount")) if isinstance(block, dict) else None


def unwrap(obj):
    """Strip the ResponseWrapper / {data: …} / {item: {data}} / {entity: {data}}
    envelopes around an entity."""
    for _ in range(4):
        if not isinstance(obj, dict):
            return obj
        if "item" in obj and isinstance(obj["item"], dict) and len(obj) <= 3:
            obj = obj["item"]
            continue
        if "entity" in obj and isinstance(obj["entity"], dict) and "data" not in obj:
            obj = obj["entity"]
            continue
        typename = obj.get("__typename") or ""
        if "data" in obj and (typename.endswith("Wrapper") or not typename
                              or set(obj) <= {"__typename", "data", "_uri", "uid", "uri", "content"}):
            inner = obj.get("data")
            if isinstance(inner, dict):
                obj = inner
                continue
        return obj
    return obj


def typename(obj):
    return obj.get("__typename") if isinstance(obj, dict) else None


def is_missing(obj):
    """No usable entity: not a dict, NotFound / GenericError, or
    RestrictedContent (shared.require reports that one as market-locked)."""
    return not isinstance(obj, dict) or typename(obj) in _NOT_FOUND_TYPES or is_restricted(obj)


def is_restricted(obj):
    return typename(obj) == "RestrictedContent"


def id_of(uri):
    if not isinstance(uri, str) or ":" not in uri:
        return None
    return uri.rsplit(":", 1)[-1] or None


def kind_of(uri):
    if not isinstance(uri, str) or not uri.startswith("spotify:"):
        return None
    parts = uri.split(":")
    if len(parts) == 5 and parts[1] == "user" and parts[3] == "playlist":
        return "playlist"
    return parts[1] if len(parts) >= 3 else None


def link_of(uri):
    """spotify:<kind>:<id> -> https://open.spotify.com/<segment>/<id>."""
    kind = kind_of(uri)
    segment = _LINK_SEGMENT.get(kind)
    rid = id_of(uri)
    if not segment or not rid:
        return None
    return f"{SITE}/{segment}/{rid}"


def entity_link(kind, rid):
    segment = _LINK_SEGMENT.get(kind, kind)
    return f"{SITE}/{segment}/{rid}" if segment and rid else None


def strip_html(text):
    if not text:
        return None
    text = _BR_RE.sub("\n", str(text))
    text = _html.unescape(_TAG_RE.sub("", text))
    lines = [line.strip() for line in text.replace("\r", "").split("\n")]
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return out or None


# i.scdn.co image ids encode the rendition: chars 8-16 of the hash are the
# size code (ab67616d|00001e02|… = 300 px cover). Used when the payload
# leaves width/height out (top tracks, search rows, chart images).
_IMAGE_SIZE_CODES = {"00004851": 64, "00001e02": 300, "0000b273": 640,       # album covers
                     "0000f178": 160, "00005174": 320, "0000e5eb": 640,       # artist avatars
                     "00003b82": 64, "0000ee85": 300,                         # user avatars
                     "0000f68d": 64, "0000a39a": 300, "00005f1f": 640}       # show / episode art
_IMAGE_ID_RE = re.compile(r"/image/([0-9a-f]{16})")


def _size_from_link(link):
    match = _IMAGE_ID_RE.search(link or "")
    return _IMAGE_SIZE_CODES.get(match.group(1)[8:]) if match else None


def images(sources):
    """[{url, width, height}] -> [{link, width, height}] largest first, deduped."""
    out, seen = [], set()
    for src in sources or []:
        if not isinstance(src, dict) or not src.get("url") or src["url"] in seen:
            continue
        seen.add(src["url"])
        width = to_int(src.get("width") or src.get("maxWidth"))
        height = to_int(src.get("height") or src.get("maxHeight"))
        if width is None and height is None:
            width = height = _size_from_link(src["url"])
        out.append({"link": src["url"], "width": width, "height": height})
    out.sort(key=lambda i: -(i["width"] or 0))
    return out or None


def image_sources(obj, *keys):
    """First non-empty `sources` list under any of the keys (coverArt,
    avatarImage, image, images.items[0], …)."""
    for key in keys:
        block = obj.get(key) if isinstance(obj, dict) else None
        if isinstance(block, dict) and "data" in block and isinstance(block["data"], dict):
            block = block["data"]
        if isinstance(block, dict) and block.get("sources"):
            return images(block["sources"])
        if isinstance(block, dict) and block.get("items"):
            first = block["items"][0] if block["items"] else None
            if isinstance(first, dict) and first.get("sources"):
                return images(first["sources"])
    return None


def iso_datetime(value):
    """Any ISO string -> UTC 'YYYY-MM-DDTHH:MM:SSZ' (offsets converted)."""
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return None


def local_datetime(value):
    """'2026-12-05T15:00+05:30' -> '2026-12-05T15:00:00+05:30' (venue-local
    time kept with its offset — the time printed on the ticket)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def release_date(block):
    """{isoString, precision, year, month, day} -> (date string, precision).
    DAY -> YYYY-MM-DD, MONTH -> YYYY-MM, YEAR -> YYYY; MINUTE/SECOND -> the
    UTC calendar date."""
    if not isinstance(block, dict):
        return None, None
    precision = str(block.get("precision") or "").upper() or None
    iso = block.get("isoString")
    year, month, day = block.get("year"), block.get("month"), block.get("day")
    if iso and not (year and month and day):
        stamp = iso_datetime(iso) or (iso[:10] + "T00:00:00Z" if len(iso) >= 10 else None)
        if stamp:
            year, month, day = year or int(stamp[:4]), month or int(stamp[5:7]), day or int(stamp[8:10])
    if not year:
        return None, None
    if precision == "YEAR" or (precision is None and not month):
        return f"{int(year):04d}", "year"
    if precision == "MONTH" or not day:
        return f"{int(year):04d}-{int(month or 1):02d}", "month"
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}", "day"


def duration_text(ms):
    ms = to_int(ms)
    if ms is None:
        return None
    seconds = ms // 1000
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def duration_fields(block):
    ms = to_int(block.get("totalMilliseconds")) if isinstance(block, dict) else to_int(block)
    return {"duration_ms": ms, "duration_text": duration_text(ms)}


def is_explicit(obj):
    label = dig(obj, "contentRating", "label")
    if label:
        return label == "EXPLICIT"
    labels = dig(obj, "contentRatingV2", "labels") or dig(obj, "contentRatingsV2", "labels")
    if isinstance(labels, list):
        return "EXPLICIT" in labels
    return None


def playable(obj):
    block = obj.get("playability") if isinstance(obj, dict) else None
    if not isinstance(block, dict):
        return None
    return bool(block.get("playable")) if "playable" in block else None


def playability_reason(obj):
    reason = dig(obj, "playability", "reason")
    return reason.lower() if isinstance(reason, str) else None


def lower(value):
    return value.lower() if isinstance(value, str) and value else None


def snake_enum(value):
    """'CONTENT_TYPE_PODCAST' -> 'podcast'-style lower-case tokens."""
    if not isinstance(value, str) or not value:
        return None
    return value.lower().replace("content_type_", "").replace("entity_type_", "")


def ordered(obj, first, last=()):
    """Reorder keys: `first` in order, the rest, then `last`."""
    out = {k: obj[k] for k in first if k in obj}
    out.update({k: v for k, v in obj.items() if k not in out and k not in last})
    out.update({k: obj[k] for k in last if k in obj})
    return out


def attributes_map(attrs):
    return {a.get("key"): a.get("value") for a in attrs or [] if isinstance(a, dict) and a.get("key")}


# ---- small shared shapes ----------------------------------------------------------

def artist_ref(obj):
    obj = unwrap(obj)
    if not isinstance(obj, dict):
        return None
    uri = obj.get("uri") or obj.get("_uri")
    name = dig(obj, "profile", "name") or obj.get("name")
    if not uri and not name:
        return None
    return {"id": id_of(uri), "name": clean(name), "link": link_of(uri)}


def artist_refs(block):
    return [a for a in (artist_ref(x) for x in items_of(block)) if a] or None


def album_ref(obj):
    obj = unwrap(obj)
    if not isinstance(obj, dict) or not (obj.get("uri") or obj.get("name")):
        return None
    date, precision = release_date(obj.get("date"))
    return {
        "id": id_of(obj.get("uri")) or clean(obj.get("id")),
        "name": clean(obj.get("name")),
        "link": link_of(obj.get("uri")),
        "release_date": date,
        "images": image_sources(obj, "coverArt"),
    }


def owner_ref(obj):
    obj = unwrap(obj)
    if not isinstance(obj, dict):
        return None
    uri = obj.get("uri")
    return {"id": clean(obj.get("username")) or id_of(uri), "name": clean(obj.get("name")),
            "link": link_of(uri)} if (uri or obj.get("name")) else None


def copyrights(block):
    out = []
    for c in items_of(block):
        if isinstance(c, dict) and c.get("text"):
            out.append({"type": _COPYRIGHT_TYPES.get(c.get("type"), lower(c.get("type"))),
                        "text": c["text"].strip()})
    return out or None


def show_ref(obj):
    obj = unwrap(obj)
    if not isinstance(obj, dict) or not obj.get("uri"):
        return None
    return {"id": id_of(obj["uri"]), "name": clean(obj.get("name")), "link": link_of(obj["uri"]),
            "publisher": clean(dig(obj, "publisher", "name")),
            "images": image_sources(obj, "coverArt")}


def preview_link(obj):
    """Public 30 s preview (mp3) of an episode / chapter / track."""
    link = dig(obj, "previewPlayback", "audioPreview", "cdnUrl") or dig(obj, "audioPreview", "url")
    return clean(link)


# ---- entities -------------------------------------------------------------------------

def track(obj, with_album=True):
    obj = unwrap(obj)
    if is_missing(obj):
        return None
    uri = obj.get("uri")
    album = obj.get("albumOfTrack") or {}
    artists = artist_refs(obj.get("artists"))
    if not artists:   # getTrack splits them into firstArtist + otherArtists
        artists = ((artist_refs(obj.get("firstArtist")) or [])
                   + (artist_refs(obj.get("otherArtists")) or [])) or None
    videos = dig(obj, "associationsV3", "videoAssociations", "totalCount")
    out = {
        "type": "track",
        "id": id_of(uri) or clean(obj.get("id")),
        "name": clean(obj.get("name")),
        "link": link_of(uri),
        "track_number": to_int(obj.get("trackNumber")),
        "disc_number": to_int(obj.get("discNumber")),
        **duration_fields(obj.get("duration") or obj.get("trackDuration")),
        "is_explicit": is_explicit(obj),
        "is_playable": playable(obj),
        "has_video": (to_int(videos) or 0) > 0 if videos is not None else None,
        "playcount": to_int(obj.get("playcount")),
        "artists": artists,
    }
    if with_album:
        out["album"] = album_ref(album)
    return out


def album(obj):
    obj = unwrap(obj)
    if is_missing(obj):
        return None
    uri = obj.get("uri")
    date, precision = release_date(obj.get("date"))
    out = {
        "type": "album",
        "id": id_of(uri) or clean(obj.get("id")),
        "name": clean(obj.get("name")),
        "link": link_of(uri),
        "album_type": lower(obj.get("type")),
        "release_date": date,
        "release_date_precision": precision,
        "label": clean(obj.get("label")),
        "total_tracks": to_int(dig(obj, "tracks", "totalCount")) or to_int(dig(obj, "tracksV2", "totalCount")),
        "is_playable": playable(obj),
        "is_prerelease": obj.get("isPreRelease") if isinstance(obj.get("isPreRelease"), bool)
        else obj.get("isAlbumPreRelease") if isinstance(obj.get("isAlbumPreRelease"), bool) else None,
        "artists": artist_refs(obj.get("artists")),
        "images": image_sources(obj, "coverArt"),
        "copyrights": copyrights(obj.get("copyright")),
    }
    return out


def release_group(obj):
    """Discography / appearsOn row: {releases: {items: [album, …]}} -> the
    first release (the others are regional duplicates)."""
    first = (items_of((obj or {}).get("releases")) or [None])[0]
    return album(first) if first else album(obj)


def artist(obj):
    obj = unwrap(obj)
    if is_missing(obj):
        return None
    uri = obj.get("uri")
    verified = dig(obj, "onPlatformReputationTrait", "verification", "isVerified")
    if verified is None:
        verified = dig(obj, "profile", "verified")
    return {
        "type": "artist",
        "id": id_of(uri) or clean(obj.get("id")),
        "name": clean(dig(obj, "profile", "name")),
        "link": link_of(uri),
        "is_verified": verified if isinstance(verified, bool) else None,
        "images": image_sources(obj.get("visuals") or {}, "avatarImage"),
    }


def playlist(obj):
    obj = unwrap(obj)
    if is_missing(obj):
        return None
    uri = obj.get("uri") or obj.get("_uri")
    attrs = attributes_map(obj.get("attributes"))
    return {
        "type": "playlist",
        "id": id_of(uri),
        "name": clean(obj.get("name")),
        "link": link_of(uri),
        "description": strip_html(obj.get("description")),
        "format": clean(obj.get("format")),
        "followers": to_int(obj.get("followers")),
        "owner": owner_ref(dig(obj, "ownerV2")),
        "updated_at": iso_datetime(attrs.get("last_updated")),
        "images": image_sources(obj, "images"),
    }


def podcast(obj):
    obj = unwrap(obj)
    if is_missing(obj):
        return None
    uri = obj.get("uri")
    return {
        "type": "podcast",
        "id": id_of(uri) or clean(obj.get("id")),
        "name": clean(obj.get("name")),
        "link": link_of(uri),
        "publisher": clean(dig(obj, "publisher", "name")),
        "media_type": lower(obj.get("mediaType")),
        "topics": [clean(t.get("title")) for t in items_of(obj.get("topics"))
                   if isinstance(t, dict) and t.get("title")] or None,
        "images": image_sources(obj, "coverArt"),
    }


def episode(obj):
    obj = unwrap(obj)
    if is_missing(obj):
        return None
    uri = obj.get("uri")
    released_at = iso_datetime(dig(obj, "releaseDate", "isoString"))
    date, _ = release_date(obj.get("releaseDate"))
    show = show_ref(dig(obj, "podcastV2") or {}) or show_ref(dig(obj, "audiobookV2") or {})
    out = {
        "type": "chapter" if typename(obj) == "Chapter" else "episode",
        "id": id_of(uri) or clean(obj.get("id")),
        "name": clean(obj.get("name")),
        "link": link_of(uri),
        "description": strip_html(obj.get("htmlDescription")) or clean(obj.get("description")),
        "release_date": date,
        "released_at": released_at,
        **duration_fields(obj.get("duration")),
        "is_explicit": is_explicit(obj),
        "is_playable": playable(obj),
        "is_paywalled": dig(obj, "restrictions", "paywallContent")
        if isinstance(dig(obj, "restrictions", "paywallContent"), bool) else None,
        "media_types": [lower(m) for m in obj.get("mediaTypes") or [] if isinstance(m, str)] or None,
        "preview_link": preview_link(obj),
        "images": image_sources(obj, "coverArt"),
    }
    if out["type"] == "chapter":
        out["audiobook"] = show
    else:
        out["podcast"] = show
    return out


def price(block):
    if not isinstance(block, dict):
        return None
    final = block.get("finalPrice") or {}
    listed = block.get("finalListPrice") or {}
    amount = to_float(final.get("amount"), 2)
    list_amount = to_float(listed.get("amount"), 2)
    if amount is None and list_amount is None:
        return None
    return {"amount": amount, "list_amount": list_amount,
            "currency": clean(final.get("currency") or listed.get("currency"))}


def rating(block):
    avg = dig(block, "averageRating") if isinstance(block, dict) else None
    if not isinstance(avg, dict) or avg.get("average") is None:
        return None
    return {"average": to_float(avg.get("average"), 2),
            "count": to_int(avg.get("totalRatings"))}


def audiobook(obj):
    obj = unwrap(obj)
    if is_missing(obj):
        return None
    uri = obj.get("uri")
    date, _ = release_date(obj.get("publishDate"))
    return {
        "type": "audiobook",
        "id": id_of(uri) or clean(obj.get("id")),
        "name": clean(obj.get("name")),
        "link": link_of(uri),
        "authors": [clean(a.get("name")) for a in obj.get("authorsV2") or [] if isinstance(a, dict)] or None,
        "narrators": [clean(n.get("name")) for n in obj.get("narrators") or [] if isinstance(n, dict)] or None,
        "publisher": clean(dig(obj, "publisher", "name")),
        "publish_date": date,
        **duration_fields(obj.get("duration")),
        "is_explicit": is_explicit(obj),
        "images": image_sources(obj, "coverArt"),
    }


def user(obj):
    obj = unwrap(obj)
    if is_missing(obj):
        return None
    uri = obj.get("uri")
    return {
        "type": "user",
        "id": clean(obj.get("username")) or clean(obj.get("id")) or id_of(uri),
        "name": clean(obj.get("displayName") or obj.get("name")),
        "link": link_of(uri),
        "images": image_sources(obj, "avatar"),
    }


def genre(obj):
    obj = unwrap(obj)
    if is_missing(obj):
        return None
    uri = obj.get("uri")
    return {"type": "genre", "id": id_of(uri), "name": clean(obj.get("name")),
            "link": link_of(uri), "images": image_sources(obj, "image")}


def concert_summary(obj):
    obj = unwrap(obj)
    if is_missing(obj) or not obj.get("uri"):
        return None
    location = obj.get("location") or {}
    return {
        "type": "concert",
        "id": id_of(obj.get("uri")),
        "title": clean(obj.get("title")),
        "link": link_of(obj.get("uri")),
        "starts_at": local_datetime(obj.get("startDateIsoString")),
        "is_festival": obj.get("festival") if isinstance(obj.get("festival"), bool) else None,
        "venue": clean(location.get("name")),
        "city": clean(location.get("city")),
        "artists": [a for a in (artist(x) for x in items_of(obj.get("artists"))) if a] or None,
    }


_ITEM_PARSERS = {
    "Track": track, "Album": album, "PreRelease": album, "Artist": artist,
    "Playlist": playlist, "Podcast": podcast, "Episode": episode, "Chapter": episode,
    "Audiobook": audiobook, "User": user, "Genre": genre, "ConcertV2": concert_summary,
    "Concert": concert_summary,
}
_KIND_PARSERS = {"track": track, "album": album, "artist": artist, "playlist": playlist,
                 "show": podcast, "episode": episode, "user": user, "genre": genre,
                 "concert": concert_summary}


def item(obj):
    """Any typed entity (mixed shelves / search top results) -> its parsed
    shape, or None for errors, restricted content and unknown types."""
    obj = unwrap(obj)
    if not isinstance(obj, dict):
        return None
    parse = _ITEM_PARSERS.get(typename(obj))
    if parse is None:
        parse = _KIND_PARSERS.get(kind_of(obj.get("uri") or obj.get("_uri")))
    return parse(obj) if parse else None


def parse_list(block, parse):
    return [x for x in (parse(i) for i in items_of(block)) if x]


# ---- pagination ---------------------------------------------------------------

def pagination(page, per_page, total_count=None, has_more=False):
    """The block route_glue.paginate() lifts into the flat gateway shape."""
    if total_count is not None and per_page:
        total_pages = (int(total_count) + int(per_page) - 1) // int(per_page)
    else:
        total_pages = page + 1 if has_more else page
    return {"page": page, "items_per_page": per_page,
            "total_pages": total_pages, "total_count": total_count}


def offset_of(page, limit):
    return (page - 1) * limit
