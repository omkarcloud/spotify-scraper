"""The 57 Spotify endpoints. Every path is served with and without the
`/spotify` prefix, so code generated against the hosted API on RapidAPI
(paths like /artists/details) runs unchanged against this server.

Params are validated by the marshmallow schemas in spotify/schemas.py (the
same ones the hosted API uses): ONE param per input — `artist`, `track`,
`album`, `playlist`, … each take an id, a spotify: URI, an open.spotify.com
link or a spotify.link short link. Unknown params are rejected with a 400
so typos surface."""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from schema_fields import load_query
from scraper_errors import BadRequest, NotFound
from spotify import (albums, artists, browse, charts, concerts, playlists, podcasts, resolve,
                     search, tracks, users)
from spotify import schemas as S


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The query as unicode strings (bottle 0.12's .get() hands back latin-1
    decoded bytes, so a UTF-8 "Beyoncé" would arrive as "BeyoncÃ©")."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _page_link(params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "")}
    query["page"] = page
    return f"{request.urlparts.scheme}://{request.urlparts.netloc}{request.path}?{urlencode(query)}"


def paginate(result, params):
    """Lift the scraper's `pagination` block into the flat shape the hosted
    API returns: count / per_page / current_page / total_pages / next /
    previous first, then the data."""
    pagination = result.pop("pagination", None) or {}
    result.pop("count", None)
    page = int(pagination.get("page") or params.get("page") or 1)
    total_pages = int(pagination.get("total_pages") or 0)
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(params, page + 1 if page < total_pages else None),
        "previous": _page_link(params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(label, schema, fn, paginated=False):
    """Validate the query, run the scraper, map errors: bad params -> 400,
    missing entity -> 404, transport/blocks -> 500."""
    params = query_dict()
    data, error = load_query(schema, params)
    if error:
        return json_response(error, 400)
    try:
        result = fn(**data)
    except ValueError as e:                # bad id / params
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:                # upstream rejected the request
        return json_response({"error": f"spotify rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Exception as e:                 # retries exhausted / blocked
        return json_response({"error": f"spotify {label} failed: {e}"}, 500)
    return json_response(paginate(result, params) if paginated else result)


def mount(path, schema, fn, paginated=False):
    """Serve an endpoint at /path and /spotify/path."""
    def handler():
        return call(path.strip("/"), schema, fn, paginated)
    handler.__name__ = "spotify_" + path.strip("/").replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route("/spotify" + path, method="GET")(handler)


P = True   # paginated
ENDPOINTS = [
    ("/artists/details", S.ArtistSchema, artists.details, False),
    ("/search/suggestions", S.SuggestionsSchema, search.suggestions, False),
    ("/search/all", S.SearchAllSchema, search.search_all, False),
    ("/search/tracks", S.SearchSchema, search.search_tracks, P),
    ("/search/artists", S.SearchSchema, search.search_artists, P),
    ("/search/albums", S.SearchSchema, search.search_albums, P),
    ("/search/playlists", S.SearchSchema, search.search_playlists, P),
    ("/search/podcasts", S.SearchSchema, search.search_podcasts, P),
    ("/search/episodes", S.SearchSchema, search.search_episodes, P),
    ("/search/audiobooks", S.SearchSchema, search.search_audiobooks, P),
    ("/search/genres", S.SearchSchema, search.search_genres, P),
    ("/search/users", S.SearchSchema, search.search_users, P),
    ("/artists/stats", S.ArtistSchema, artists.stats, False),
    ("/artists/top-tracks", S.ArtistSchema, artists.top_tracks, False),
    ("/artists/albums", S.ArtistAlbumsSchema, artists.albums, P),
    ("/artists/related", S.ArtistSchema, artists.related, False),
    ("/artists/appears-on", S.ArtistSchema, artists.appears_on, False),
    ("/artists/discovered-on", S.ArtistSchema, artists.discovered_on, False),
    ("/artists/featuring", S.ArtistSchema, artists.featuring, False),
    ("/artists/playlists", S.ArtistSchema, artists.playlists, False),
    ("/artists/concerts", S.ArtistSchema, artists.concerts, False),
    ("/artists/radio", S.ArtistPagedSchema, artists.radio, P),
    ("/artists/batch", S.ArtistBatchSchema, artists.batch, False),
    ("/tracks/details", S.TrackSchema, tracks.details, False),
    ("/tracks/stream-count", S.TrackSchema, tracks.stream_count, False),
    ("/tracks/batch", S.TrackBatchSchema, tracks.batch, False),
    ("/tracks/credits", S.TrackSchema, tracks.credits, False),
    ("/tracks/previews", S.TrackPreviewsSchema, tracks.previews, False),
    ("/tracks/related", S.TrackSchema, tracks.related, False),
    ("/tracks/similar-albums", S.TrackLimitSchema, tracks.similar_albums, False),
    ("/tracks/radio", S.TrackPagedSchema, tracks.radio, P),
    ("/albums/details", S.AlbumSchema, albums.details, False),
    ("/albums/tracks", S.AlbumTracksSchema, albums.tracks, P),
    ("/playlists/details", S.PlaylistDetailsSchema, playlists.details, False),
    ("/playlists/tracks", S.PlaylistTracksSchema, playlists.tracks, P),
    ("/playlists/followers", S.PlaylistSchema, playlists.follower_count, False),
    ("/charts/top-tracks", S.EmptySchema, charts.top_tracks, False),
    ("/charts/top-albums", S.EmptySchema, charts.top_albums, False),
    ("/charts/top-artists", S.EmptySchema, charts.top_artists, False),
    ("/charts/country", S.CountryChartSchema, charts.country_chart, False),
    ("/browse/home", S.HomeSchema, browse.home, False),
    ("/browse/categories", S.EmptySchema, browse.categories, False),
    ("/browse/category", S.CategorySchema, browse.category, False),
    ("/browse/section", S.SectionSchema, browse.section, P),
    ("/browse/country-hub", S.CountryHubSchema, browse.country_hub, False),
    ("/podcasts/details", S.PodcastSchema, podcasts.podcast_details, False),
    ("/podcasts/episodes", S.PodcastEpisodesSchema, podcasts.podcast_episodes, P),
    ("/episodes/details", S.EpisodeSchema, podcasts.episode_details, False),
    ("/audiobooks/details", S.AudiobookSchema, podcasts.audiobook_details, False),
    ("/audiobooks/chapters", S.AudiobookChaptersSchema, podcasts.audiobook_chapters, P),
    ("/chapters/details", S.ChapterSchema, podcasts.chapter_details, False),
    ("/users/details", S.UserSchema, users.details, False),
    ("/users/playlists", S.UserPlaylistsSchema, users.playlists, P),
    ("/concerts/nearby", S.ConcertsNearbySchema, concerts.nearby, False),
    ("/concerts/details", S.ConcertSchema, concerts.details, False),
    ("/concerts/locations", S.ConcertLocationsSchema, concerts.locations, False),
    ("/resolve", S.ResolveSchema, resolve.resolve, False),
]

for _path, _schema, _fn, _paginated in ENDPOINTS:
    mount(_path, _schema, _fn, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [e[0] for e in ENDPOINTS]})
