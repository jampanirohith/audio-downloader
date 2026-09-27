# Current Implementation Rules

- No duplicate finding, duplicate matching, or duplicate resolution.
- Spotify ISRC is metadata only.
- Spotify search uses `title + album`; the first returned track whose duration is within the configured tolerance is selected.
- When selected, Spotify album artwork uses the largest API image and is preserved byte-for-byte. No crop, resize, or recompression is performed.
- LRCLIB uses only `GET /api/get`. There is no `/api/search` call or fallback.
- Only synchronized lyrics are eligible.
- Synced output gets MP3 + LRC + same-basename JSON in `songs/synced_lyrics/`.
- No-synced output gets MP3 + same-basename JSON in `songs/no_synced_lyrics/`.
- MP3 tags contain concise music metadata, YTMusic/YouTube/Spotify IDs and important URLs, artwork, and embedded synced lyrics.
- Source descriptions, age-limit details, channel/uploader details, extractor internals, raw API objects, and other verbose information belong in the sidecar JSON.
