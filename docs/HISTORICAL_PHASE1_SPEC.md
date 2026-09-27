# Phase 1 — Active Implementation Specification

This document describes the current implementation contract for the project.

## 1. Identity and playlist behavior

- Every playlist occurrence receives one permanent integer serial number.
- Serial numbers are assigned in the order returned by YTMusic during first ingestion.
- A serial is never changed or reused.
- Repeated occurrences are independent playlist records and can each produce a retained MP3.
- The YTMusic source video ID is source metadata, not playlist identity.
- Playlist order is preserved in `playlist_position`.
- `playlist.db` is the permanent record of playlist occurrences and processing state.
- `songs.db` records the retained file for completed occurrences.

## 2. Unavailable YTMusic entries

YTMusic may return an item whose `videoId` is missing or whose `isAvailable` flag is false. Such an occurrence is preserved with its permanent serial, title, artist, album, duration, original playlist-item JSON, and a descriptive error state. It must not crash ingestion or erase other playlist records.

When a later ingestion observes a usable source ID for the same occurrence, reconciliation can restore the existing serial to `pending`.

The current implementation calls `get_playlist(..., limit=None, related=False, suggestions_limit=0)` so the complete playlist is requested and unrelated suggestions are not mixed into the track list. The YTMusic API documentation states that `limit=None` retrieves all items and that `tracks` contains playlist-item dictionaries.

## 3. Source acquisition

Each usable entry is acquired with one complete yt-dlp operation. The acquisition writes:

- final source audio converted to MP3;
- complete `master.info.json` source metadata;
- all available thumbnail variants.

The acquisition does not use yt-dlp's metadata-embedding option. Python/Mutagen owns the final ID3 write.

## 4. Metadata model

The application maintains three layers:

1. Raw source objects: exact YTMusic playlist-item JSON and exact yt-dlp info JSON.
2. Normalized application metadata: predictable typed fields used by the database and standard ID3 frames.
3. Final embedded metadata: standard ID3 frames, application/source TXXX fields, URL frames, machine-readable unique IDs, compressed complete raw JSON, and embedded artwork.

No raw downloader object is discarded merely because ID3 has no dedicated standard frame for it.

## 5. Complete embedded metadata

The final MP3 contains:

- native ID3 frames for common music fields;
- TXXX fields for every normalized metadata field;
- explicit YTMusic playlist/source identity fields;
- explicit selected YouTube video fields;
- raw top-level fields from the YTMusic playlist item and yt-dlp objects where suitable for direct TXXX export;
- WXXX URLs for important source links;
- UFID frames for the YTMusic source video ID and selected YouTube video ID;
- gzip-compressed GEOB frames containing the complete raw source/YTMusic/selected-video JSON objects;
- square front-cover artwork in APIC.

The complete GEOB objects are the lossless metadata record. TXXX/native frames are the player-friendly projection.

## 6. YouTube video enrichment

The search query is constructed as:

```text
{title} {album_name} official video song
```

Search results are processed in returned order. A result whose title contains `lyrics` as a word, case-insensitively, is skipped. The first remaining result is selected immediately. No post-retrieval ranking or scoring is performed.

The selected result is enriched using its complete yt-dlp metadata object. If no acceptable result exists, the song still completes and the selected-video fields are absent.

## 7. Artwork

The initial acquisition requests all thumbnail variants. The application additionally inspects the YouTube Music page artwork when configured to do so. Square candidates are preferred; among square candidates, the largest usable image is preferred. A non-square fallback is center-cropped to a square. EXIF orientation is corrected and the final cover is normalized to JPEG.

This behavior addresses the documented case where ordinary YouTube thumbnail URLs can be 480×360 with borders while the YouTube Music page exposes square `lh3.googleusercontent.com` artwork.

## 8. Finalization and integrity

The final MP3 is first created as a temporary production file. After all metadata and artwork are written, it is reopened and validated. Only then is SHA-256 calculated and the temporary production file atomically renamed to the final filename.

The database commit occurs only after the final file is valid. Temporary files are removed after successful commit.

## 9. Filename rules

The final filename is:

```text
{serial:03d}_{safe_title}_{safe_artist}.mp3
```

The full filename is bounded by a configurable maximum so Windows path handling is safe. Serial identity is always retained in the filename.

## 10. Recovery

- A failed processing attempt records `error` on the playlist entry.
- Entries with usable source URLs can be returned to `pending`.
- Null-source unavailable entries are not placed into the processing queue.
- Existing temporary work is represented by a per-serial manifest.
- Failed final files are never registered as completed song rows.
- Post-commit cleanup failure does not retroactively convert a valid completed song into an error.

## 11. Verification contract

A completed item must have:

- a valid retained MP3;
- readable audio duration;
- required metadata frames;
- complete raw source objects in GEOB;
- valid embedded square artwork;
- recorded SHA-256 and file size;
- a matching completed playlist record.
