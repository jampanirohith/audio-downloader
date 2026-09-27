# Final Audit — Current Build

## Rules verified

1. No duplicate detection or duplicate resolution.
2. Spotify optional and metadata-only; ISRC never participates in identity or matching.
3. Spotify selected track = first duration-matching result in returned order.
4. Largest Spotify artwork is downloaded and preserved without transformation.
5. LRCLIB client calls only `/api/get`.
6. Only synced LRCLIB lyrics produce `.lrc` files.
7. Synced lyrics are embedded as SYLT + USLT.
8. Each MP3 has a same-basename JSON sidecar with detailed metadata.
9. MP3 contains concise metadata only; no raw GEOB/COMM/source-description dump.
10. YTMusic source video ID and selected YouTube video ID are preserved when available.
11. Final MP3 validation happens before SHA-256 and database commit.

Offline test verification is performed by `pytest -q`.
