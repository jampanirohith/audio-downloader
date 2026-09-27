# Current Project Specification

## Identity and duplicates
A playlist occurrence retains a permanent serial number. The retained-song duplicate identifier is ISRC only. A valid ISRC is normalized before comparison. When a duplicate is found, the operator chooses whether to keep the previously retained song or the current song. Missing ISRC means no duplicate check.

## Spotify
When enabled, search with `{title} {album}`. Iterate returned Spotify tracks in returned order and select the first track whose duration is within `duration_tolerance_seconds` of the actual downloaded YTMusic audio duration. Use matched Spotify catalog metadata to enrich the song and store Spotify identifiers and ISRC.

## Lyrics
Call only LRCLIB `GET /api/get`. Do not call `/api/search`. Accept only synchronized lyrics. Store the LRC beside synced songs and embed synchronized lyrics in the MP3.

## MP3 vs sidecar
The MP3 carries concise, interoperable music metadata, the main YTMusic/YouTube/Spotify identifiers and URLs, canonical ISRC when available, artwork, and synchronized lyrics. The same-basename sidecar JSON stores verbose/raw source and API metadata, artwork provenance, lyrics response/match information, duplicate-resolution details, and final file hashes.
