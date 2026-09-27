# Active Specification — Current Build

## MP3

The MP3 contains only player-facing metadata and the most useful external identities:

- Title, artist, album, album artist
- Release date
- Track/disc numbers
- Genre, composer, publisher/label, copyright, language, BPM, compilation and duration when known
- YTMusic source video ID and URL
- Selected YouTube music-video ID, URL and title
- Spotify track ID, album ID and URL when matched
- Spotify ISRC when returned, as ordinary metadata only
- Front-cover artwork
- Synchronized lyrics as ID3 SYLT plus USLT compatibility text

Do not put source descriptions, age limits, channel details, extractor internals, or raw API blobs into the MP3.

## Sidecar

Every finalized MP3 has the same basename with `.json`. The sidecar is the detailed record and may contain all source/API fields, complete raw JSON objects, searches, identifiers, artwork provenance, lyrics response/text, and final file hashes.

## Spotify artwork

When Spotify enrichment is selected and artwork is enabled, select the largest album image returned by Spotify. Preserve the downloaded bytes exactly; do not crop, resize, recompress, sharpen, color-convert, or otherwise transform them. Spotify's current Web API documentation explicitly says visual content must be kept in its original form.

## LRCLIB

Only `GET /api/get` may be called. Never call `/api/search`. Accept only responses containing valid synchronized lyrics. The service documents `/api/get` as the metadata lookup route and its current implementation describes duration-aware matching; current responses can expose `lyricsId` and `syncedLyrics`.
