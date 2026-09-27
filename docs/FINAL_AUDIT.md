# Final Implementation Audit

### Identity
- Permanent playlist serials are retained.
- Duplicate finding/resolution has been removed.

### Spotify
- Optional via configuration.
- Search uses title + album.
- First duration-matching returned result is selected.
- Full album metadata is fetched.
- Largest artwork image is selected.
- Artwork bytes are preserved without modification.
- ISRC is metadata only.

### LRCLIB
- Only `/api/get` is called.
- `/api/search` is never used.
- Only synchronized lyrics are saved.

### MP3
- Concise standard music ID3 is embedded.
- Key YTMusic/YouTube/Spotify IDs and URLs are embedded.
- Artwork is embedded.
- Synced lyrics are embedded as SYLT + USLT.
- Raw JSON/source descriptions/channel detail are not embedded.

### JSON sidecar
- Same basename as MP3.
- Contains normalized metadata.
- Contains complete raw YTMusic, yt-dlp, YouTube, Spotify and LRCLIB records.
- Contains artwork provenance and hash.
- Contains lyric response/text and hashes.
- Contains final MP3 size and SHA-256.

### Verification
- Local regression suite is required to pass before packaging.
- Packaged archive is extracted and tested again.
