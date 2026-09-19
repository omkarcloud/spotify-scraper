"""Offline tests for the Spotify refs, marshmallow schemas, parsers and the
endpoint functions with the transport monkeypatched to serve fixtures
(raw pathfinder / charts payloads captured 2026-09-19) — no network.

    python -m pytest spotify/test_endpoints.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from schema_fields import load_query  # noqa: E402
from spotify import (albums, artists, charts, concerts, fetch, parsers as P, playlists,  # noqa: E402
                     podcasts, refs, schemas, search, tracks)

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f)


# ---- refs / schemas ------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "11dFghVXANMlKmJXsNCbNl",
    "spotify:track:11dFghVXANMlKmJXsNCbNl",
    "https://open.spotify.com/track/11dFghVXANMlKmJXsNCbNl?si=abc123",
    "https://open.spotify.com/intl-de/track/11dFghVXANMlKmJXsNCbNl",
    "open.spotify.com/embed/track/11dFghVXANMlKmJXsNCbNl",
])
def test_track_ref_forms(value):
    assert refs.resolve("track", value) == "11dFghVXANMlKmJXsNCbNl"


def test_ref_rejects_other_kinds_and_garbage():
    with pytest.raises(ValueError):
        refs.resolve("track", "https://open.spotify.com/album/4aawyAB9vmqN3uQ7FjRGTy")
    with pytest.raises(ValueError):
        refs.resolve("artist", "not an id")
    with pytest.raises(ValueError):
        refs.resolve("album", "https://www.deezer.com/album/302127")


def test_special_refs():
    assert refs.resolve("playlist", "spotify:user:spotifycharts:playlist:37i9dQZEVXbLp5XoPON0wI") \
        == "37i9dQZEVXbLp5XoPON0wI"
    assert refs.resolve("user", "https://open.spotify.com/user/nocopyrightsounds") == "nocopyrightsounds"
    assert refs.resolve("category", "https://open.spotify.com/genre/0JQ5DAqbMKFEC4WFtoNRpw") \
        == "0JQ5DAqbMKFEC4WFtoNRpw"
    assert refs.resolve("audiobook", "spotify:show:40ygvasZaqVMMBkgYoUy8C") == "40ygvasZaqVMMBkgYoUy8C"
    assert refs.resolve("track", "https://spotify.link/zSAbm2zQbDb") == "https://spotify.link/zSAbm2zQbDb"


def test_schemas():
    data, err = load_query(schemas.ArtistAlbumsSchema, {
        "artist": "spotify:artist:06HL4z0CvFAxyc27GXpf02", "type": "Singles", "sort": "oldest"})
    assert err is None and data == {"artist": "06HL4z0CvFAxyc27GXpf02", "type": "singles",
                                    "sort": "oldest", "page": 1, "limit": 50}
    data, err = load_query(schemas.TrackBatchSchema, {
        "tracks": "11dFghVXANMlKmJXsNCbNl, spotify:track:4uLU6hMCjMI75M1A2tKUQC,11dFghVXANMlKmJXsNCbNl"})
    assert err is None and data["tracks"] == ["11dFghVXANMlKmJXsNCbNl", "4uLU6hMCjMI75M1A2tKUQC"]
    _, err = load_query(schemas.TrackSchema, {"track": "11dFghVXANMlKmJXsNCbNl", "bogus": "1"})
    assert err and "bogus" in err["errors"]
    _, err = load_query(schemas.SearchSchema, {"query": "x", "limit": "500"})
    assert err and "limit" in err["errors"]
    data, _ = load_query(schemas.CountryChartSchema, {"country": "gb"})
    assert data == {"country": "GB", "chart": "top-songs"}
    data, _ = load_query(schemas.CountryChartSchema, {})
    assert data["country"] == "GLOBAL"
    _, err = load_query(schemas.HomeSchema, {"timezone": "Mars/Base"})
    assert err and "timezone" in err["errors"]


def test_search_window():
    with pytest.raises(ValueError):
        search._typed("tracks", "love", page=11, limit=100)


# ---- parser helpers --------------------------------------------------------------------

def test_release_date_precision():
    assert P.release_date({"isoString": "2017-05-26T00:00:00Z", "precision": "DAY", "year": 2017}) \
        == ("2017-05-26", "day")
    assert P.release_date({"year": 2010, "precision": "YEAR"}) == ("2010", "year")
    assert P.release_date({"day": 7, "month": 11, "year": 2025, "precision": "DAY"}) == ("2025-11-07", "day")
    assert P.release_date(None) == (None, None)


def test_images_infer_size_from_id():
    out = P.images([{"url": "https://i.scdn.co/image/ab67616d00001e02d7812467811a7da6e6a44902"},
                    {"url": "https://i.scdn.co/image/ab67616d0000b273d7812467811a7da6e6a44902"}])
    assert [i["width"] for i in out] == [640, 300]


def test_datetime_helpers():
    assert P.iso_datetime("2026-12-05T15:00+05:30") == "2026-12-05T09:30:00Z"
    assert P.local_datetime("2026-12-05T15:00+05:30") == "2026-12-05T15:00:00+05:30"
    assert P.duration_text(8899753) == "2:28:19"


def test_unwrap_and_missing():
    assert P.unwrap({"__typename": "TrackResponseWrapper", "data": {"__typename": "Track", "uri": "x"}}) \
        == {"__typename": "Track", "uri": "x"}
    assert P.item({"__typename": "AudiobookResponseWrapper", "data": {"__typename": "RestrictedContent"}}) is None
    assert P.track({"__typename": "NotFound"}) is None


# ---- endpoints over fixtures -------------------------------------------------------------

@pytest.fixture
def offline(monkeypatch):
    payloads = {
        "getTrack": fixture("pf_get_track.json")["data"],
        "getAlbum": fixture("pf_get_album.json")["data"],
        "queryArtistOverview": fixture("pf_artist_overview.json")["data"],
        "fetchPlaylist": fixture("pf_fetch_playlist.json")["data"],
        "searchDesktop": fixture("pf_search_desktop.json")["data"],
        "concert": fixture("pf_concert.json")["data"],
        "queryShowMetadataV2": fixture("pf_audiobook_show.json")["data"],
        "queryPodcastEpisodes": fixture("pf_podcast_episodes.json")["data"],
        "queryTrackCreditsGroupedModal": {"trackUnion": {"name": "x", "creditsTrait": {
            "contributors": {"items": [{"name": "A", "role": "Writer", "roleGroup": {"name": "Writers"},
                                        "uri": "spotify:artist:2wCBGp0AIrgr5VBnF2qGM0"}]},
            "sources": {"items": [{"name": "VDE-GALLO"}]}}}},
        "trackPreview": {"lookup": [{"__typename": "TrackResponseWrapper", "data": {
            "previews": {"audioPreviewsV2": {"items": [{"url": "https://p.scdn.co/mp3-preview/abc"}]}},
            "uri": "spotify:track:4iV5W9uYEdYUVa79Axb7Rh"}}]},
        "queryBookChapters": {"podcastUnionV2": {"__typename": "Audiobook", "chaptersV2": {
            "items": [], "totalCount": 29}}},
    }
    calls = []

    def fake_pathfinder(operation, variables, country=None):
        calls.append((operation, country))
        return payloads[operation]

    monkeypatch.setattr(fetch, "pathfinder", fake_pathfinder)
    monkeypatch.setattr(fetch, "charts_overview", lambda: fixture("charts_public.json"))
    monkeypatch.setattr(fetch, "embed_entity", lambda kind, rid: {})
    return calls


def test_track_details(offline):
    out = tracks.details("4iV5W9uYEdYUVa79Axb7Rh")
    assert out["id"] == "4iV5W9uYEdYUVa79Axb7Rh" and out["playcount"] == 183362
    assert out["preview_link"] == "https://p.scdn.co/mp3-preview/abc"
    assert out["album"]["release_date"] == "2010" and out["album"]["copyrights"]
    assert [a["name"] for a in out["artists"]] == ["Eduard Abramyan", "Sona Shaboyan"]
    assert out["credits"]["sources"] == ["VDE-GALLO"]
    assert "uri" not in out and "type" not in out


def test_album_details(offline):
    out = albums.details("4aawyAB9vmqN3uQ7FjRGTy")
    assert out["label"].startswith("Mr.305") and out["total_tracks"] == 18
    assert len(out["tracks"]) == 18 and out["tracks"][0]["playcount"] == 10788269
    assert out["copyrights"][0]["type"] == "phonogram"


def test_artist_details(offline):
    out = artists.details("06HL4z0CvFAxyc27GXpf02")
    assert out["stats"]["monthly_listeners"] == 100125350 and out["stats"]["world_rank"] == 5
    assert out["stats"]["top_cities"][0]["city"] == "London"
    assert out["top_tracks"][0]["playcount"] > 1_000_000_000
    assert out["discography_counts"]["singles"] == 79
    assert out["external_links"][0]["name"] == "facebook"


def test_playlist_chart_rows(offline):
    out = playlists.details("37i9dQZEVXbMDoHDwVN2tF")
    assert out["followers"] == 16970461 and out["chart"]["rank_type"] == "plays"
    row = out["items"][0]
    assert row["position"] == 1 and row["chart"]["movement"] == "same" and row["chart"]["plays"] == 6159133
    assert row["item"]["type"] == "track" and row["item"]["playcount"] == 161118537


def test_search_all_drops_restricted(offline):
    out = search.search_all("radiohead")
    assert out["top_results"][0]["type"] == "artist"
    assert out["audiobooks"] == {"total_count": 0, "results": []}
    assert out["tracks"]["results"][0]["name"] == "Let Down"


def test_concert_details(offline):
    out = concerts.details("2OvGgoad28kYNzpw6hutns")
    assert out["venue"]["country"] == "IN" and out["venue"]["latitude"] == pytest.approx(28.472755)
    assert out["tickets"][0]["seller"] == "BookMyShow"
    assert out["starts_at"] == "2026-12-05T15:00:00+05:30"


def test_global_charts(offline):
    out = charts.top_tracks()
    assert out["chart"]["period"] == "weekly" and len(out["results"]) == 50
    assert out["results"][0]["rank"] == 1 and out["results"][0]["track"]["name"]
    assert charts.top_artists()["results"][0]["artist"]["name"]


def test_audiobook_runs_through_us_exit(offline):
    out = podcasts.audiobook_details("40ygvasZaqVMMBkgYoUy8C")
    assert out["price"] == {"amount": 18.49, "list_amount": 20.0, "currency": "USD"}
    assert out["authors"] == ["James Clear"] and out["total_chapters"] == 29
    want = config.SPOTIFY_AUDIOBOOK_COUNTRY          # "us" in the hosted API
    assert all(country == want for op, country in offline if op in ("queryShowMetadataV2", "queryBookChapters"))


def test_podcast_rejects_audiobook(offline):
    with pytest.raises(fetch.SpotifyBadRequest):
        podcasts.podcast_details("40ygvasZaqVMMBkgYoUy8C")


def test_embed_session_parse():
    html = ('<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"state":'
            '{"settings":{"session":{"accessToken":"BQabc","accessTokenExpirationTimestampMs":'
            '1789806420231,"isAnonymous":true}}}}}}</script>')
    token, exp = fetch.embed_session(html)
    assert token == "BQabc" and exp == pytest.approx(1789806420.231)
    assert fetch.embed_session("<html></html>") == (None, None)

# ---- proven example values (live 200 with data on 2026-09-19) -----------------------------
# One call per route: the public docs / playground use these values, so each must
# still pass its route's schema. (Read by the publishing tools' derive_facts.py.)

def _example(path, schema, **params):
    data, err = load_query(schema, params)
    assert err is None, (path, err)
    return data


def test_route_examples_validate():
    _example("/spotify/tracks/details", schemas.TrackSchema, track='0VjIjW4GlUZAMYd2vXMi3b')
    _example("/spotify/search/suggestions", schemas.SuggestionsSchema, query='taylor sw')
    _example("/spotify/search/all", schemas.SearchAllSchema, query='taylor swift')
    _example("/spotify/search/tracks", schemas.SearchSchema, query='blinding lights')
    _example("/spotify/search/albums", schemas.SearchSchema, query='1989')
    _example("/spotify/search/artists", schemas.SearchSchema, query='taylor swift')
    _example("/spotify/search/playlists", schemas.SearchSchema, query='workout')
    _example("/spotify/search/podcasts", schemas.SearchSchema, query='joe rogan')
    _example("/spotify/search/episodes", schemas.SearchSchema, query='elon musk')
    _example("/spotify/search/audiobooks", schemas.SearchSchema, query='atomic habits')
    _example("/spotify/search/genres", schemas.SearchSchema, query='hip hop')
    _example("/spotify/search/users", schemas.SearchSchema, query='spotify')
    _example("/spotify/tracks/stream-count", schemas.TrackSchema, track='0VjIjW4GlUZAMYd2vXMi3b')
    _example("/spotify/tracks/batch", schemas.TrackBatchSchema, tracks='0VjIjW4GlUZAMYd2vXMi3b,7qiZfU4dY1lWllzX7mPBI3')
    _example("/spotify/tracks/credits", schemas.TrackSchema, track='0VjIjW4GlUZAMYd2vXMi3b')
    _example("/spotify/tracks/previews", schemas.TrackPreviewsSchema, tracks='0VjIjW4GlUZAMYd2vXMi3b,7qiZfU4dY1lWllzX7mPBI3')
    _example("/spotify/tracks/related", schemas.TrackSchema, track='0VjIjW4GlUZAMYd2vXMi3b')
    _example("/spotify/tracks/similar-albums", schemas.TrackLimitSchema, track='0VjIjW4GlUZAMYd2vXMi3b')
    _example("/spotify/tracks/radio", schemas.TrackPagedSchema, track='0VjIjW4GlUZAMYd2vXMi3b')
    _example("/spotify/albums/details", schemas.AlbumSchema, album='4a6NzYL1YHRUgx9e3YZI6I')
    _example("/spotify/albums/tracks", schemas.AlbumTracksSchema, album='4a6NzYL1YHRUgx9e3YZI6I')
    _example("/spotify/artists/details", schemas.ArtistSchema, artist='06HL4z0CvFAxyc27GXpf02')
    _example("/spotify/artists/stats", schemas.ArtistSchema, artist='06HL4z0CvFAxyc27GXpf02')
    _example("/spotify/artists/batch", schemas.ArtistBatchSchema, artists='06HL4z0CvFAxyc27GXpf02,3TVXtAsR1Inumwj472S9r4')
    _example("/spotify/artists/top-tracks", schemas.ArtistSchema, artist='06HL4z0CvFAxyc27GXpf02')
    _example("/spotify/artists/albums", schemas.ArtistAlbumsSchema, artist='06HL4z0CvFAxyc27GXpf02')
    _example("/spotify/artists/related", schemas.ArtistSchema, artist='06HL4z0CvFAxyc27GXpf02')
    _example("/spotify/artists/appears-on", schemas.ArtistSchema, artist='06HL4z0CvFAxyc27GXpf02')
    _example("/spotify/artists/discovered-on", schemas.ArtistSchema, artist='06HL4z0CvFAxyc27GXpf02')
    _example("/spotify/artists/featuring", schemas.ArtistSchema, artist='06HL4z0CvFAxyc27GXpf02')
    _example("/spotify/artists/playlists", schemas.ArtistSchema, artist='06HL4z0CvFAxyc27GXpf02')
    _example("/spotify/artists/concerts", schemas.ArtistSchema, artist='6KImCVD70vtIoJWnq6nGn3')
    _example("/spotify/artists/radio", schemas.ArtistPagedSchema, artist='06HL4z0CvFAxyc27GXpf02')
    _example("/spotify/playlists/details", schemas.PlaylistDetailsSchema, playlist='37i9dQZF1DXcBWIGoYBM5M')
    _example("/spotify/playlists/tracks", schemas.PlaylistTracksSchema, playlist='37i9dQZF1DXcBWIGoYBM5M')
    _example("/spotify/playlists/followers", schemas.PlaylistSchema, playlist='37i9dQZF1DXcBWIGoYBM5M')
    _example("/spotify/podcasts/details", schemas.PodcastSchema, podcast='4rOoJ6Egrf8K2IrywzwOMk')
    _example("/spotify/podcasts/episodes", schemas.PodcastEpisodesSchema, podcast='4rOoJ6Egrf8K2IrywzwOMk')
    _example("/spotify/episodes/details", schemas.EpisodeSchema, episode='7rACFBcIIDWROlUB0MoGkW')
    _example("/spotify/audiobooks/details", schemas.AudiobookSchema, audiobook='40ygvasZaqVMMBkgYoUy8C')
    _example("/spotify/audiobooks/chapters", schemas.AudiobookChaptersSchema, audiobook='40ygvasZaqVMMBkgYoUy8C')
    _example("/spotify/chapters/details", schemas.ChapterSchema, chapter='4vxkqkMeYRgpMzQa7yyKN0')
    _example("/spotify/users/details", schemas.UserSchema, user='spotify')
    _example("/spotify/users/playlists", schemas.UserPlaylistsSchema, user='spotify')
    _example("/spotify/browse/category", schemas.CategorySchema, category='0JQ5DAqbMKFEC4WFtoNRpw')
    _example("/spotify/browse/section", schemas.SectionSchema, section='0JQ5IMCbQBLoSVpnseIhn6')
    _example("/spotify/browse/country-hub", schemas.CountryHubSchema, country='US')
    _example("/spotify/charts/country", schemas.CountryChartSchema, country='US')
    _example("/spotify/concerts/details", schemas.ConcertSchema, concert='662FQPoFwqt6JVawvWS1FU')
    _example("/spotify/concerts/nearby", schemas.ConcertsNearbySchema, location='Los Angeles')
    _example("/spotify/concerts/locations", schemas.ConcertLocationsSchema, query='los angeles')
    _example("/spotify/resolve", schemas.ResolveSchema, link='https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b')
