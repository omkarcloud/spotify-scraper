"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. The functions live in spotify/ (artists, tracks, albums,
playlists, podcasts, users, browse, charts, concerts, search).
"""
import json
import os

from spotify import artists, charts, tracks

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # an artist id, a spotify:artist: URI or any open.spotify.com artist link
    save("artist_taylor_swift.json", artists.details("06HL4z0CvFAxyc27GXpf02"))

    # a track with its exact play count, credits and 30-second preview
    save("track_blinding_lights.json", tracks.details("0VjIjW4GlUZAMYd2vXMi3b"))

    # a country's weekly Top Songs chart — "GLOBAL" or any country code
    save("chart_top_songs_us.json", charts.country_chart("US", "top-songs"))
