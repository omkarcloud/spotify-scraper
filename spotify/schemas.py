"""Marshmallow request schemas for every /spotify/* route.

Generic fields live in the shared top-level schema_fields.py; this module
adds the Spotify resolvers and the per-route schemas. Every schema's load()
output is the kwargs dict its endpoint function takes.

ONE param per input (tripadvisor QueryOrLinkField convention, never a
sibling `url`/`id` pair): `track`, `album`, `artist`, `playlist`,
`podcast`, `episode`, `audiobook`, `chapter`, `concert`, `user`,
`category`, `section` each take a bare id, a spotify:<type>:<id> URI, an
open.spotify.com link (any intl-xx prefix, embed links, ?si= share params)
or a spotify.link short link (refs.py). List params (`tracks`, `artists`)
take comma-separated ids / URIs / links.
"""
from zoneinfo import ZoneInfo

from marshmallow import ValidationError, fields

from schema_fields import (COUNTRY_CODES, BaseSchema, ChoiceField, PageField, PageSizeField,
                           QueryField, RefField, StrippedString)
from spotify import refs
from spotify.artists import DISCOGRAPHY_OPS, SORTS
from spotify.charts import COUNTRY_CHARTS


class TrackRefField(RefField):
    resolver = staticmethod(lambda value: refs.resolve("track", value))


class AlbumRefField(RefField):
    resolver = staticmethod(lambda value: refs.resolve("album", value))


class ArtistRefField(RefField):
    resolver = staticmethod(lambda value: refs.resolve("artist", value))


class PlaylistRefField(RefField):
    resolver = staticmethod(lambda value: refs.resolve("playlist", value))


class PodcastRefField(RefField):
    resolver = staticmethod(lambda value: refs.resolve("podcast", value))


class EpisodeRefField(RefField):
    resolver = staticmethod(lambda value: refs.resolve("episode", value))


class AudiobookRefField(RefField):
    resolver = staticmethod(lambda value: refs.resolve("audiobook", value))


class ChapterRefField(RefField):
    resolver = staticmethod(lambda value: refs.resolve("chapter", value))


class ConcertRefField(RefField):
    resolver = staticmethod(lambda value: refs.resolve("concert", value))


class UserRefField(RefField):
    resolver = staticmethod(lambda value: refs.resolve("user", value))


class CategoryRefField(RefField):
    resolver = staticmethod(lambda value: refs.resolve("category", value))


class SectionRefField(RefField):
    resolver = staticmethod(lambda value: refs.resolve("section", value))


class RefListField(fields.Field):
    """Comma-separated ids / URIs / links -> list of unique ids."""

    def __init__(self, kind, max_items, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)
        self.kind = kind
        self.max_items = max_items

    def _deserialize(self, value, attr, data, **kwargs):
        values = [v.strip() for v in str(value).split(",") if v.strip()]
        try:
            return refs.resolve_list(self.kind, values, self.max_items)
        except ValueError as e:
            raise ValidationError(str(e))


class ChartCountryField(StrippedString):
    """'global' or an ISO country code -> 'GLOBAL' / upper-cased code."""

    def __init__(self, **kwargs):
        kwargs.setdefault("load_default", "GLOBAL")
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None or value.lower() == "global":
            return "GLOBAL"
        if value.upper() not in COUNTRY_CODES:
            raise ValidationError("Must be global or a 2-letter ISO country code (US, GB, IN, ...).")
        return value.upper()


class HubCountryField(StrippedString):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value.upper() not in COUNTRY_CODES:
            raise ValidationError("Must be a 2-letter ISO country code (US, GB, IN, ...).")
        return value.upper()


class TimezoneField(StrippedString):
    """IANA time zone name (America/New_York); default UTC."""

    def __init__(self, **kwargs):
        kwargs.setdefault("load_default", "UTC")
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return "UTC"
        try:
            ZoneInfo(value)
        except Exception:
            raise ValidationError("Must be an IANA time zone such as America/New_York or Europe/London.")
        return value


class LinkField(StrippedString):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)


def _page():
    return PageField(max_page=1000)


# ---- search -------------------------------------------------------------------------

class SuggestionsSchema(BaseSchema):
    query = QueryField(max_length=100)
    limit = PageSizeField(default=10, max_size=20)


class SearchAllSchema(BaseSchema):
    query = QueryField()
    limit = PageSizeField(default=10, max_size=50)


class SearchSchema(BaseSchema):
    query = QueryField()
    page = _page()
    limit = PageSizeField(default=20, max_size=100)


# ---- tracks ---------------------------------------------------------------------------

class TrackSchema(BaseSchema):
    track = TrackRefField()


class TrackLimitSchema(TrackSchema):
    limit = PageSizeField(default=20, max_size=50)


class TrackPagedSchema(TrackSchema):
    page = _page()
    limit = PageSizeField(default=50, max_size=100)


class TrackBatchSchema(BaseSchema):
    tracks = RefListField("track", max_items=20)


class TrackPreviewsSchema(BaseSchema):
    tracks = RefListField("track", max_items=50)


# ---- albums ---------------------------------------------------------------------------

class AlbumSchema(BaseSchema):
    album = AlbumRefField()


class AlbumTracksSchema(AlbumSchema):
    page = _page()
    limit = PageSizeField(default=50, max_size=100)


# ---- artists --------------------------------------------------------------------------

class ArtistSchema(BaseSchema):
    artist = ArtistRefField()


class ArtistAlbumsSchema(ArtistSchema):
    type = ChoiceField(list(DISCOGRAPHY_OPS), load_default="all")
    sort = ChoiceField(list(SORTS), load_default="newest")
    page = _page()
    limit = PageSizeField(default=50, max_size=100)


class ArtistPagedSchema(ArtistSchema):
    page = _page()
    limit = PageSizeField(default=50, max_size=100)


class ArtistBatchSchema(BaseSchema):
    artists = RefListField("artist", max_items=20)


# ---- playlists ------------------------------------------------------------------------

class PlaylistSchema(BaseSchema):
    playlist = PlaylistRefField()


class PlaylistDetailsSchema(PlaylistSchema):
    limit = PageSizeField(default=100, max_size=100)


class PlaylistTracksSchema(PlaylistSchema):
    page = _page()
    limit = PageSizeField(default=100, max_size=100)


# ---- podcasts / episodes / audiobooks ------------------------------------------------------

class PodcastSchema(BaseSchema):
    podcast = PodcastRefField()


class PodcastEpisodesSchema(PodcastSchema):
    page = _page()
    limit = PageSizeField(default=50, max_size=100)


class EpisodeSchema(BaseSchema):
    episode = EpisodeRefField()


class AudiobookSchema(BaseSchema):
    audiobook = AudiobookRefField()


class AudiobookChaptersSchema(AudiobookSchema):
    page = _page()
    limit = PageSizeField(default=50, max_size=50)


class ChapterSchema(BaseSchema):
    chapter = ChapterRefField()


# ---- users ----------------------------------------------------------------------------

class UserSchema(BaseSchema):
    user = UserRefField()


class UserPlaylistsSchema(UserSchema):
    page = _page()
    limit = PageSizeField(default=50, max_size=50)


# ---- browse / charts --------------------------------------------------------------------

class EmptySchema(BaseSchema):
    pass


class CategorySchema(BaseSchema):
    category = CategoryRefField()
    section_limit = PageSizeField(default=20, max_size=50)


class SectionSchema(BaseSchema):
    section = SectionRefField()
    page = _page()
    limit = PageSizeField(default=50, max_size=50)


class HomeSchema(BaseSchema):
    section_limit = PageSizeField(default=20, max_size=50)
    timezone = TimezoneField()


class CountryHubSchema(BaseSchema):
    country = HubCountryField()


class CountryChartSchema(BaseSchema):
    country = ChartCountryField()
    chart = ChoiceField(list(COUNTRY_CHARTS), load_default="top-songs")


# ---- concerts / misc ---------------------------------------------------------------------

class ConcertSchema(BaseSchema):
    concert = ConcertRefField()


class ConcertsNearbySchema(BaseSchema):
    location = QueryField(max_length=100)


class ConcertLocationsSchema(BaseSchema):
    query = QueryField(max_length=100)


class ResolveSchema(BaseSchema):
    link = LinkField()
