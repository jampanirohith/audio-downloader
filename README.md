# YouTube Music Playlist Downloader & Enricher — Phase 1

This is the current implementation contract. It downloads usable YouTube Music playlist occurrences, enriches them with optional Spotify catalog metadata, finds synchronized LRCLIB lyrics, selects a YouTube music video, creates a portable MP3, and writes a same-basename JSON sidecar containing the detailed record.

## Active rules

- No duplicate detection or duplicate resolution exists. Every playlist occurrence is processed independently and keeps its permanent serial.
- ISRC is not a matching key. Spotify ISRC, when available, is ordinary metadata only.
- Spotify enrichment is optional. It uses the Spotify Web API search with `title + album` and selects the first returned track whose duration is within the configured tolerance.
- When Spotify is selected, the largest album-art image returned by Spotify is downloaded at its original resolution and preserved byte-for-byte. The project does not crop, resize, recompress, or otherwise alter Spotify artwork.
- LRCLIB uses **only `GET /api/get`**. The project never calls `/api/search`. The lookup uses track title, artist, album, and duration and accepts only a record that contains valid synchronized lyrics.
- Only synchronized lyrics are saved as `.lrc`. Plain-only lyrics are ignored.
- Synced songs are stored under `songs/synced_lyrics/`; songs without synced lyrics are stored under `songs/no_synced_lyrics/`.
- Synchronized lyrics are embedded in the MP3 using ID3 `SYLT` plus a compatibility `USLT` projection.
- Each MP3 has a same-basename `.json` sidecar beside it containing the detailed normalized record, all source/API metadata, search results used for selection, artwork provenance, lyric response, and file integrity information.
- The MP3 itself contains only concise player-facing metadata and important IDs/URLs: title, artist, album, release date, track/disc, genre when known, composer/publisher/copyright when known, YTMusic source ID, selected YouTube video ID/title, Spotify track/album ID and ISRC when available, artwork, and embedded synchronized lyrics.
- Verbose source descriptions, age-limit fields, channel details, raw API objects, extractor internals, and other detailed data belong in the sidecar JSON, not the MP3.

## Spotify

Configure `spotify.enabled=true`, `client_id`, and `client_secret`, or set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` when `use_env=true`. Spotify documents that album cover art is returned in multiple sizes; this project selects the largest returned image and preserves it without transformation. Spotify also documents that visual content must be kept in its original form and that metadata/cover art should link back to Spotify.

Spotify ISRC is written to `TSRC` when returned, but it is never used for duplicate matching.

## LRCLIB

The client uses only:

```text
GET https://lrclib.net/api/get
```

No search endpoint is used. LRCLIB documents `/api/get` as the metadata lookup route and its current implementation uses title/artist/album plus duration-aware matching; the current API may expose `lyricsId` and `syncedLyrics`.

## Embedded lyrics

The `.lrc` file is the canonical external synced-lyrics artifact. The same timing/text is embedded in the MP3 as ID3 `SYLT`, with `USLT` carrying the plain-text projection for players that do not expose timed lyrics. Mutagen documents both frame types and SYLT millisecond timestamps.

## Sidecar JSON

For every finalized MP3, a same-basename JSON file is written: 

```text
songs/synced_lyrics/001_Title_Artist.mp3
songs/synced_lyrics/001_Title_Artist.lrc
songs/synced_lyrics/001_Title_Artist.json

or

songs/no_synced_lyrics/002_Title_Artist.mp3
songs/no_synced_lyrics/002_Title_Artist.json
```

The JSON is the detailed/provenance record. It includes the complete raw yt-dlp source object, YTMusic playlist item, selected YouTube metadata, Spotify track/album data, LRCLIB response, normalized metadata, artwork source and dimensions/hash, lyrics text/hash, final file size/hash, and all paths.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Install FFmpeg/FFprobe and a supported JavaScript runtime for current yt-dlp YouTube extraction paths. Then run:

```powershell
python main.py --doctor
python main.py
```

Useful commands:

```powershell
python main.py --status
python main.py --check-invariants
python main.py --ingest-only
python main.py --no-ingest
python main.py --retry-errors
python main.py --limit 10
python scripts/inspect_mp3.py "songs\synced_lyrics\001_song_artist.mp3"
```

## Testing

```powershell
pytest -q
```
