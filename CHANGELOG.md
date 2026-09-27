# Current Release Changes

## Final correction

- LRCLIB is restricted to `/api/get` only.
- Removed the old LRCLIB `/api/search` fallback.
- Spotify enrichment is optional and selects the first duration-matching search result.
- Spotify largest album artwork is preserved at original API resolution without pixel transformation.
- Non-square Spotify artwork is rejected instead of cropped; the pipeline falls back to YTMusic artwork.
- Added full synced-lyrics embedding with SYLT + USLT.
- Added same-basename JSON sidecar for every final MP3.
- Moved verbose source/API details out of MP3 ID3 and into the sidecar.
- MP3 now keeps concise standard music metadata plus important source IDs/URLs.
- Preserved YTMusic source video ID and selected YouTube video ID.
- Retained Spotify ISRC as ordinary metadata only; it has no duplicate-detection role.
- Hardened unavailable YTMusic playlist items with `videoId=None`.
- Fixed inspection tooling and active documentation to match the final architecture.
