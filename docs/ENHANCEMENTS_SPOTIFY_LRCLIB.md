# Spotify + LRCLIB Enhancement

## Spotify

The pipeline optionally calls Spotify Web API search with `q = title + album`, retrieves track data, and chooses the first returned result whose `duration_ms` is within the configured tolerance of the downloaded YTMusic audio duration. The full album object is fetched so that the largest album cover image can be selected. Spotify documents multiple album-image sizes and track external IDs such as ISRC.

The Spotify cover bytes are saved without transformation and become the APIC cover. The source image URL, dimensions, MIME type and SHA-256 are recorded in the sidecar.

## LRCLIB

Only `GET /api/get` is used. The client never calls `/api/search`. The request uses title, artist, album and duration. The current LRCLIB codebase documents metadata lookup on `/api/get` and duration-aware matching around roughly two seconds; the API response can contain `syncedLyrics` and `lyricsId`.

Only synchronized results are accepted. A plain-only response is treated as no synced lyrics.

## Output

With synchronized lyrics:

```text
songs/synced_lyrics/name.mp3
songs/synced_lyrics/name.lrc
songs/synced_lyrics/name.json
```

Without synchronized lyrics:

```text
songs/no_synced_lyrics/name.mp3
songs/no_synced_lyrics/name.json
```

The MP3 embeds the LRC timing/text as SYLT plus a USLT compatibility projection. The JSON contains the complete lyric response and downloaded lyric text.
