# Final Build Information

Release: Phase 1 current corrected build

## Locked behavior

- No duplicate detection, duplicate matching, or duplicate resolution.
- Spotify enrichment is optional and controlled by `config.json -> spotify.enabled`.
- Spotify search uses `title + album` and chooses the first returned track whose duration is within the configured tolerance.
- Spotify ISRC is metadata only.
- When Spotify is selected, its largest returned album image is downloaded and preserved byte-for-byte. No crop, resize, recompress, or visual transformation is applied.
- LRCLIB uses only `GET /api/get`. `/api/search` is never called.
- Only synchronized LRCLIB lyrics are saved as `.lrc`.
- Synced lyrics are embedded in the MP3 as ID3 SYLT plus USLT compatibility text.
- Every finalized MP3 has a same-basename `.json` sidecar containing detailed/raw metadata and integrity information.
- The MP3 contains only concise player-facing metadata, important YTMusic/YouTube/Spotify IDs/URLs, artwork, and lyrics.
- Source descriptions, age-limit information, channel details, raw API payloads, and extractor internals remain in the sidecar JSON.

## Verification

- Offline regression suite: 25 passed.
- Python bytecode compilation: passed.
- Package extraction/re-test: performed before release packaging.
- Live authenticated YouTube Music/Spotify/LRCLIB network execution is intentionally not claimed from the sandbox.
