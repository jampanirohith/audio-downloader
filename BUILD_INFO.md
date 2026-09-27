# Build Information

## Release
Current build with ISRC-only duplicate detection restored.

## Verified
- 29 pytest tests passing.
- Python compilation succeeds for source, scripts and tests.
- `playlist.db` schema user_version=4.
- `songs.db` schema user_version=7.
- `songs.isrc` column and partial non-NULL index are present.
- `python main.py --status` succeeds on a fresh build.
- `python main.py --check-invariants` succeeds on a fresh build.
- Archive is rebuilt from the verified working tree.

## Duplicate behavior
- Identifier: normalized ISRC only.
- Spotify ISRC is preferred when matched; source ISRC is the fallback.
- Missing/invalid ISRC skips duplicate matching.
- No title/artist/album/duration/hash/fuzzy fallback.
- Duplicate resolution: interactive keep previous / keep current.

## Important current integrations
- Spotify search: title + album; first duration match within configured tolerance.
- Spotify album artwork: largest returned image, bytes preserved unchanged.
- LRCLIB: GET /api/get only; synchronized lyrics only.
- MP3: concise player-facing metadata, important IDs/URLs, ISRC, artwork, synchronized lyrics.
- JSON sidecar: detailed/raw source and API metadata.
