# Metadata Embedding

## Standard ID3

The MP3 uses standard ID3 frames for title, artists, album, release date, track/disc, genre, composer, publisher, copyright, language, BPM, compilation and duration where available.

`TSRC` contains the canonical ISRC when one is available. ISRC is also exposed as `TXXX:isrc`.

## Concise custom metadata

TXXX is limited to durable application/catalog fields such as serial number, playlist position, YTMusic source ID, selected YouTube ID/title, Spotify track/album IDs, Spotify ISRC, canonical ISRC, lyric status and artwork properties.

UFID and WXXX are used for machine-readable identities and important source/catalog URLs.

## Verbose data

The final MP3 deliberately does not contain raw API blobs, source descriptions, age-limit data, channel internals or downloader internals. Those details are retained in the same-basename JSON sidecar.
