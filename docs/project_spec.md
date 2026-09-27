# Current Project Specification

> This file is the active specification for the implementation in this repository. The original planning document is preserved as `HISTORICAL_PHASE1_SPEC.md`.

## 1. Pipeline

YouTube Music playlist ingestion -> permanent serial assignment -> one yt-dlp acquisition -> metadata normalization -> optional Spotify enrichment -> selected YouTube music-video lookup -> LRCLIB `/api/get` synced-lyrics lookup -> concise MP3 metadata + artwork + embedded lyrics -> same-basename JSON sidecar -> validation -> SHA-256 -> atomic finalization -> songs.db.

## 2. Identity

A playlist occurrence is identified by its permanent serial number. There is no duplicate detection or duplicate resolution. Repeated occurrences are independent records. Spotify ISRC is stored only as ordinary metadata when available.

## 3. Spotify enrichment

When `spotify.enabled=true`, search with `{title} {album}`. Iterate returned Spotify tracks in their returned order and select the first track whose `duration_ms` is within `duration_tolerance_seconds` of the actual downloaded YTMusic audio duration. Fetch the full Spotify album record and select the largest album image. Preserve the selected image bytes exactly. Use its metadata to improve the song metadata and write Spotify IDs/ISRC to the MP3 when available.

## 4. LRCLIB

Only `GET https://lrclib.net/api/get` is permitted. The request uses `track_name`, `artist_name`, `album_name`, and `duration`. No `/api/search` fallback exists. Accept only a response containing timestamped `syncedLyrics`; plain-only lyrics are not downloaded or saved.

## 5. Output layout

With synced lyrics:

```text
songs/synced_lyrics/<serial>_<title>_<artist>.mp3
songs/synced_lyrics/<serial>_<title>_<artist>.lrc
songs/synced_lyrics/<serial>_<title>_<artist>.json
```

Without synced lyrics:

```text
songs/no_synced_lyrics/<serial>_<title>_<artist>.mp3
songs/no_synced_lyrics/<serial>_<title>_<artist>.json
```

## 6. MP3 metadata contract

The MP3 contains only concise player-facing metadata:

- standard music ID3: title, artists, album, album artist, release date, track/disc, genre, composer, publisher/label, copyright, language, BPM, compilation, encoder, duration;
- YTMusic source video ID and URL;
- selected YouTube video ID, URL and title;
- Spotify track ID, album ID, URLs and ISRC when available;
- front-cover artwork;
- synchronized lyrics in SYLT plus USLT.

Do not embed source descriptions, age limits, channel/uploader details, extractor internals, raw API JSON, or other verbose provenance.

## 7. Sidecar JSON

The same-basename JSON file is the detailed record. It contains normalized metadata plus the complete raw source/API objects used by the pipeline: YTMusic playlist item, yt-dlp info, selected YouTube metadata, Spotify track/album metadata, LRCLIB response and lyrics, artwork source/size/hash, search queries, file paths, file size and SHA-256, and processing status.

## 8. Artwork safety

Spotify album art is preserved in its original returned form. No cropping, resizing, recompressing, or other transformation is applied. If a Spotify image cannot be used as a valid front cover without modification, the pipeline falls back to its YTMusic artwork instead of altering the Spotify image.

## 9. Validation

No song reaches `songs.db` as completed until the final MP3 can be reopened, standard tags and key IDs are correct, artwork is present, and synced lyrics (when present) match the `.lrc` content. The sidecar is written atomically and the finalized MP3 is SHA-256 hashed before database commit.
