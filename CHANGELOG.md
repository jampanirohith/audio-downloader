# Changelog

## Current release
- Restored ISRC as the sole duplicate identifier.
- Added canonical `songs.isrc` storage and indexed lookup.
- Added interactive keep-previous / keep-current duplicate resolution.
- Added safe replacement transaction for keep-current with post-commit old-file cleanup.
- Preserved permanent playlist serials during duplicate replacement.
- Preserved duplicate status across playlist re-ingestion.
- Added ISRC to standard `TSRC` and concise `TXXX:isrc` metadata.
- Retained Spotify ISRC separately as `spotify_isrc`.
- Added duplicate-resolution details to the JSON sidecar.
- Bumped MP3 metadata export version to 6.
