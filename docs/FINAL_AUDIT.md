# Final Audit

- Playlist identity remains serial-number based.
- Retained-song duplicate identity is now ISRC-only.
- Spotify ISRC is preferred when Spotify enrichment matches; source ISRC is the fallback.
- No fuzzy or metadata-combination duplicate heuristics are used.
- Duplicate decisions are explicit and user-controlled.
- Final MP3 validation verifies canonical ISRC in TSRC when available.
- Detailed metadata remains in the JSON sidecar.
- LRCLIB calls only `/api/get`.
- Synchronized lyrics remain embedded and written to `.lrc`.
