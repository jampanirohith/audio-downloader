# Metadata Embedding Contract

The MP3 is deliberately concise. Detailed provenance lives in the sidecar JSON.

## Standard ID3

- TIT2: title
- TPE1: track artist
- TPE2: album artist
- TALB: album
- TDRC: release date
- TRCK: track number when known
- TPOS: disc number when known
- TCON: genre when known
- TCOM: composer when known
- TPUB: publisher/label when known
- TCOP: copyright when known
- TLAN: language when known
- TBPM: BPM when known
- TCMP: compilation flag when known
- TENC: encoder when known
- TLEN: actual downloaded audio duration in milliseconds
- TSRC: Spotify ISRC when Spotify supplied it; never used for matching
- APIC type 3: front artwork
- SYLT: synchronized lyrics
- USLT: plain-text projection of the synchronized lyrics

## Key application metadata

TXXX is intentionally limited to concise, durable fields such as playlist serial, playlist position, YTMusic source ID, selected YouTube video ID/title, Spotify track/album ID, Spotify ISRC, lyric status, LRCLIB ID/match data, artwork provenance, and sidecar path.

UFID identifies the main external objects:

- `https://music.youtube.com/` -> YTMusic source video ID
- `https://www.youtube.com/` -> selected YouTube video ID
- `https://open.spotify.com/track/` -> Spotify track ID

WXXX carries the corresponding source URLs.

## Explicitly NOT embedded

The final MP3 must not contain GEOB raw JSON, source descriptions, channel/age-limit detail, extractor internals, or large raw API payloads. Those are stored in the same-basename JSON sidecar.

## Artwork

When Spotify enrichment is used and its album image is selected, the largest Spotify image is embedded without resizing/cropping/re-encoding. Spotify's developer documentation states that visual content should be kept in its original form.
