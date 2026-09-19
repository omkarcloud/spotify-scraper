"""Link resolver: any Spotify link, URI or short link -> type, id, canonical
link and URI (handy before calling the typed endpoints)."""
from spotify import fetch, refs
from spotify import parsers as P

_PUBLIC_TYPES = {"track": "track", "album": "album", "artist": "artist", "playlist": "playlist",
                 "show": "show", "episode": "episode", "user": "user", "concert": "concert",
                 "genre": "category", "page": "category", "section": "section",
                 "prerelease": "prerelease", "audiobook": "show", "chapter": "episode"}


def resolve(link):
    """spotify.link / open.spotify.com / spotify: URI -> {type, id, link, uri}."""
    original = link
    expanded = None
    if refs.is_short_link(link):
        expanded = fetch.expand_short_link(link if "://" in link else "https://" + link)
        link = expanded
    kind, rid = refs.kind_and_id(link)
    public = _PUBLIC_TYPES.get(kind or "")
    if not public or not rid:
        raise ValueError("link must be an open.spotify.com link, a spotify.link short link "
                         "or a spotify:<type>:<id> URI")
    uri_kind = {"genre": "page", "audiobook": "show", "chapter": "episode"}.get(kind, kind)
    return {"input": original, "type": public, "id": rid,
            "link": P.entity_link(uri_kind, rid), "uri": f"spotify:{uri_kind}:{rid}",
            "expanded_link": expanded.split("?")[0] if expanded else None}
