# Implementation Analysis

## Identity and duplicates

A playlist occurrence has a permanent serial number. Retained-song identity uses ISRC as the sole duplicate key. Canonical ISRC is stored in `songs.isrc` and indexed. Spotify ISRC is preferred when Spotify enrichment returns one; yt-dlp/source ISRC is the fallback. Missing or invalid ISRC skips duplicate matching.

Duplicate handling is interactive. `keep_previous` marks the current playlist occurrence `duplicate` and preserves the existing retained row/file. `keep_current` builds and validates the new MP3 first, then uses one SQLite transaction to remove the prior retained row, insert the current row, mark the current playlist occurrence completed, and return the prior playlist serial to pending. The old physical artifacts are deleted only after that commit.

## Spotify

Spotify is optional. Search uses `title + album`; results are checked in returned order and the first result within the duration tolerance of the actual downloaded YTMusic audio is selected. The full album object supplies artwork and catalog metadata. Track external IDs can include ISRC. The Spotify ISRC is both embedded as normal metadata and used as the preferred duplicate identifier when present.

## Lyrics

Only LRCLIB `/api/get` is called. Only synchronized lyrics are accepted. The same synchronized content is written to the LRC sidecar file and embedded into the MP3 as SYLT plus USLT compatibility text.

## MP3 and sidecar

The MP3 contains concise player-facing fields, core IDs and URLs, canonical ISRC when available, artwork, and synchronized lyrics. Verbose source/API objects are retained in the same-basename JSON sidecar so the MP3 remains interoperable without becoming a raw metadata dump.
