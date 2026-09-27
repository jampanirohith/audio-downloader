# Phase 1 — YouTube Music Playlist Downloader & Enricher

This build ingests a YouTube Music playlist, downloads each usable playlist occurrence, enriches its metadata with optional Spotify data, selects a YouTube music-video result, fetches only synchronized LRCLIB lyrics through `/api/get`, embeds concise metadata/artwork/lyrics into the MP3, and writes a detailed same-basename JSON sidecar.

## Current rules

- Permanent playlist serial numbers are never reused.
- ISRC is the **only duplicate identifier**.
- Spotify ISRC is preferred when Spotify enrichment finds a matching track; source ISRC can be used as a fallback.
- Missing or invalid ISRC means duplicate checking is skipped.
- No title/artist/album/duration/hash/fuzzy fallback is used for duplicates.
- On duplicate, the operator chooses **keep previous** or **keep current**.
- Keep-current validates the replacement before removing the prior retained song; the DB transition is transactional and old files are cleaned after commit.
- Spotify search is `title + album`; the first result within the configured duration tolerance is selected.
- Spotify artwork uses the largest API image unchanged.
- LRCLIB uses only `GET /api/get`; `/api/search` is never called.
- Only synchronized lyrics are accepted. Synced outputs contain MP3 + LRC + JSON; unsynced outputs contain MP3 + JSON.
- The MP3 contains player-facing metadata, important source/catalog IDs/URLs, canonical ISRC when available, artwork, and synchronized lyrics. Verbose/raw data belongs in the sidecar JSON.

## Configuration

`config.json` includes:

```json
"duplicate_detection": {
  "enabled": true,
  "identifier": "isrc",
  "on_duplicate": "prompt"
}
```

Set Spotify credentials in the `spotify` section or use `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` environment variables.

## Run

```powershell
python main.py --doctor
python main.py
```

To retry entries that are in the `error` state:

```powershell
python main.py --retry-errors
```

To inspect current state:

```powershell
python main.py --status
python main.py --check-invariants
```

## Output layout

```text
songs/
├── synced_lyrics/
│   ├── 001_Title_Artist.mp3
│   ├── 001_Title_Artist.lrc
│   └── 001_Title_Artist.json
└── no_synced_lyrics/
    ├── 002_Title_Artist.mp3
    └── 002_Title_Artist.json
```
