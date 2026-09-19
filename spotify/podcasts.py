"""Spotify podcasts, episodes, audiobooks and audiobook chapters.

Podcasts and audiobooks share Spotify's `show` URI space; the same GraphQL
union answers both, told apart by typename. Audiobooks are
RestrictedContent outside the US, so every audiobook / chapter call runs
through config.SPOTIFY_AUDIOBOOK_COUNTRY's exit.
"""
from spotify import fetch
from spotify import parsers as P
from spotify.fetch import SpotifyBadRequest
from spotify.shared import audiobook_country, paged_result, ref, require, run

PREVIEW_EPISODES = 10


def _show(sid, country=None):
    data = run("queryShowMetadataV2", {"uri": f"spotify:show:{sid}"}, country=country)
    return require(P.dig(data, "podcastUnionV2"), "show", sid)


def _topics(obj):
    out = []
    for t in P.items_of(obj.get("topics")):
        if isinstance(t, dict) and t.get("title"):
            out.append({"id": P.id_of(t.get("uri")), "name": P.clean(t.get("title")),
                        "link": P.link_of(t.get("uri"))})
    return out or None


def _episodes_page(sid, offset, limit):
    data = run("queryPodcastEpisodes", {"uri": f"spotify:show:{sid}", "offset": offset, "limit": limit})
    obj = require(P.dig(data, "podcastUnionV2"), "podcast", sid)
    if P.typename(obj) == "Audiobook":
        raise SpotifyBadRequest(f"{sid} is an audiobook; use /spotify/audiobooks/chapters")
    block = P.dig(obj, "episodesV2") or {}
    results = []
    for row in P.items_of(block):
        parsed = P.episode(row)
        if parsed:
            parsed.pop("type", None)
            parsed.pop("podcast", None)
            results.append(parsed)
    return results, P.total_of(block)


def _trailer(obj):
    trailer = P.unwrap(obj.get("trailerV2"))
    if not isinstance(trailer, dict) or not (trailer.get("uri") or trailer.get("_uri")):
        return None
    uri = trailer.get("uri") or trailer.get("_uri")
    return {"id": P.id_of(uri), "name": P.clean(trailer.get("name")), "link": P.link_of(uri),
            **P.duration_fields(trailer.get("duration")), "preview_link": P.preview_link(trailer)}


def podcast_details(podcast):
    """Podcast metadata (publisher, rating, topics, consumption order,
    explicit flag, trailer) + total episode count + the latest episodes."""
    sid, _ = ref("podcast", podcast)
    try:
        obj = _show(sid)
    except fetch.SpotifyNotFound as e:
        if "market" in str(e):   # audiobooks are RestrictedContent outside the US
            raise SpotifyBadRequest(f"{sid} is not a podcast here (audiobooks: use /spotify/audiobooks/details)")
        raise
    if P.typename(obj) == "Audiobook":
        raise SpotifyBadRequest(f"{sid} is an audiobook; use /spotify/audiobooks/details")
    latest, total = _episodes_page(sid, 0, PREVIEW_EPISODES)
    return {
        "id": sid,
        "name": P.clean(obj.get("name")),
        "link": P.entity_link("show", sid),
        "publisher": P.clean(P.dig(obj, "publisher", "name")),
        "description": P.strip_html(obj.get("htmlDescription")) or P.clean(obj.get("description")),
        "media_type": P.lower(obj.get("mediaType")),
        "consumption_order": P.lower(obj.get("consumptionOrderV2")),
        "is_explicit": P.is_explicit(obj),
        "is_playable": P.playable(obj),
        "rating": P.rating(obj.get("rating")),
        "total_episodes": total,
        "topics": _topics(obj),
        "images": P.image_sources(obj, "coverArt"),
        "trailer": _trailer(obj),
        "latest_episodes": latest or None,
    }


def podcast_episodes(podcast, page=1, limit=50):
    """One page of a podcast's episodes, newest first."""
    sid, _ = ref("podcast", podcast)
    results, total = _episodes_page(sid, P.offset_of(page, limit), limit)
    return paged_result("results", results, page, limit, total,
                        podcast={"id": sid, "link": P.entity_link("show", sid)})


def _episode_or_chapter(eid, country=None):
    data = run("getEpisodeOrChapter", {"uri": f"spotify:episode:{eid}",
                                       "includeEpisodeContentRatingsV2": False}, country=country)
    return require(P.dig(data, "episodeUnionV2"), "episode", eid)


def episode_details(episode):
    """One episode: description, release time, duration, explicit /
    paywall flags, media types, transcript flag, 30 s preview, podcast."""
    eid, _ = ref("episode", episode)
    obj = _episode_or_chapter(eid)
    if P.typename(obj) == "Chapter":
        raise SpotifyBadRequest(f"{eid} is an audiobook chapter; use /spotify/chapters/details")
    out = P.episode(obj) or {}
    out.pop("type", None)
    out["has_transcript"] = bool(P.items_of(P.dig(obj, "transcripts")))
    out["playability_reason"] = P.playability_reason(obj)
    return out


def audiobook_details(audiobook):
    """Audiobook metadata: authors, narrators, publisher, publish date,
    duration, rating, price, genres, copyrights, pre-release window,
    trailer, total chapters and the first chapters (US market)."""
    sid, _ = ref("audiobook", audiobook)
    country = audiobook_country()
    obj, (chapters, total) = fetch.run_parallel([
        lambda: _show(sid, country=country),
        lambda: _chapters_page(sid, 0, PREVIEW_EPISODES),
    ])
    if P.typename(obj) != "Audiobook":
        raise SpotifyBadRequest(f"{sid} is a podcast; use /spotify/podcasts/details")
    out = P.audiobook(obj) or {}
    out.pop("type", None)
    genres = [P.clean(g.get("shortName") or g.get("contextualName")) for g in obj.get("genres") or []
              if isinstance(g, dict)]
    out.update({
        "description": P.strip_html(obj.get("htmlDescriptionPlain")) or P.strip_html(obj.get("htmlDescription")),
        "summary": P.clean(obj.get("description")),
        "is_prerelease": obj.get("isPreRelease") if isinstance(obj.get("isPreRelease"), bool) else None,
        "prerelease_ends_at": P.iso_datetime(P.dig(obj, "preReleaseEndDateTime", "isoString"))
        if obj.get("isPreRelease") else None,
        "is_playable": P.playable(obj),
        "rating": P.rating(obj.get("rating")),
        "price": P.price(obj.get("price")),
        "genres": [g for g in genres if g] or None,
        "copyrights": P.copyrights(obj.get("copyrights")),
        "total_chapters": total,
        "trailer": _trailer(obj),
        "first_chapters": chapters or None,
    })
    return P.ordered(out, ("id", "name", "link", "authors", "narrators", "publisher",
                           "publish_date", "duration_ms", "duration_text", "description"))


def _chapters_page(sid, offset, limit):
    data = run("queryBookChapters", {"uri": f"spotify:show:{sid}", "offset": offset, "limit": limit},
               country=audiobook_country())
    obj = require(P.dig(data, "podcastUnionV2"), "audiobook", sid)
    block = P.dig(obj, "chaptersV2") or {}
    results = []
    start = offset
    for row in P.items_of(block):
        parsed = P.episode(row)
        if parsed:
            parsed.pop("type", None)
            parsed.pop("audiobook", None)
            start += 1
            results.append({"number": start, **parsed})
    return results, P.total_of(block)


def audiobook_chapters(audiobook, page=1, limit=50):
    """One page of an audiobook's chapters in reading order."""
    sid, _ = ref("audiobook", audiobook)
    results, total = _chapters_page(sid, P.offset_of(page, limit), limit)
    return paged_result("results", results, page, limit, total,
                        audiobook={"id": sid, "link": P.entity_link("show", sid)})


def chapter_details(chapter):
    """One audiobook chapter (US market)."""
    cid, _ = ref("chapter", chapter)
    obj = _episode_or_chapter(cid, country=audiobook_country())
    out = P.episode(obj) or {}
    out.pop("type", None)
    out["playability_reason"] = P.playability_reason(obj)
    return out
