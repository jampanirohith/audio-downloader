# Final Audit — ISRC Duplicate Release

- Canonical ISRC field added to normalized metadata.
- Spotify ISRC overlays canonical ISRC when available.
- Source ISRC is supported as fallback.
- Duplicate index exists on `songs.isrc` for non-NULL values.
- Duplicate checks exclude the current serial.
- Missing/invalid ISRC skips duplicate matching.
- Duplicate decisions are interactive unless a test resolver is injected.
- Keep-previous does not run YouTube/LRCLIB work after the duplicate decision.
- Keep-current never deletes the old physical artifacts before current validation and DB commit.
- Playlist duplicate status survives normal re-ingestion for the same usable source item.
- Final MP3 validates canonical ISRC in `TSRC` when present.
