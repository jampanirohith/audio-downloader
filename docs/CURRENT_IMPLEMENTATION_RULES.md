# Current Implementation Rules

- Duplicate identification is ISRC-only.
- Spotify ISRC is a metadata source and the preferred ISRC when Spotify enrichment returns one.
- Source ISRC from yt-dlp may be used when Spotify does not supply one.
- Missing/invalid ISRC means no duplicate lookup.
- No title, artist, album, duration, YTMusic ID, YouTube ID, filename, hash, fuzzy, or heuristic duplicate matching.
- Duplicate resolution is user-controlled: keep previous or keep current.
- `keep_previous` -> current playlist status `duplicate`; existing retained song unchanged.
- `keep_current` -> validated current song replaces the prior retained song; prior playlist serial returns to `pending`.
- Spotify search uses `title + album`; first returned duration match within configured tolerance.
- Spotify artwork uses the largest returned album image unchanged.
- LRCLIB calls only `/api/get` and accepts synchronized lyrics only.
