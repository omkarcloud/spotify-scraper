"""Spotify reference parsing: ONE param per input that auto-detects its
forms (tripadvisor QueryOrLinkField convention — never a sibling
`url`/`id` pair). Every resolver returns a plain string so the validated
params stay usable as a response-cache key:

  track     4uLU6hMCjMI75M1A2tKUQC
            | spotify:track:4uLU6hMCjMI75M1A2tKUQC
            | https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC?si=…
            | https://open.spotify.com/intl-de/track/…  (locale prefix)
            | https://open.spotify.com/embed/track/…    (embed link)
            | https://spotify.link/AbC123               (short link, expanded
                                                         by the endpoint)
  album / artist / playlist / episode / chapter / concert — same forms
  podcast / audiobook   show id | spotify:show:… | /show/ link
  user      username (any chars Spotify allows) | spotify:user:… | /user/ link
  category  0JQ5DAqbMKFEC4WFtoNRpw | spotify:page:… | /genre/<id> link
  section   0JQ5IMCbQBLoSVpnseIhn6 | spotify:section:… | /section/<id> link

A short link resolves to the literal link here (no network in validation);
`entity_id()` expands it at request time via fetch.expand_short_link.
"""
import re
from urllib.parse import unquote, urlparse

_ID_RE = re.compile(r"^[0-9A-Za-z]{22}$")
_SHORT_HOSTS = ("spotify.link", "spotify.app.link")
_LOCALE_SEGMENT_RE = re.compile(r"^intl-[a-z]{2}(?:-[a-z]{2})?$", re.I)

# public kind -> (uri/link kinds accepted, uri kind used upstream)
KINDS = {
    "track": (("track",), "track"),
    "album": (("album",), "album"),
    "artist": (("artist",), "artist"),
    "playlist": (("playlist",), "playlist"),
    "episode": (("episode",), "episode"),
    "chapter": (("episode", "chapter"), "episode"),
    "podcast": (("show",), "show"),
    "audiobook": (("show", "audiobook"), "show"),
    "concert": (("concert",), "concert"),
    "user": (("user",), "user"),
    "category": (("page", "genre"), "page"),
    "section": (("section",), "section"),
}

_EXAMPLES = {
    "track": "4uLU6hMCjMI75M1A2tKUQC", "album": "4aawyAB9vmqN3uQ7FjRGTy",
    "artist": "06HL4z0CvFAxyc27GXpf02", "playlist": "37i9dQZEVXbMDoHDwVN2tF",
    "episode": "7rACFBcIIDWROlUB0MoGkW", "chapter": "4vxkqkMeYRgpMzQa7yyKN0",
    "podcast": "4rOoJ6Egrf8K2IrywzwOMk", "audiobook": "40ygvasZaqVMMBkgYoUy8C",
    "concert": "2OvGgoad28kYNzpw6hutns", "user": "spotify",
    "category": "0JQ5DAqbMKFEC4WFtoNRpw", "section": "0JQ5IMCbQBLoSVpnseIhn6",
}
_LINK_KIND = {"podcast": "show", "audiobook": "show", "chapter": "episode",
              "category": "genre"}


def _error(kind):
    link_kind = _LINK_KIND.get(kind, kind)
    return ValueError(f"{kind} must be a Spotify {kind} id (e.g. {_EXAMPLES[kind]}), a "
                      f"spotify:{KINDS[kind][1]}:… URI or an open.spotify.com/{link_kind}/ link")


def is_short_link(value):
    host = (urlparse(value if "://" in value else "https://" + value).hostname or "").lower()
    return host in _SHORT_HOSTS


def _valid_id(kind, value):
    if kind == "user":
        return bool(value) and len(value) <= 128 and "/" not in value
    return bool(_ID_RE.match(value))


def parse_link(value):
    """open.spotify.com link -> (kind, id) or (None, None). Handles the
    intl-xx locale prefix, /embed/ links and ?si= share params."""
    url = value if "://" in value else "https://" + value.lstrip("/")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not (host == "open.spotify.com" or host == "play.spotify.com"):
        return None, None
    segments = [s for s in parsed.path.split("/") if s]
    if segments and _LOCALE_SEGMENT_RE.match(segments[0]):
        segments = segments[1:]
    if segments and segments[0] == "embed":
        segments = segments[1:]
    if len(segments) >= 2:
        return segments[0].lower(), unquote(segments[1])
    return None, None


def resolve(kind, value):
    """Any accepted form -> the bare id (or the short link, expanded later)."""
    accepted, _ = KINDS[kind]
    value = str(value or "").strip()
    if not value:
        raise _error(kind)
    if value.startswith("spotify:"):
        parts = value.split(":")
        # spotify:user:<name>:playlist:<id> (old playlist URIs)
        if len(parts) == 5 and parts[1] == "user" and parts[3] == "playlist" and kind == "playlist":
            parts = ["spotify", "playlist", parts[4]]
        if len(parts) == 3 and parts[1] in accepted and _valid_id(kind, unquote(parts[2])):
            return unquote(parts[2])
        raise _error(kind)
    if is_short_link(value):
        return value if "://" in value else "https://" + value
    if "spotify.com" in value.lower():
        link_kind, rid = parse_link(value)
        if link_kind in accepted and rid and _valid_id(kind, rid):
            return rid
        raise _error(kind)
    if _valid_id(kind, value):
        return value
    raise _error(kind)


def resolve_list(kind, values, max_items):
    """Comma-separated refs -> unique ids (short links are not accepted in lists)."""
    out = []
    for raw in values:
        rid = resolve(kind, raw)
        if rid.startswith("http"):
            raise ValueError(f"short links are not accepted in a list; paste full {kind} links or ids")
        if rid not in out:
            out.append(rid)
    if not out:
        raise ValueError(f"give at least one {kind}")
    if len(out) > max_items:
        raise ValueError(f"at most {max_items} {kind}s per request")
    return out


def entity_id(kind, ref):
    """A resolved ref -> bare id, expanding a short link over the network."""
    if not ref.startswith("http"):
        return ref
    from spotify import fetch
    target = fetch.expand_short_link(ref)
    link_kind, rid = parse_link(target)
    if link_kind in KINDS[kind][0] and rid and _valid_id(kind, rid):
        return rid
    raise ValueError(f"that short link points at a {link_kind or 'non-Spotify'} page, not a {kind}")


def uri(kind, rid):
    return f"spotify:{KINDS[kind][1]}:{rid}"


def kind_and_id(value):
    """Any Spotify URI or link -> (uri kind, id); (None, None) if unrecognised."""
    value = str(value or "").strip()
    if value.startswith("spotify:"):
        parts = value.split(":")
        if len(parts) == 5 and parts[1] == "user" and parts[3] == "playlist":
            return "playlist", parts[4]
        if len(parts) >= 3:
            return parts[1], unquote(parts[2])
        return None, None
    return parse_link(value)
