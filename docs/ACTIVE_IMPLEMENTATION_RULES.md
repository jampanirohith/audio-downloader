# Active Implementation Rules

1. Playlist serial numbers remain permanent and unique.
2. ISRC is the only duplicate identifier.
3. Canonical ISRC is normalized to uppercase alphanumeric form before comparison/storage when a valid ISRC is available.
4. Spotify ISRC is used when Spotify enrichment finds one; source ISRC may be used as a fallback.
5. If no usable ISRC exists, duplicate detection is skipped; no title/artist/duration/hash fallback is used.
6. When a duplicate ISRC is found, the user chooses `keep_previous` or `keep_current`.
7. `keep_previous` marks the current playlist occurrence `duplicate` and preserves the retained song.
8. `keep_current` builds and validates the replacement first, then atomically replaces the retained database row and returns the previous playlist occurrence to `pending`; old physical artifacts are removed only after the database commit.
9. Spotify search remains `title + album`; the first duration-matching result within tolerance is selected.
10. Spotify artwork uses the largest API image and is preserved byte-for-byte.
11. LRCLIB uses only `GET /api/get`; never `GET /api/search`.
12. Only synchronized lyrics are accepted.
13. Synced outputs are MP3 + LRC + JSON in `songs/synced_lyrics/`; unsynced outputs are MP3 + JSON in `songs/no_synced_lyrics/`.
14. MP3 tags contain concise player-facing metadata, important IDs/URLs, artwork, and embedded synchronized lyrics.
15. Verbose/raw API metadata remains in the sidecar JSON.
16. YTMusic source ID, selected YouTube video ID, Spotify IDs, and canonical ISRC are retained when available.
