# Test Matrix

| Area | Coverage |
|---|---|
| Unavailable YTMusic item | Preserve serial; no ingestion crash |
| Spotify matching | Returned-order duration match |
| Spotify artwork | Largest image; byte-for-byte preservation |
| LRCLIB | `/api/get` only; no `/api/search` |
| Synced lyrics | LRC file + SYLT + USLT |
| No synced lyrics | No LRC; unsynced folder |
| Sidecar | Same-basename JSON with detailed metadata |
| MP3 metadata | Concise standard ID3 + key IDs/URLs |
| Verbose tags | GEOB/COMM rejected |
| Database | Current schema and serial invariants |
| Filename safety | Windows-safe filenames |
| Packaging | Extracted archive re-test |
