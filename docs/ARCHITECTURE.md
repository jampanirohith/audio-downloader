# Architecture

```text
YouTube Music playlist
        |
        v
playlist ingestion -> permanent serials -> playlist.db
        |
        v
ONE yt-dlp acquisition
  |-- audio
  |-- info.json
  `-- thumbnails
        |
        +--> artwork selection (Spotify largest image when matched; YTMusic fallback)
        |
        +--> metadata normalization
        |
        +--> optional Spotify enrichment
        |
        +--> selected YouTube video metadata
        |
        `--> LRCLIB GET /api/get -> synced lyrics only
                    |
                    v
             final MP3 build
              |-- concise ID3
              |-- important IDs/URLs
              |-- APIC artwork
              `-- SYLT + USLT lyrics
                    |
                    +--> same-basename JSON sidecar (all detailed/raw metadata)
                    +--> optional LRC file
                    v
                 validate -> hash -> atomic promote -> songs.db
```
