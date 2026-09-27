# Active Implementation Rules

This file supersedes historical Phase 1 rules where they conflict.

1. No duplicate detection.
2. Spotify ISRC is metadata only.
3. Spotify search: `title + album`; first duration-matching track within tolerance.
4. Spotify artwork: largest API image; preserve returned bytes exactly; no crop/resize/re-encode.
5. LRCLIB: only `GET /api/get`; never `GET /api/search`.
6. Accept lyrics only when synchronized lyrics are present and timestamp-valid.
7. Synced outputs: MP3 + LRC + JSON sidecar in `songs/synced_lyrics/`.
8. Unsynced outputs: MP3 + JSON sidecar in `songs/no_synced_lyrics/`.
9. MP3 contains concise standard ID3 + key IDs/URLs + artwork + embedded lyrics.
10. Verbose/raw metadata is stored in the same-basename sidecar JSON.
11. YTMusic source video ID and selected YouTube video ID are always retained when available.
12. The sidecar is written atomically and contains final file size/SHA-256.

Research basis: Spotify documents multiple album image sizes and requires visual content to be kept in its original form; LRCLIB documents `/api/get` metadata lookup and synchronized-lyrics fields; Mutagen documents SYLT and USLT frames.
