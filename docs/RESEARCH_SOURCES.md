# Current External API Research

- Spotify Web API Search: https://developer.spotify.com/documentation/web-api/reference/search
- Spotify Web API Get Track: https://developer.spotify.com/documentation/web-api/reference/get-track
- Spotify Web API Get Album: https://developer.spotify.com/documentation/web-api/reference/get-an-album
- LRCLIB `/api/get` implementation/API architecture: https://github.com/tranxuanthang/lrclib/blob/main/ARCHITECTURE.md
- LRCLIB current lyricsId API change: https://github.com/tranxuanthang/lrclib/pull/116
- Mutagen ID3 documentation: https://mutagen.readthedocs.io/en/latest/user/id3.html

Notes:
- Spotify documents album images in multiple sizes and current track responses expose external IDs such as ISRC.
- Spotify's current developer policy says visual content must be kept in its original form, so this project does not crop or recompress Spotify album artwork.
- LRCLIB `/api/get` is metadata lookup. This project deliberately does not use `/api/search`.
- Mutagen supports SYLT for synchronized lyrics and USLT for unsynchronized lyric text.
