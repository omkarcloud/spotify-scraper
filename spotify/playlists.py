"""Spotify playlists: details (owner, followers, collaborators, chart
metadata) with the first page of items, paginated items, and the radio
playlists Spotify generates for a track or artist.

Chart playlists (Top 50 / Top Songs / Viral) carry per-row attributes the
web player shows as movement arrows: current_pos, previous_pos, status and
`rank` (the play count when the playlist's rank_type is "plays") — kept
as a `chart` block on each item.
"""
from spotify import fetch
from spotify import parsers as P
from spotify.shared import paged_result, ref, require, run

MAX_ITEMS_PER_CALL = 100


def _movement(status):
    return {"UP": "up", "DOWN": "down", "EQUAL": "same", "NEW": "new",
            "RE_ENTRY": "re_entry"}.get(str(status or "").upper(), P.lower(status))


def playlist_item(row, rank_type=None):
    """One content row -> {position fields, added_at, added_by, item}."""
    if not isinstance(row, dict):
        return None
    entity = P.item(row.get("itemV2"))
    if not entity:
        return None
    attrs = P.attributes_map(row.get("attributes"))
    chart = None
    if attrs.get("current_pos") or attrs.get("status"):
        rank_value = P.to_int(attrs.get("rank"))
        chart = {
            "position": P.to_int(attrs.get("current_pos")),
            "previous_position": P.to_int(attrs.get("previous_pos")) or None,
            "movement": _movement(attrs.get("status")),
            "plays": rank_value if rank_type == "plays" else None,
        }
    return {
        "added_at": P.iso_datetime(P.dig(row, "addedAt", "isoString")),
        "added_by": P.owner_ref(P.dig(row, "addedBy")),
        "chart": chart,
        "item": entity,
    }


def _metadata(obj):
    attrs = P.attributes_map(obj.get("attributes"))
    members = []
    for m in P.items_of(obj.get("members")):
        if not isinstance(m, dict):
            continue
        member = P.owner_ref(P.dig(m, "user"))
        if member:
            member.update({"is_owner": bool(m.get("isOwner")),
                           "permission": P.lower(m.get("permissionLevel"))})
            members.append(member)
    chart = None
    if attrs.get("chart_entity_type") or attrs.get("rank_type"):
        chart = {"entity_type": P.clean(attrs.get("chart_entity_type")),
                 "rank_type": P.clean(attrs.get("rank_type")),
                 "new_entries": P.to_int(attrs.get("new_entries_count"))}
    content = obj.get("content") or {}
    uri = obj.get("uri")
    return {
        "id": P.id_of(uri),
        "name": P.clean(obj.get("name")),
        "link": P.link_of(uri),
        "description": P.strip_html(obj.get("description")),
        "format": P.clean(obj.get("format")),
        "followers": P.to_int(obj.get("followers")),
        "total_items": P.total_of(content),
        "owner": P.owner_ref(P.dig(obj, "ownerV2")),
        "members": members or None,
        "chart": chart,
        "updated_at": P.iso_datetime(attrs.get("last_updated")),
        "images": P.image_sources(obj, "images"),
    }, (chart or {}).get("rank_type")


def _fetch(pid, offset, limit):
    data = run("fetchPlaylist", {"uri": f"spotify:playlist:{pid}", "offset": offset, "limit": limit,
                                 "enableWatchFeedEntrypoint": False,
                                 "includeEpisodeContentRatingsV2": False})
    return require(P.dig(data, "playlistV2"), "playlist", pid)


def _items(obj, rank_type, start):
    rows = P.items_of(P.dig(obj, "content"))
    out = []
    for i, row in enumerate(rows):
        parsed = playlist_item(row, rank_type)
        if parsed:
            out.append({"position": start + i + 1, **parsed})
    return out


def details(playlist, limit=100):
    """Playlist metadata (owner, followers, collaborators, chart info,
    last update) plus its first `limit` items."""
    pid, _ = ref("playlist", playlist)
    obj = _fetch(pid, 0, limit)
    meta, rank_type = _metadata(obj)
    meta["items"] = _items(obj, rank_type, 0)
    return meta


def _page(pid, page, limit):
    offset = P.offset_of(page, limit)
    obj = _fetch(pid, offset, limit)
    meta, rank_type = _metadata(obj)
    items = _items(obj, rank_type, offset)
    return meta, items


def tracks(playlist, page=1, limit=100):
    """One page of a playlist's items (tracks and episodes), each with its
    position, added date / adder and chart movement where present."""
    pid, _ = ref("playlist", playlist)
    meta, items = _page(pid, page, limit)
    head = {k: meta[k] for k in ("id", "name", "link", "followers", "total_items")}
    return paged_result("results", items, page, limit, meta.get("total_items"), playlist=head)


def radio_for(seed_uri, page, limit):
    """Spotify's generated "<seed> Radio" playlist for a track/artist URI."""
    body = fetch.spclient(f"/inspiredby-mix/v2/seed_to_playlist/{seed_uri}",
                          {"response-format": "json"})
    items = (body or {}).get("mediaItems") or []
    playlist_uri = next((i.get("uri") for i in items if isinstance(i, dict)
                         and P.kind_of(i.get("uri")) == "playlist"), None)
    if not playlist_uri:
        raise fetch.SpotifyNotFound(f"no radio for {seed_uri}")
    pid = P.id_of(playlist_uri)
    meta, entries = _page(pid, page, limit)
    head = {k: meta[k] for k in ("id", "name", "link", "total_items")}
    return paged_result("results", entries, page, limit, meta.get("total_items"),
                        seed={"type": P.kind_of(seed_uri), "id": P.id_of(seed_uri),
                              "link": P.link_of(seed_uri)},
                        playlist=head)


def follower_count(playlist):
    """Follower count straight from the popcount service (cheap)."""
    pid, _ = ref("playlist", playlist)
    body = fetch.spclient(f"/popcount/v2/playlist/{pid}/count")
    return {"id": pid, "link": P.entity_link("playlist", pid),
            "followers": P.to_int((body or {}).get("count"))}
