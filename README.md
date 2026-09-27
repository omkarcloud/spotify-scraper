# 🎧 Spotify Scraper

Spotify Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Spotify data for free.

## ✨ What Can I Get?

- 🎤 **Every artist's real numbers** — monthly listeners, followers, world rank, top listener cities & top tracks with exact play counts
- 🎵 **Full details on 100M+ tracks** — play counts, songwriters & producers, 30-second previews, albums with labels & copyrights
- 📈 **Charts & playlists from 184 markets** — Top Songs & Top 50 per country, global weekly charts, playlists with followers & chart movement
- 🎙️ **7M podcasts & 700K audiobooks** — episodes, ratings, authors, narrators, prices & chapters, plus upcoming concerts with ticket sellers

## 🎥 Example: A Full Spotify Artist

```json
{
  "id": "06HL4z0CvFAxyc27GXpf02",
  "name": "Taylor Swift",
  "link": "https://open.spotify.com/artist/06HL4z0CvFAxyc27GXpf02",
  "is_verified": true,
  "stats": {
    "followers": 164280621,
    "monthly_listeners": 100125350,
    "world_rank": 5,
    "top_cities": [
      { "city": "London", "region": "ENG", "country": "GB", "listeners": 1555584 },
      { "city": "Quezon City", "region": "00", "country": "PH", "listeners": 1462346 }
    ]
  },
  "latest_release": {
    "name": "I Knew It, I Knew You (From \"Toy Story 5\")",
    "album_type": "single",
    "release_date": "2026-06-12",
    "label": "Walt Disney Records / Pixar"
  },
  "top_tracks": [
    { "name": "The Fate of Ophelia", "duration_text": "3:46", "playcount": 1665656522 }
  ],
  "discography_counts": { "albums": 33, "singles": 79, "compilations": 1, "appears_on": 152, "music_videos": 116 },
  "related_artists": [
    { "id": "74KM79TiuVKeVCqs8QtB0B", "name": "Sabrina Carpenter", "link": "https://open.spotify.com/artist/74KM79TiuVKeVCqs8QtB0B" }
  ],
  "external_links": [
    { "name": "instagram", "link": "https://instagram.com/taylorswift" }
  ]
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Spotify Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/spotify-scraper
cd spotify-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/artists/details?artist=06HL4z0CvFAxyc27GXpf02"
```

```json
{
  "id": "06HL4z0CvFAxyc27GXpf02",
  "name": "Taylor Swift",
  "link": "https://open.spotify.com/artist/06HL4z0CvFAxyc27GXpf02",
  "is_verified": true,
  "stats": {
    "followers": 164280621,
    "monthly_listeners": 100125350,
    "world_rank": 5,
    "top_cities": [
      { "city": "London", "region": "ENG", "country": "GB", "listeners": 1555584 }
    ]
  },
  "top_tracks": [
    { "name": "The Fate of Ophelia", "duration_text": "3:46", "playcount": 1665656522 }
  ],
  "discography_counts": { "albums": 33, "singles": 79, "compilations": 1, "appears_on": 158, "music_videos": 116 }
}
```

All 57 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

57 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Artist Details | `/artists/details` | Monthly listeners, followers, world rank, top tracks, bio — one call |
| Search Suggestions | `/search/suggestions` | Autocomplete completions plus suggested artists and tracks |
| Search Everything | `/search/all` | Top results plus every type in one call |
| Search Tracks / Artists / Albums / Playlists / Podcasts / Episodes / Audiobooks / Genres / Users | `/search/tracks`, `/search/artists`, `/search/albums`, `/search/playlists`, `/search/podcasts`, `/search/episodes`, `/search/audiobooks`, `/search/genres`, `/search/users` | Up to 100 results per page, first 1,000 per search |
| Artist Stats | `/artists/stats` | Monthly listeners, followers, world rank, top cities — fast |
| Artist Top Tracks | `/artists/top-tracks` | Top 10 tracks with exact play counts |
| Artist Discography | `/artists/albums` | Albums, singles or compilations, newest or oldest first |
| Related Artists | `/artists/related` | Up to 40 artists fans also like |
| Artist Appears On / Discovered On / Featured In / Playlists | `/artists/appears-on`, `/artists/discovered-on`, `/artists/featuring`, `/artists/playlists` | Albums and playlists that carry the artist |
| Artist Concerts | `/artists/concerts` | Upcoming shows with date, city and line-up |
| Artist Radio / Track Radio | `/artists/radio`, `/tracks/radio` | Spotify's auto-generated radio mix |
| Artists Batch Stats | `/artists/batch` | Stats for up to 20 artists at once |
| Track Details | `/tracks/details` | Play count, credits, preview, album and copyrights |
| Track Stream Count | `/tracks/stream-count` | Exact all-time play count, fast |
| Tracks Batch | `/tracks/batch` | Details and play counts for 20 tracks at once |
| Track Credits | `/tracks/credits` | Songwriters, producers and performers with roles |
| Track Previews | `/tracks/previews` | 30-second MP3 preview links for 50 tracks |
| Related Tracks / Similar Albums | `/tracks/related`, `/tracks/similar-albums` | Recommendations with play counts |
| Album Details / Album Tracks | `/albums/details`, `/albums/tracks` | Label, copyrights, every track's play count |
| Playlist Details / Playlist Tracks | `/playlists/details`, `/playlists/tracks` | Followers, owner, tracks with chart movement |
| Playlist Followers | `/playlists/followers` | Follower count, fast |
| Top Songs / Albums / Artists Global | `/charts/top-tracks`, `/charts/top-albums`, `/charts/top-artists` | Weekly global charts with previous rank |
| Country Charts | `/charts/country` | Any country's Top Songs or Top 50 with plays |
| Home Feed / Browse Categories / Browse Category / Browse Section | `/browse/home`, `/browse/categories`, `/browse/category`, `/browse/section` | Spotify's home and genre pages, shelf by shelf |
| Country Hub | `/browse/country-hub` | A country's charts, popular artists, albums and trending songs |
| Podcast Details / Podcast Episodes / Episode Details | `/podcasts/details`, `/podcasts/episodes`, `/episodes/details` | Ratings, topics, every episode with preview |
| Audiobook Details / Audiobook Chapters / Chapter Details | `/audiobooks/details`, `/audiobooks/chapters`, `/chapters/details` | Authors, narrators, price, rating and chapters |
| User Profile / User Playlists | `/users/details`, `/users/playlists` | Public profile and playlists with followers |
| Concerts Nearby / Concert Details / Concert Locations | `/concerts/nearby`, `/concerts/details`, `/concerts/locations` | Shows near any city, venues and ticket sellers |
| Resolve Link | `/resolve` | Any Spotify link or short link to type and ID |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-spotify-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-spotify-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-spotify-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/artists/details",
    params={"artist": "06HL4z0CvFAxyc27GXpf02"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Spotify Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Spotify%20Scraper%20API.)

[![Ask Us by Email about Spotify Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Spotify%20Scraper%20API&body=I%20need%20help%20using%20the%20Spotify%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**IMDb Scraper**](https://github.com/omkarcloud/imdb-scraper) — movies & TV: ratings, cast, box office & all 6 IMDb charts
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/spotify-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/spotify-scraper)
