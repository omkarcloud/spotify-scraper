"""Spotify search: autocomplete suggestions, one-call search across every
type (top results + each section) and typed, paginated searches.

Pathfinder search quirks (validated 2026-09-19): offset + limit must stay
within the first 1000 results; `limit` up to 100 is honoured; audiobooks
are RestrictedContent outside the US, so audiobook search runs through the
US exit while every other type uses the default egress.
"""
from spotify import ops
from spotify import parsers as P
from spotify.shared import SEARCH_WINDOW, audiobook_country, paged_result, run, window

# public type -> (operation, searchV2 key, item parser)
SEARCH_TYPES = {
    "tracks": ("searchTracks", "tracksV2", P.track),
    "albums": ("searchAlbums", "albumsV2", P.album),
    "artists": ("searchArtists", "artists", P.artist),
    "playlists": ("searchPlaylists", "playlists", P.playlist),
    "podcasts": ("searchPodcasts", "podcasts", P.podcast),
    "episodes": ("searchEpisodes", "episodes", P.episode),
    "audiobooks": ("searchAudiobooks", "audiobooks", P.audiobook),
    "genres": ("searchGenres", "genres", P.genre),
    "users": ("searchUsers", "users", P.user),
}
ALL_SECTIONS = (("tracks", "tracksV2", P.track), ("artists", "artists", P.artist),
                ("albums", "albumsV2", P.album), ("playlists", "playlists", P.playlist),
                ("podcasts", "podcasts", P.podcast), ("episodes", "episodes", P.episode),
                ("audiobooks", "audiobooks", P.audiobook), ("genres", "genres", P.genre),
                ("users", "users", P.user))


def _variables(query, offset, limit, top_results=5):
    return {"searchTerm": query, "offset": offset, "limit": limit,
            **dict(ops.SEARCH_FLAGS, numberOfTopResults=top_results)}


def suggestions(query, limit=10):
    """Autocomplete as typed into the Spotify search box: query completions
    plus the entities (artists, tracks, …) the box suggests."""
    data = run("searchSuggestions", {"query": query, "limit": limit, "numberOfTopResults": limit})
    search = P.dig(data, "searchV2") or {}
    completions, entities = [], []
    for row in P.items_of(P.dig(search, "topResultsV2", "itemsV2")):
        obj = P.unwrap(row)
        if P.typename(obj) == "SearchAutoCompleteEntity" or (isinstance(obj, dict) and "text" in obj):
            text = P.clean(obj.get("text"))
            if text and text not in completions:
                completions.append(text)
            continue
        parsed = P.item(obj)
        if parsed:
            entities.append(parsed)
    return {"query": query, "suggestions": completions[:limit], "results": entities[:limit]}


def search_all(query, limit=10):
    """Every section at once: top results + tracks, artists, albums,
    playlists, podcasts, episodes, audiobooks, genres and users, `limit`
    items each, with each section's total match count."""
    data = run("searchDesktop", _variables(query, 0, limit))
    search = P.dig(data, "searchV2") or {}
    top = [x for x in (P.item(r) for r in P.items_of(P.dig(search, "topResultsV2", "itemsV2"))) if x]
    featured = [x for x in (P.item(r) for r in P.items_of(P.dig(search, "topResultsV2", "featured"))) if x]
    out = {"query": query, "top_results": top or None, "featured": featured or None}
    for name, key, parse in ALL_SECTIONS:
        block = search.get(key) or {}
        results = P.parse_list(block, parse)
        out[name] = {"total_count": P.total_of(block) if results or name != "audiobooks" else 0,
                     "results": results}
    return out


def _typed(kind, query, page, limit):
    operation, key, parse = SEARCH_TYPES[kind]
    offset, limit = window(page, limit, cap=SEARCH_WINDOW)
    country = audiobook_country() if kind == "audiobooks" else None
    data = run(operation, _variables(query, offset, limit), country=country)
    block = P.dig(data, "searchV2", key) or {}
    results = P.parse_list(block, parse)
    total = P.total_of(block)
    has_more = P.dig(block, "pagingInfo", "nextOffset") is not None
    if total is not None:
        total = min(total, SEARCH_WINDOW)
    return paged_result("results", results, page, limit, total, has_more=has_more, query=query)


def _make(kind):
    def impl(query, page=1, limit=20):
        return _typed(kind, query, page, limit)
    impl.__name__ = f"search_{kind}"
    impl.__doc__ = f"One page of {kind} matching `query`."
    return impl


search_tracks = _make("tracks")
search_albums = _make("albums")
search_artists = _make("artists")
search_playlists = _make("playlists")
search_podcasts = _make("podcasts")
search_episodes = _make("episodes")
search_audiobooks = _make("audiobooks")
search_genres = _make("genres")
search_users = _make("users")
