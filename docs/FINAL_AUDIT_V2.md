# Final Audit — Current Release

1. Permanent playlist serials are preserved.
2. ISRC is the only duplicate identifier.
3. Missing/invalid ISRC skips duplicate lookup.
4. Spotify ISRC takes precedence over source ISRC when Spotify enrichment matches.
5. Keep-previous and keep-current duplicate resolution are covered by transaction-aware logic.
6. Keep-current never destroys the previous retained file before the replacement is validated and committed.
7. Duplicate status is preserved across re-ingestion of the same usable source item.
8. Canonical ISRC is written to `songs.isrc`, indexed, and embedded as ID3 `TSRC` when available.
9. LRCLIB remains `/api/get` only.
10. Spotify artwork remains the largest API image, preserved unchanged.
