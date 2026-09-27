# Implementation Analysis and Hardening Notes

## Playlist ingestion

A playlist item can exist without a usable YTMusic `videoId`. The implementation preserves the occurrence and permanent serial, records the original playlist-item metadata, marks it as unavailable, and does not attempt a download until a usable source URL exists. A later refresh can reuse the same serial when the source becomes usable.

## Identity and duplicates

There is no duplicate detection, duplicate matching, or duplicate resolution. Every playlist occurrence is independent. Spotify ISRC is ordinary metadata only.

## Metadata architecture

The project deliberately separates three layers:

1. concise player-facing MP3 ID3 metadata;
2. important external IDs and URLs in TXXX/UFID/WXXX;
3. detailed/provenance data in a same-basename JSON sidecar.

The final MP3 has no raw source JSON, source description, age-limit data, or channel/uploader detail. The sidecar retains those details through normalized objects and complete raw API/source JSON.

## Spotify enrichment

Spotify is optional. Search uses `title + album`. Results are examined in returned order and the first track whose `duration_ms` is within the configured tolerance is selected. The full album object supplies the largest cover image and additional catalog metadata such as release date, track/disc number, label, copyrights and ISRC.

Spotify artwork is preserved without pixel modification. This follows Spotify's current developer documentation, which states that visual content must be kept in its original form.

## LRCLIB

Only `GET /api/get` is used. No `/api/search` request exists in the runtime flow. Requests use track title, artist, album and duration. Only timestamp-valid `syncedLyrics` are accepted.

## Lyrics output

With synced lyrics, the final folder contains MP3 + LRC + JSON. The MP3 contains the same synced lyrics as SYLT and a USLT plain-text compatibility frame. Without synced lyrics, only MP3 + JSON are produced and the MP3 contains no lyrics frames.

## Finalization

The output MP3 is tagged, reopened, validated, and hashed before promotion. The sidecar is written atomically. SQLite completion is committed only after the final MP3 exists.
