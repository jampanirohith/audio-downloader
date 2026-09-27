# ISRC Duplicate Detection

The project uses ISRC as the sole retained-song duplicate identifier.

## Canonical value
ISRC is normalized by removing spaces/hyphens, upper-casing, and accepting the standard 12-character ISRC shape. Invalid values are treated as missing.

## Source precedence
1. Spotify matched-track ISRC when Spotify enrichment is enabled and a track is matched.
2. yt-dlp/source metadata ISRC when Spotify does not supply one.

The canonical value is stored in `songs.isrc`, emitted as ID3 `TSRC`, and also available as `TXXX:isrc`. Spotify's original value remains in `spotify_isrc`.

## Duplicate lookup
Only `songs.isrc` is queried. If no ISRC exists, the current song proceeds without a duplicate lookup.

## User resolution
- Keep previous: current playlist entry becomes `duplicate`; the retained row/file stays untouched.
- Keep current: the new MP3 is fully built and validated first. One SQLite transaction removes the previous retained row, inserts the current row, marks the current playlist entry `completed`, and returns the previous playlist serial to `pending`. Physical removal of the old serial's artifacts occurs only after the transaction commits.
