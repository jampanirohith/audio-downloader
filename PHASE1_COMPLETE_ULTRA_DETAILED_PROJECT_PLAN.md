# PHASE 1 — YouTube Music Playlist Downloader & Enricher

## Complete Ultra-Detailed Project Plan — Current Authoritative Build

**Status:** Current consolidated implementation plan

**Purpose:** This document consolidates the original Phase 1 specification and every subsequent project change discussed during implementation. The **Current Authoritative Specification** sections describe what the implementation is intended to do now. The **Historical Original Specification** appendix preserves the original planning document verbatim so no original requirement is lost. Where later requirements changed an earlier rule, the current rule explicitly takes precedence and the superseded rule is identified.

**Generated:** 2026-09-27

---

# 1. Executive Summary

This project is a standalone Python pipeline that ingests one YouTube Music playlist, assigns every playlist occurrence a permanent serial number, downloads usable YT Music source audio, enriches the song with optional Spotify catalog information, locates one YouTube music-video result using the project's deterministic search rule, obtains only synchronized lyrics from LRCLIB through `GET /api/get`, selects high-quality artwork, writes a concise and player-compatible final ID3 metadata set, embeds synchronized lyrics, creates a same-basename detailed JSON sidecar, validates and hashes the final MP3, and commits the resulting retained-song record into SQLite.

The architecture deliberately separates:

1. **Playlist identity** — permanent serial + playlist position in `playlist.db`.
2. **Retained song identity** — song row in `songs.db`, with **ISRC as the only duplicate identifier** when an ISRC exists.
3. **Source metadata** — detailed YT Music/yt-dlp information.
4. **Catalog enrichment** — optional Spotify information and Spotify artwork.
5. **Video enrichment** — selected YouTube music-video ID/title/URL and core facts.
6. **Lyrics enrichment** — LRCLIB synchronized lyrics only.
7. **Player-facing MP3 metadata** — concise standard ID3 + durable custom identifiers + artwork + lyrics.
8. **Full detailed provenance** — same-basename JSON sidecar containing detailed source/API fields, raw JSON, selection information, artwork provenance, lyric response/matching details, and file hashes.

The current implementation intentionally does **not** dump raw source descriptions, age-limit information, channel internals, downloader internals, or raw API blobs into the main MP3 metadata. Those details belong in the JSON sidecar.

---

# 2. Current Authoritative Rules

These rules are locked for the current build unless explicitly changed in a future revision.

## 2.1 Playlist identity

- Every playlist occurrence receives one permanent integer serial number.
- Serial numbers are assigned according to the order returned by YTMusic playlist ingestion.
- Serial numbers never change.
- Serial numbers are never reused.
- Repeated tracks in the playlist remain separate playlist occurrences.
- The permanent serial is the stable link between a playlist occurrence and its retained file/record.

## 2.2 Playlist ingestion

- The complete playlist is read through `ytmusicapi`.
- Returned playlist order is authoritative.
- No alphabetical, artist, duration, popularity, ISRC, or other sorting is performed.
- An unavailable item (`videoId=None`, `isAvailable=False`) must not crash ingestion.
- An unavailable entry is preserved with its serial and position and recorded as `error` until it can be retried.
- When a previously unavailable occurrence later becomes usable, the existing serial is reused rather than assigning a new serial.

## 2.3 Source download

- The actual song audio comes from the YT Music source associated with the playlist occurrence.
- One complete initial `yt-dlp` acquisition is used for audio, source `info.json`, and thumbnails.
- `--add-metadata` is not used by the initial acquisition.
- FFmpeg/FFprobe are required.
- A supported JavaScript runtime may be required by the installed yt-dlp version for some YouTube extraction paths.

## 2.4 Spotify enrichment

- Spotify enrichment is optional and controlled by configuration.
- Client Credentials authentication is used.
- Credentials may be supplied in `config.json` or via `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` environment variables.
- Search query is exactly `title + album`.
- Returned Spotify result order is preserved.
- The first returned result within the configured duration tolerance of the actual downloaded YT Music audio duration is selected.
- No Spotify candidate scoring system is used.
- No Spotify result ranking beyond returned order + duration match is introduced.
- Spotify can enrich core music metadata.
- Spotify ISRC is preferred as the canonical ISRC when a Spotify track is successfully matched and supplies a valid ISRC.
- If Spotify does not supply a valid ISRC, valid source ISRC from yt-dlp may be used.
- ISRC is metadata and the sole duplicate identifier; it is not used for any other matching heuristic.
- Spotify artwork uses the largest album image returned by Spotify.
- Spotify artwork bytes are preserved byte-for-byte and are not cropped, resized, recompressed, sharpened, recolored, or otherwise transformed.
- If Spotify artwork is unavailable/invalid for the intended use, the pipeline may fall back to the YT Music artwork pipeline.

## 2.5 ISRC duplicate detection

- ISRC is the **only** retained-song duplicate identifier.
- Canonical ISRC is normalized by removing spaces and hyphens and uppercasing alphanumeric content, then validated against the standard 12-character form.
- Invalid ISRC is treated as missing.
- Missing/invalid ISRC means no duplicate lookup is performed.
- No title, artist, album, duration, YT Music ID, YouTube ID, filename, audio hash, fuzzy similarity, or composite metadata matching is permitted.
- When a duplicate exists, the operator explicitly chooses `keep_previous` or `keep_current`.

## 2.6 Duplicate resolution

### Keep previous

- The existing retained song is untouched.
- The previous MP3/LRC/JSON remains untouched.
- The current temporary acquisition is discarded.
- The current playlist occurrence is marked `duplicate`.
- No current `songs.db` row is created.

### Keep current

- The current replacement is completely built and validated before old physical artifacts are destroyed.
- The old retained row and current retained row transition is performed transactionally.
- The old playlist serial is returned to `pending`.
- The current playlist serial becomes `completed`.
- The old physical artifacts are cleaned after the database commit.
- Playlist serial identities never change.

## 2.7 YouTube music-video discovery

- Search query is built as `{title} {album} official video song` using normalized/current song metadata.
- Search results are consumed in returned order.
- A result is skipped only when its title contains the word `lyrics`, case-insensitively.
- The first remaining result is immediately selected.
- No result score, confidence value, ranking, weighted heuristic, duration comparison, channel comparison, popularity comparison, or manual weighting is performed by the application.
- If every fetched result contains `lyrics`, there is no selected video.
- Lack of an acceptable YouTube result does not fail the song.

## 2.8 LRCLIB lyrics

- Only `GET /api/get` is permitted.
- `/api/search` is never called.
- Lookup uses the current song metadata and duration.
- Only valid synchronized lyrics are accepted.
- Plain-only lyrics are not downloaded as `.lrc` and do not count as synchronized lyrics.
- Synced lyrics are saved alongside the MP3 as `.lrc`.
- Synced lyrics are also embedded into the MP3 using synchronized lyrics metadata plus a compatibility plain-text lyrics projection.
- Songs with synced lyrics are stored under `songs/synced_lyrics/`.
- Songs without synced lyrics are stored under `songs/no_synced_lyrics/`.
- Unsynced songs do not receive an `.lrc` file.

## 2.9 Artwork

- Spotify is the preferred final artwork provider when Spotify enrichment is enabled, a track is matched, and usable album artwork is available.
- The largest Spotify image returned is selected.
- Spotify image bytes are preserved unchanged.
- For YT Music fallback artwork, all useful yt-dlp thumbnail variants may be considered and a page OpenGraph image may be inspected.
- The YT Music fallback prefers a valid square candidate and can normalize a non-square fallback to square JPEG.
- Artwork is embedded as front cover APIC.

## 2.10 MP3 metadata

The MP3 is intentionally concise and player-facing. It contains:

- Title
- Track artist
- Album artist
- Album
- Release date
- Track/disc number when known
- Genre when known
- Composer when known
- Publisher/label when known
- Copyright when known
- Language when known
- BPM when known
- Compilation when known
- Actual MP3 duration
- Canonical ISRC when available
- YT Music source video ID and URL
- Selected YouTube music-video ID, URL and title
- Spotify track ID, album ID, URL and ISRC when matched/available
- Front-cover artwork
- Synchronized lyrics
- A small durable set of application metadata via TXXX/UFID/WXXX

The MP3 does **not** contain the large raw API blobs or verbose source/debug information.

## 2.11 Sidecar JSON

Every finalized MP3 gets a same-basename `.json` sidecar.

The JSON is the detailed record and can contain:

- Complete normalized metadata
- Playlist identity
- YT Music playlist-item JSON
- yt-dlp source `info.json`
- Spotify search/match information
- Spotify track JSON
- Spotify album JSON
- Spotify artwork provenance
- Selected YouTube search information
- Selected YouTube information JSON
- LRCLIB response/matching information
- Downloaded synchronized lyric text
- Artwork provenance and hashes
- MP3 file size/hash
- LRC path/status
- Duplicate decision information
- Build/schema versions

---

# 3. End-to-End Architecture

```text
YouTube Music Playlist
        |
        v
YTMusic API ingestion
        |
        +--> preserve API order
        +--> assign/reuse permanent serials
        |
        v
playlist.db
        |
        v
next pending playlist occurrence
        |
        v
Create temp/{serial}/
        |
        v
ONE yt-dlp acquisition
  |-- master.mp3
  |-- master.info.json
  `-- thumbnails
        |
        +--> source validation
        |
        +--> metadata normalization
        |
        +--> optional Spotify search
        |       |
        |       +--> first duration match
        |       `--> optional largest Spotify artwork
        |
        +--> canonical ISRC determination
        |       |
        |       `--> ISRC-only duplicate lookup
        |                |
        |                +--> unique
        |                |
        |                `--> user decision
        |                         |
        |                         +--> keep previous
        |                         `--> keep current
        |
        +--> YouTube video search
        |       |
        |       `--> first result not containing 'lyrics'
        |
        +--> LRCLIB GET /api/get
        |       |
        |       `--> synchronized lyrics only
        |
        +--> artwork selection
        |
        v
final metadata model
        |
        +-------------------+
        |                   |
        v                   v
concise MP3 tags       detailed sidecar JSON
        |                   |
        +-- APIC             +-- raw source JSON
        +-- SYLT             +-- Spotify JSON
        +-- USLT             +-- YouTube JSON
        +-- standard ID3     +-- LRCLIB data
        +-- TXXX             +-- provenance
        +-- UFID             +-- hashes
        +-- WXXX             +-- file information
        |
        v
validate final MP3
        |
        v
SHA-256
        |
        v
atomic promotion
        |
        +--> songs/.../*.mp3
        +--> songs/.../*.lrc (synced only)
        +--> songs/.../*.json
        |
        v
transactional SQLite commit
        |
        +--> songs.db
        `--> playlist.db status=completed
```

---

# 4. Project Directory

```text
phase1_project/
├── main.py
├── config.json
├── cookies.txt
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── README.md
├── BUILD_INFO.md
├── CHANGELOG.md
├── .gitignore
│
├── src/
│   ├── __init__.py
│   ├── db_playlist.py
│   ├── db_songs.py
│   ├── playlist_ingest.py
│   ├── downloader.py
│   ├── metadata.py
│   ├── duplicate_checker.py
│   ├── spotify.py
│   ├── youtube_finder.py
│   ├── lrclib.py
│   ├── artwork.py
│   ├── embedder.py
│   ├── validator.py
│   ├── hashing.py
│   ├── sidecar.py
│   └── pipeline.py
│
├── scripts/
│   ├── clean_runtime.py
│   ├── init_db.py
│   ├── inspect_mp3.py
│   └── reembed_existing.py
│
├── tests/
│   ├── test_phase1.py
│   └── fixtures/
│       ├── sample.mp3
│       └── sample.jpg
│
├── docs/
│   ├── ACTIVE_SPEC.md
│   ├── ACTIVE_IMPLEMENTATION_RULES.md
│   ├── CURRENT_IMPLEMENTATION_RULES.md
│   ├── DUPLICATE_ISRC.md
│   ├── METADATA_EMBEDDING.md
│   ├── ENHANCEMENTS_SPOTIFY_LRCLIB.md
│   ├── ARTWORK_FIX.md
│   ├── ARCHITECTURE.md
│   ├── TEST_MATRIX.md
│   ├── FINAL_AUDIT*.md
│   ├── HISTORICAL_PHASE1_SPEC.md
│   ├── project_spec.md
│   ├── implementation_analysis.md
│   └── runtime_notes.md
│
├── songs/
│   ├── synced_lyrics/
│   │   ├── <name>.mp3
│   │   ├── <name>.lrc
│   │   └── <name>.json
│   └── no_synced_lyrics/
│       ├── <name>.mp3
│       └── <name>.json
│
├── temp/
├── logs/
│   └── phase1.log
└── db/
    ├── playlist.db
    └── songs.db
```

---

# 5. Runtime Dependencies

## 5.1 Python

- Python 3.11+.

## 5.2 Python packages

The project requires these functional dependencies:

- `ytmusicapi`
- `yt-dlp`
- `mutagen`
- `requests`
- `Pillow`

Development/testing dependencies include pytest tooling.

## 5.3 External binaries

- FFmpeg
- FFprobe
- A supported JavaScript runtime for yt-dlp where the installed yt-dlp extraction path requires it.

## 5.4 Runtime doctor

`python main.py --doctor` checks the configuration/environment and reports missing runtime components before normal processing.

---

# 6. Configuration

The configuration controls integration availability and operational limits but must not silently change architectural rules.

Current example:

```json
{
  "ytmusic_playlist_id": "YOUR_PLAYLIST_ID",
  "ytmusic_auth_file": null,
  "paths": {
    "songs": "songs",
    "songs_with_synced_lyrics": "songs/synced_lyrics",
    "songs_without_synced_lyrics": "songs/no_synced_lyrics",
    "temp": "temp",
    "database": "db",
    "logs": "logs"
  },
  "download": {
    "audio_format": "mp3",
    "audio_quality": "0",
    "write_info_json": true,
    "write_thumbnail": true,
    "convert_thumbnail": "jpg",
    "write_all_thumbnails": true
  },
  "youtube_video_search": {
    "results_to_fetch": 10,
    "skip_title_keyword": "lyrics"
  },
  "spotify": {
    "enabled": false,
    "client_id": "",
    "client_secret": "",
    "use_env": true,
    "market": "IN",
    "search_limit": 10,
    "duration_tolerance_seconds": 2,
    "timeout_seconds": 30,
    "max_retries": 3,
    "fail_on_error": false,
    "artwork": {
      "enabled": true,
      "timeout_seconds": 30,
      "fail_on_error": false
    }
  },
  "lyrics": {
    "enabled": true,
    "timeout_seconds": 30,
    "max_retries": 3,
    "request_delay_seconds": 0.5,
    "user_agent": "Phase1AudioDownloader/1.0 (https://github.com/your-user/your-repo)",
    "fail_on_error": false,
    "endpoint": "/api/get",
    "download_only_synced": true,
    "embed_synced": true,
    "embed_plain_fallback": true
  },
  "retry": {
    "max_attempts": 3,
    "backoff_seconds": 2
  },
  "yt_dlp_binary": "yt-dlp",
  "cookies_file": "cookies.txt",
  "ffmpeg_location": null,
  "js_runtime": "auto",
  "js_runtime_path": null,
  "socket_timeout_seconds": 30,
  "download_timeout_seconds": 3600,
  "youtube_search_timeout_seconds": 120,
  "youtube_metadata_timeout_seconds": 120,
  "max_description_chars": 0,
  "artwork": {
    "og_image_enabled": true,
    "og_image_timeout_seconds": 30,
    "force_square": true,
    "max_dimension": 1200,
    "jpeg_quality": 98
  },
  "filesystem": {
    "max_filename_length": 180
  },
  "duplicate_detection": {
    "enabled": true,
    "identifier": "isrc",
    "on_duplicate": "prompt"
  }
}

```

## 6.1 Configuration semantics

### YouTube Music

- `ytmusic_playlist_id`: playlist to ingest.
- `ytmusic_auth_file`: optional authentication file.

### Paths

- `songs`: root song directory.
- `songs_with_synced_lyrics`: final synced output directory.
- `songs_without_synced_lyrics`: final non-synced output directory.
- `temp`: per-entry work area.
- `database`: SQLite directory.
- `logs`: application logs.

### Download

- `audio_format`: final audio format (`mp3`).
- `audio_quality`: yt-dlp audio quality selection.
- `write_info_json`: source info JSON must be written.
- `write_thumbnail`: artwork acquisition must be attempted.
- `convert_thumbnail`: YT Music fallback thumbnail conversion format.
- `write_all_thumbnails`: collect all available yt-dlp thumbnail variants for selection.

### YouTube video search

- `results_to_fetch`: maximum results fetched.
- `skip_title_keyword`: title exclusion keyword; current value `lyrics`.

### Spotify

- `enabled`: enable/disable enrichment.
- `client_id`, `client_secret`: credentials.
- `use_env`: permit environment-variable credential overrides.
- `market`: Spotify market used for search/catalog requests.
- `search_limit`: number of search results requested.
- `duration_tolerance_seconds`: maximum allowed duration difference.
- request timeout/retry controls.
- `artwork.enabled`: enable Spotify artwork.
- artwork timeout/failure behavior.

### Lyrics

- `enabled`: enable LRCLIB integration.
- `timeout_seconds`: HTTP timeout.
- `max_retries`: retry count.
- `request_delay_seconds`: throttle between calls.
- `user_agent`: HTTP user-agent.
- `fail_on_error`: whether LRCLIB failure should fail the song.
- `endpoint`: must remain `/api/get`.
- `download_only_synced`: synchronized lyrics only.
- `embed_synced`: embed synchronized lyrics.
- `embed_plain_fallback`: current compatibility behavior; no unsynced `.lrc` is created.

### Retry

- `max_attempts`: pipeline attempts.
- `backoff_seconds`: delay between attempts.

### yt-dlp / network

- `yt_dlp_binary`: command/executable.
- `cookies_file`: optional cookies.
- `ffmpeg_location`: optional explicit FFmpeg location.
- `js_runtime`, `js_runtime_path`: JavaScript runtime selection.
- socket/download/search/metadata timeouts.

### Artwork

- `og_image_enabled`: inspect page OpenGraph image for YT Music fallback.
- `og_image_timeout_seconds`: OG request timeout.
- `force_square`: square YT Music fallback normalization.
- `max_dimension`: maximum normalized YT Music fallback size.
- `jpeg_quality`: YT Music fallback JPEG quality.

### Filesystem

- `max_filename_length`: maximum safe final filename length.

### Duplicate detection

- `enabled`: enable ISRC duplicate handling.
- `identifier`: must be `isrc` for current architecture.
- `on_duplicate`: `prompt` for interactive resolution.

---

# 7. Playlist Ingestion

## 7.1 Read configuration

Load `ytmusic_playlist_id` and optional YTMusic authentication.

## 7.2 Create client

Create a `ytmusicapi.YTMusic` client.

## 7.3 Retrieve complete playlist

The playlist ingestion layer requests the complete playlist according to the current ytmusicapi interface and processes returned items in order.

## 7.4 Track extraction

For normal entries, extract:

- `videoId`
- title
- artists
- album
- duration
- availability
- original playlist-item JSON

## 7.5 Unavailable entries

An item such as:

```json
{
  "videoId": null,
  "title": "Nuvvu Navvukuntu",
  "isAvailable": false
}
```

is not an ingestion-fatal error.

The item is preserved. The application stores the metadata that exists, keeps the permanent serial, and records an `error` state explaining that the entry currently has no usable source video ID.

No fake `videoId` is generated.

## 7.6 Existing entries

When the same usable playlist occurrence is ingested again:

- preserve its serial,
- preserve its historical status when applicable,
- refresh source fields as appropriate,
- never recycle serials.

## 7.7 New entries

Allocate the next never-used serial after the existing maximum.

## 7.8 Ingestion order

Initial serial assignment follows API return order. Processing of pending entries follows:

```sql
ORDER BY playlist_position ASC, serial_number ASC
LIMIT 1
```

---

# 8. Playlist Database — Current Schema

`playlist.db` answers: **which playlist occurrences exist and what state are they in?**

Current table:

```sql
CREATE TABLE playlist_entries (
    serial_number INTEGER PRIMARY KEY,
    playlist_position INTEGER NOT NULL,
    ytm_playlist_id TEXT,
    ytm_video_id TEXT,
    ytm_url TEXT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT,
    duration INTEGER,
    ytm_playlist_item_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'completed', 'duplicate', 'error')),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Indexes:

```sql
CREATE INDEX idx_playlist_status_position
ON playlist_entries(status, playlist_position, serial_number);

CREATE INDEX idx_playlist_video_id
ON playlist_entries(ytm_video_id);
```

## 8.1 Status meanings

### pending
Entry is ready to be processed.

### completed
Entry currently owns the retained song row/file.

### duplicate
Entry was processed and intentionally did not retain its own song because its ISRC duplicated an existing retained song and the operator chose to keep the previous song.

### error
The entry cannot currently be processed successfully, for example because the source is unavailable or an unrecoverable processing error occurred.

---

# 9. Songs Database — Current Schema

`songs.db` answers: **which playlist entries currently own retained songs, and what normalized/file/enrichment metadata belongs to those songs?**

Current table:

```sql
CREATE TABLE songs (
    serial_number INTEGER PRIMARY KEY,
    ytm_playlist_id TEXT,
    title TEXT NOT NULL,
    title_original TEXT,
    primary_artist TEXT,
    artist TEXT,
    artists_json TEXT,
    album TEXT,
    album_artist TEXT,
    isrc TEXT,
    track_number TEXT,
    disc_number TEXT,
    release_date TEXT,
    release_date_source TEXT,
    upload_date TEXT,
    upload_timestamp INTEGER,
    release_timestamp INTEGER,
    modified_date TEXT,
    modified_timestamp INTEGER,
    description TEXT,
    genre TEXT,
    composer TEXT,
    publisher TEXT,
    copyright TEXT,
    license TEXT,
    comment TEXT,
    language TEXT,
    bpm INTEGER,
    compilation INTEGER,
    encoder TEXT,
    duration INTEGER,
    source_duration INTEGER,
    source_ext TEXT,
    source_container TEXT,
    source_codec TEXT,
    source_format_id TEXT,
    source_format_note TEXT,
    source_bitrate INTEGER,
    source_sample_rate INTEGER,
    source_channels INTEGER,
    source_filesize INTEGER,
    source_filesize_approx INTEGER,
    source_language TEXT,
    source_video_id TEXT,
    source_webpage_url TEXT,
    source_original_url TEXT,
    source_display_id TEXT,
    source_webpage_url_basename TEXT,
    source_webpage_url_domain TEXT,
    source_extractor TEXT,
    source_extractor_key TEXT,
    source_channel TEXT,
    source_channel_id TEXT,
    source_channel_url TEXT,
    source_channel_follower_count INTEGER,
    source_channel_is_verified INTEGER,
    source_uploader TEXT,
    source_uploader_id TEXT,
    source_uploader_url TEXT,
    source_views INTEGER,
    source_location TEXT,
    source_availability TEXT,
    source_age_limit INTEGER,
    source_live_status TEXT,
    source_media_type TEXT,
    source_thumbnail TEXT,
    source_thumbnails_json TEXT,
    source_categories_json TEXT,
    source_tags_json TEXT,
    source_playlist TEXT,
    source_playlist_id TEXT,
    source_playlist_count INTEGER,
    source_playlist_index INTEGER,
    source_playlist_uploader TEXT,
    source_playlist_uploader_id TEXT,
    source_playlist_channel TEXT,
    source_playlist_channel_id TEXT,
    source_playlist_webpage_url TEXT,
    ytm_video_id TEXT,
    ytm_url TEXT,
    ytm_playlist_item_json TEXT,
    source_info_json TEXT NOT NULL,
    mp3_path TEXT NOT NULL,
    mp3_size INTEGER,
    mp3_sha256 TEXT,
    yt_video_id TEXT,
    yt_video_url TEXT,
    yt_video_title TEXT,
    yt_video_fulltitle TEXT,
    yt_video_alt_title TEXT,
    yt_video_channel TEXT,
    yt_video_channel_id TEXT,
    yt_video_uploader TEXT,
    yt_video_uploader_id TEXT,
    yt_video_upload_date TEXT,
    yt_video_timestamp INTEGER,
    yt_video_release_date TEXT,
    yt_video_release_timestamp INTEGER,
    yt_video_duration INTEGER,
    yt_video_views INTEGER,
    yt_video_likes INTEGER,
    yt_video_comments INTEGER,
    yt_video_thumbnail TEXT,
    yt_video_description TEXT,
    yt_video_categories_json TEXT,
    yt_video_tags_json TEXT,
    yt_video_extractor TEXT,
    yt_video_extractor_key TEXT,
    yt_video_info_json TEXT,
    yt_video_search_query TEXT,
    yt_video_search_result_index INTEGER,
    yt_video_search_results_fetched INTEGER,
    yt_video_match_method TEXT,
    artwork_source_url TEXT,
    artwork_width INTEGER,
    artwork_height INTEGER,
    artwork_path TEXT,
    artwork_provider TEXT,
    metadata_json_path TEXT,
    spotify_track_id TEXT,
    spotify_track_name TEXT,
    spotify_track_url TEXT,
    spotify_uri TEXT,
    spotify_artists_json TEXT,
    spotify_artist_ids_json TEXT,
    spotify_artist_urls_json TEXT,
    spotify_album_id TEXT,
    spotify_album_name TEXT,
    spotify_album_url TEXT,
    spotify_album_type TEXT,
    spotify_album_release_date TEXT,
    spotify_album_release_precision TEXT,
    spotify_album_total_tracks INTEGER,
    spotify_album_artwork_url TEXT,
    spotify_album_artwork_width INTEGER,
    spotify_album_artwork_height INTEGER,
    spotify_album_label TEXT,
    spotify_album_copyrights_json TEXT,
    spotify_duration_ms INTEGER,
    spotify_duration_seconds INTEGER,
    spotify_duration_delta_ms INTEGER,
    spotify_explicit INTEGER,
    spotify_popularity INTEGER,
    spotify_isrc TEXT,
    spotify_track_number INTEGER,
    spotify_disc_number INTEGER,
    spotify_search_query TEXT,
    spotify_search_result_index INTEGER,
    spotify_raw_json TEXT,
    spotify_album_raw_json TEXT,
    lyrics_status TEXT,
    lyrics_path TEXT,
    lrclib_id INTEGER,
    lrclib_track_name TEXT,
    lrclib_artist_name TEXT,
    lrclib_album_name TEXT,
    lrclib_duration INTEGER,
    lrclib_duration_delta_seconds REAL,
    lrclib_match_method TEXT,
    lrclib_raw_json TEXT,
    lyrics_embedded INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Indexes:

```sql
CREATE INDEX idx_songs_isrc ON songs(isrc) WHERE isrc IS NOT NULL;
CREATE INDEX idx_songs_yt_video_id ON songs(yt_video_id);
CREATE INDEX idx_songs_ytm_video_id ON songs(ytm_video_id);
```

---

# 10. Database Invariants

After every successful committed state:

1. A serial exists at most once in `playlist.db`.
2. A serial exists at most once in `songs.db`.
3. `completed` playlist entries have a matching `songs.db` row.
4. A completed row points to an existing valid final MP3.
5. `duplicate` playlist entries do not own a retained `songs.db` row.
6. `pending` entries normally do not own a retained `songs.db` row.
7. `error` entries are allowed without a retained song.
8. `songs.isrc` contains the canonical ISRC when one exists.
9. The ISRC index contains non-NULL values only.
10. Duplicate lookup never considers the current serial as an existing duplicate of itself.

---

# 11. State Machine

```text
pending
   |
   v
processing
   |
   +-----------------------------+
   |                             |
   v                             v
success                       failure
   |                             |
   v                             v
ISRC duplicate check           error
   |                             |
   +----------+----------+       |
              |          |       |
              v          v       |
            unique    duplicate  |
              |          |       |
              |      user choice |
              |       /      \   |
              |      v        v  |
              | keep_prev  keep_current
              |      |        |
              |      v        v
              |  duplicate  completed
              |                 |
              +-----------------+

Old completed entry + keep_current:
old serial -> pending
current serial -> completed
```

Error retry:

```text
error -> pending
```

---

# 12. Per-Entry Working Directory

For serial `004`:

```text
temp/004/
```

The directory is the complete temporary workspace for one processing attempt.

Expected acquisition artifacts:

```text
temp/004/
├── master.mp3
├── master.info.json
├── thumbnails / thumbnail variants
└── manifest/recovery metadata when applicable
```

Temporary final production output can be staged separately until validation and promotion.

No temporary artifact is considered a retained library file.

---

# 13. One Complete yt-dlp Acquisition

The downloader must obtain the source package in one initial acquisition operation.

Conceptual behavior:

```bash
yt-dlp \
  -x \
  --audio-format mp3 \
  --audio-quality 0 \
  --write-info-json \
  --write-thumbnail \
  --write-all-thumbnails \
  --convert-thumbnails jpg \
  -o "temp/{serial}/master.%(ext)s" \
  "{ytm_url}"
```

The exact command may adapt to the installed yt-dlp version, but these behaviors must remain:

- acquire source audio;
- write complete source info JSON;
- acquire thumbnails needed for artwork selection;
- do not use `--add-metadata`;
- use the YT Music source URL, not a general YouTube audio search.

---

# 14. Source Validation

Before enrichment:

- `master.mp3` exists.
- `master.info.json` exists.
- JSON parses successfully.
- MP3 is readable.
- MP3 duration can be obtained.
- At least one usable artwork source exists when artwork is required.

Failure behavior:

1. write descriptive error;
2. set playlist entry to `error`;
3. do not create a `songs.db` retained row;
4. preserve serial;
5. retain enough information for retry.

---

# 15. Metadata Normalization

The metadata pipeline has three conceptual layers.

## Layer A — Raw metadata

The exact `master.info.json`, YT Music playlist-item JSON, Spotify API JSON, YouTube selected-result JSON, and LRCLIB response are preserved in the sidecar.

## Layer B — Normalized application model

A structured normalized representation is used internally and persisted to `songs.db`.

## Layer C — MP3 export model

Only selected player-facing fields and important identifiers are mapped into ID3.

---

# 16. Final Metadata Source Precedence

## 16.1 Title

Primary: normalized YT Music/yt-dlp title.

Spotify matched track may overlay the final title when Spotify enrichment is enabled and matched.

## 16.2 Artist

Primary: normalized YT Music/yt-dlp artist information.

Spotify matched track may overlay artist names when matched.

## 16.3 Album

Primary: YT Music/yt-dlp album.

Spotify matched track may overlay album identity/name when matched.

## 16.4 Album artist

Spotify album artists may improve album-artist identity when matched; otherwise source metadata is used when available.

## 16.5 Release date

Use catalog/source release date rather than silently replacing it with upload date.

Spotify release date can enrich/overlay the music release date when a match is accepted.

## 16.6 Track/disc number

Spotify catalog track/disc values can enrich source metadata when matched.

Playlist serial is never used as album track number.

## 16.7 Publisher/label

Use source publisher when present; Spotify album label can fill/enrich when present.

## 16.8 Copyright

Use source copyright when present; Spotify album copyright data can enrich it when present.

## 16.9 Duration

The actual downloaded MP3 duration is authoritative for the song file.

Spotify duration is used only for candidate matching and retained as catalog metadata.

YouTube music-video duration is video metadata and does not replace song duration.

## 16.10 ISRC

Canonical precedence:

1. valid Spotify matched-track ISRC;
2. valid source/yt-dlp ISRC fallback;
3. missing if neither exists.

---

# 17. Spotify Integration — Detailed Plan

## 17.1 Authentication

Use Spotify Web API Client Credentials flow.

Credential priority:

1. environment variables when `use_env=true` and variables exist;
2. config values;
3. disabled/error behavior according to configuration.

The project does not download Spotify audio.

## 17.2 Search

Search query:

```text
{title} {album}
```

The request should identify tracks rather than albums/playlists.

## 17.3 Candidate selection

For each returned result in original order:

1. read Spotify track duration;
2. compare with actual downloaded audio duration;
3. accept the first track whose duration delta is within `duration_tolerance_seconds`.

No post-search scoring is used.

## 17.4 Spotify data imported

Track:

- Spotify track ID
- track name
- Spotify URL
- URI
- artists
- artist IDs
- artist URLs
- album ID/name/URL/type
- album release date/precision
- album total tracks
- track/disc number
- duration in milliseconds/seconds
- explicit flag
- popularity
- external IDs including ISRC

Album:

- album object
- album label
- copyrights
- all album image metadata

## 17.5 Spotify artwork

- select largest returned album image by dimensions/area;
- download exact bytes;
- validate image format/readability;
- preserve bytes unchanged;
- embed unchanged image as APIC;
- record URL, dimensions, MIME type, byte length and SHA-256 in sidecar.

No resampling is done to Spotify artwork.

---

# 18. ISRC — Detailed Plan

## 18.1 Canonicalization

Input examples may contain spaces or hyphens. Canonical representation is uppercase alphanumeric characters in the standard 12-character shape.

Invalid values become missing.

## 18.2 Storage

Canonical ISRC:

```text
songs.isrc
```

Spotify original source value:

```text
songs.spotify_isrc
```

## 18.3 MP3

Write canonical ISRC to:

```text
TSRC
```

and expose it as:

```text
TXXX:isrc
```

only when one exists.

## 18.4 Duplicate query

Only:

```sql
SELECT *
FROM songs
WHERE isrc = ?
LIMIT 1;
```

No fallback matching.

---

# 19. Duplicate Resolution — Transactional Safety

## 19.1 Keep previous

The current temporary work is disposable.

Order:

1. detect duplicate;
2. show current + existing metadata;
3. operator selects previous;
4. mark current playlist entry `duplicate`;
5. commit status;
6. clean current temp artifacts.

## 19.2 Keep current

Never destroy old retained artifacts before the replacement is valid.

Order:

1. detect duplicate;
2. operator selects current;
3. finish Spotify/YouTube/LRCLIB/artwork work;
4. build final MP3;
5. write tags;
6. write lyrics;
7. validate final MP3;
8. generate sidecar;
9. compute hashes;
10. stage replacement files;
11. transactionally replace old/current DB ownership;
12. commit;
13. remove old artifacts;
14. clean temporary workspace.

If a failure occurs before commit, the previous retained song should remain intact.

---

# 20. YouTube Music-Video Search

## 20.1 Query

```text
{title} {album} official video song
```

## 20.2 Filtering

For each result in returned order:

```text
lower(result.title)
```

If it contains `lyrics`, skip it.

Otherwise select immediately.

## 20.3 Selected fields

Main MP3 metadata only needs:

- YouTube video ID
- YouTube video URL
- YouTube video title

Detailed fields remain in JSON, including when available:

- channel
- channel ID
- uploader
- uploader ID
- upload date
- release date
- timestamp
- duration
- views
- likes/comments
- categories/tags
- thumbnail
- raw info JSON

## 20.4 No acceptable result

Set selected-video fields to null/absent and continue successfully.

---

# 21. LRCLIB — Detailed Plan

## 21.1 Allowed endpoint

Only:

```text
GET /api/get
```

is permitted.

The implementation must never call `/api/search`.

## 21.2 Inputs

Use current song metadata:

- track name/title
- artist
- album
- duration

## 21.3 Acceptance

Accept only when:

- response is structurally valid;
- synchronized lyrics are present;
- synchronized lyrics parse into valid timestamped lines.

Plain-only lyrics are rejected for the `.lrc` workflow.

## 21.4 Saved lyrics

Synced:

```text
<name>.lrc
```

and embedded as synchronized lyrics.

Unsynced:

- no `.lrc` file;
- song placed in `songs/no_synced_lyrics`;
- JSON records the lyric lookup/result status.

## 21.5 Lyrics embedding

The final MP3 receives:

- `SYLT` for synchronized timestamped lyrics;
- `USLT` compatibility representation containing lyric text.

The actual `.lrc` file preserves the timestamped external representation.

---

# 22. Artwork — Detailed Plan

## 22.1 Provider precedence

1. Spotify matched track artwork when enabled and valid.
2. YT Music/yt-dlp fallback artwork.

## 22.2 Spotify

Use the largest image returned by Spotify.

Preserve the bytes exactly.

## 22.3 YT Music fallback

The thumbnail problem addressed by the implementation is that generic YouTube thumbnails can be padded/widescreen while YT Music exposes square album-art images.

The fallback process:

1. collect all yt-dlp thumbnails;
2. inspect thumbnail dimensions/URLs;
3. optionally inspect YT Music OpenGraph image;
4. classify square candidates;
5. prefer valid square artwork;
6. use source provenance to break ties;
7. if fallback is not square and square normalization is enabled, center-crop to square;
8. correct EXIF orientation;
9. output normalized JPEG.

Spotify artwork does not go through this transformation stage.

## 22.4 MP3 embedding

Artwork is embedded as front cover `APIC`.

---

# 23. MP3 Metadata Contract

## 23.1 Standard ID3 frames

When available:

```text
TIT2  Title
TPE1  Track artist
TPE2  Album artist
TALB  Album
TDRC  Release date
TRCK  Track number
TPOS  Disc number
TCON  Genre
TCOM  Composer
TPUB  Publisher/label
TCOP  Copyright
TLAN  Language
TBPM  BPM
TCMP  Compilation
TENC  Encoder
TLEN  Actual duration in milliseconds
TSRC  Canonical ISRC
APIC  Front cover
SYLT  Synchronized lyrics
USLT  Lyrics text compatibility
```

Only fields with meaningful values are written, except fields explicitly required by the final validation contract.

## 23.2 TXXX

Keep TXXX concise. Durable application/catalog fields include:

- serial number
- playlist position
- YT Music source ID
- YouTube selected video ID/title
- Spotify track ID
- Spotify album ID
- Spotify ISRC
- canonical ISRC
- lyrics status
- artwork provider/basic properties

## 23.3 UFID

Use machine-readable identifiers for:

- YT Music source ID
- selected YouTube video ID
- Spotify track ID when available

## 23.4 WXXX

Use important URLs:

- YT Music source URL
- selected YouTube video URL
- Spotify track URL
- Spotify album URL when available

## 23.5 Intentionally excluded from main MP3 metadata

Do not embed:

- raw API JSON
- raw yt-dlp blobs
- long source descriptions
- age restrictions
- verbose channel details
- extractor internals
- downloader debug information
- giant thumbnail lists
- format-selection internals

Those go to JSON sidecar.

---

# 24. Sidecar JSON Contract

Every finalized MP3 must have a same-basename JSON.

Example:

```text
001_Urike_Urike_Artist.mp3
001_Urike_Urike_Artist.json
```

If synced:

```text
001_Urike_Urike_Artist.lrc
```

## 24.1 Recommended top-level sections

```json
{
  "schema_version": "...",
  "metadata_export_version": "...",
  "playlist": {},
  "song": {},
  "source": {},
  "spotify": {},
  "youtube_video": {},
  "lyrics": {},
  "artwork": {},
  "files": {},
  "duplicate": {},
  "timestamps": {}
}
```

## 24.2 Raw provenance

The sidecar can contain complete raw objects rather than trying to encode them into ID3.

This is where verbose source data belongs.

---

# 25. Filename Rules

Final filename:

```text
{serial:03d}_{safe_title}_{safe_artist}.mp3
```

Corresponding files:

```text
{same basename}.json
{same basename}.lrc    # only synced lyrics
```

Requirements:

- serial always present;
- Windows-invalid characters removed/replaced;
- no directory traversal;
- reserved Windows names protected;
- filename length bounded;
- readable title/artist preserved where possible;
- database identity never changes because of filename sanitization.

---

# 26. Finalization Order

The safe order is:

```text
1. Read playlist occurrence
2. Create/recover temporary workspace
3. Acquire source once with yt-dlp
4. Validate source artifacts
5. Normalize metadata
6. Attempt Spotify enrichment when enabled
7. Determine canonical ISRC
8. Check ISRC duplicate
9. Resolve duplicate decision if needed
10. Search selected YouTube music video
11. Fetch selected video metadata
12. Obtain accepted LRCLIB synced lyrics through /api/get only
13. Select artwork
14. Construct final MP3 staging path
15. Copy/source audio into staging output
16. Write standard ID3 tags with Mutagen
17. Write concise TXXX fields
18. Write UFID/WXXX identity/URL fields
19. Embed APIC artwork
20. Embed SYLT/USLT lyrics
21. Save
22. Reopen
23. Validate
24. Generate JSON sidecar
25. Hash final MP3
26. Stage MP3/LRC/JSON
27. Atomically promote final files
28. Commit songs.db + playlist.db state transactionally
29. Clean previous duplicate artifacts if applicable
30. Remove temp directory
31. Report result
```

Physical file replacement and DB transitions must be coordinated so the application does not destroy the previous retained song before the replacement is known to be valid.

---

# 27. Validation Contract

Validation occurs on the **fully tagged, fully embedded final MP3**, not on the raw `master.mp3`.

Checks should include:

## File

- exists;
- nonzero size;
- reopenable;
- valid MP3/audio stream;
- readable duration.

## Standard metadata

- title present;
- artist present;
- album present when expected;
- release date valid when present;
- track/disc valid when present;
- standard fields match normalized model.

## ISRC

- `TSRC` matches canonical ISRC when one is available;
- no fake `NULL` string is written.

## Important source/catalog identities

- YT Music ID matches normalized source;
- YouTube selected-video ID/URL match normalized selected result;
- Spotify ID/ISRC match normalized Spotify result when matched.

## Artwork

- APIC exists;
- image is decodable;
- correct provider/bytes/provenance when applicable.

## Lyrics

- synced status matches sidecar;
- SYLT exists for synced songs;
- USLT compatibility projection exists when enabled;
- `.lrc` exists only for synced songs.

## Sidecar

- same basename exists;
- valid JSON;
- references final MP3 path;
- contains file hash/size;
- contains source/catalog provenance.

---

# 28. Hashing

After all metadata, artwork and lyrics embedding are complete:

```text
SHA-256(final MP3 bytes)
```

Store:

```text
songs.mp3_size
songs.mp3_sha256
```

and sidecar JSON file information.

The hash covers the final fully-tagged MP3, not the original `master.mp3`.

---

# 29. Error Handling

## 29.1 Source unavailable

- preserve playlist occurrence;
- status `error`;
- descriptive message;
- no `songs.db` retained row;
- retry later.

## 29.2 yt-dlp failure

- do not mark completed;
- preserve serial;
- clean partial temporary artifacts;
- allow retry.

## 29.3 Spotify failure

Default behavior is nonfatal when `fail_on_error=false`:

- continue without Spotify enrichment;
- continue using source metadata/artwork.

When `fail_on_error=true`, Spotify failure may fail the song entry.

## 29.4 YouTube no match

Nonfatal:

- selected-video fields absent/null;
- song still completes.

## 29.5 LRCLIB no synced lyrics

Nonfatal:

- song completes;
- no `.lrc` file;
- placed in `songs/no_synced_lyrics`;
- sidecar records lookup/result.

## 29.6 Final validation failure

- do not promote final MP3;
- do not insert retained `songs.db` row;
- mark playlist `error`;
- preserve serial;
- clean or retain diagnostics according to recovery policy.

---

# 30. Recovery and Restart

The pipeline is designed to tolerate interruption.

On restart:

1. initialize/migrate databases;
2. inspect playlist state;
3. retry pending entries;
4. optionally retry error entries with `--retry-errors`;
5. detect stale temporary workspaces;
6. never interpret an incomplete `.tmp` file as a completed library file;
7. preserve permanent serials.

For duplicate replacement:

- if crash occurs before commit, previous retained row/file remains the safe fallback;
- if commit succeeds, post-commit cleanup removes old artifacts;
- orphan cleanup must never delete a file still referenced by a committed `songs.db` row.

---

# 31. CLI / Operational Commands

Current main options include:

```text
python main.py
python main.py --config config.json
python main.py --ingest-only
python main.py --no-ingest
python main.py --status
python main.py --doctor
python main.py --retry-errors
python main.py --check-invariants
python main.py --limit N
```

Typical workflow:

```powershell
python main.py --doctor
python main.py
```

Monitoring:

```powershell
python main.py --status
python main.py --check-invariants
```

Retry:

```powershell
python main.py --retry-errors
```

---

# 32. Logging

The application logs important state changes to `logs/phase1.log`.

Useful events:

- playlist ingestion summary;
- serial allocation/reuse;
- unavailable playlist entries;
- source acquisition start/end;
- Spotify match/no-match/error;
- ISRC detection;
- duplicate prompt and decision;
- YouTube search query and selection;
- LRCLIB request/result/status;
- artwork provider and size;
- final validation;
- hash;
- DB commit;
- cleanup.

Credentials/secrets must never be logged.

---

# 33. Security and Credential Handling

- Do not commit actual Spotify credentials.
- Prefer environment variables for credentials.
- `cookies.txt` is a user-local credential artifact and should remain ignored by version control.
- Do not print cookie contents.
- Do not put Spotify client secrets in sidecar JSON.
- Sidecar raw API records must exclude credential headers/tokens.
- Network requests should use configured timeouts.
- File paths are sanitized before final output.
- Temporary directories are scoped by serial number.

---

# 34. Module Responsibilities

## `main.py`

Application entry point and CLI.

Responsibilities:

- parse arguments;
- load config;
- initialize directories/databases;
- run doctor/status/invariant operations;
- start ingestion and processing;
- propagate top-level errors with appropriate exit code.

## `src/playlist_ingest.py`

Responsibilities:

- YTMusic client lifecycle;
- playlist retrieval;
- playlist-item normalization;
- unavailable-entry handling;
- permanent serial allocation/reuse;
- database ingestion.

## `src/downloader.py`

Responsibilities:

- build exact yt-dlp acquisition command;
- invoke yt-dlp;
- set runtime/network arguments;
- validate acquisition artifacts.

## `src/metadata.py`

Responsibilities:

- parse `info.json`;
- normalize fields;
- canonicalize ISRC;
- track/date/duration handling;
- convert raw source data to normalized metadata.

## `src/spotify.py`

Responsibilities:

- client credentials authentication;
- Spotify track search;
- returned-order/duration match;
- track/album retrieval;
- metadata overlay;
- largest artwork selection;
- raw data preservation.

## `src/duplicate_checker.py`

Responsibilities:

- ISRC-only duplicate lookup;
- no fallback heuristic.

## `src/youtube_finder.py`

Responsibilities:

- exact search-query construction;
- result retrieval;
- case-insensitive `lyrics` filtering;
- first acceptable selection;
- selected video metadata extraction.

## `src/lrclib.py`

Responsibilities:

- `/api/get` only;
- throttle/retry;
- synchronized lyric validation;
- LRCLIB result normalization.

## `src/artwork.py`

Responsibilities:

- YT Music thumbnail discovery;
- OpenGraph discovery;
- candidate scoring for square/fallback artwork only;
- YT Music artwork normalization;
- Spotify artwork download with byte preservation.

## `src/embedder.py`

Responsibilities:

- final ID3 creation/writing;
- standard frames;
- concise TXXX;
- UFID/WXXX;
- APIC artwork;
- SYLT/USLT lyrics.

## `src/validator.py`

Responsibilities:

- reopen final MP3;
- validate frames/IDs/artwork/lyrics;
- reject incomplete output before final DB commit.

## `src/sidecar.py`

Responsibilities:

- build same-basename detailed JSON;
- serialize all provenance safely;
- write/re-read sidecar.

## `src/hashing.py`

Responsibilities:

- SHA-256 calculation.

## `src/db_playlist.py`

Responsibilities:

- playlist schema/migrations;
- queries;
- serial integrity;
- status transitions;
- retry/reset.

## `src/db_songs.py`

Responsibilities:

- song schema/migrations;
- canonical ISRC storage/index;
- retained-row operations;
- file metadata persistence;
- song integrity checks.

## `src/pipeline.py`

Responsibilities:

- orchestration;
- per-entry lifecycle;
- duplicate resolution;
- temp workspace management;
- final path calculation;
- transaction coordination;
- overall run/status/invariant logic.

---

# 35. Detailed Data Flow for One Song

Assume:

```text
serial = 001
Title = Urike Urike
Album = Urike Urike (From "Hit 2")
Artist = M.M. Sreelekha, Sid Sriram, Ramya Behara
```

## Step A — Playlist

Create/reuse:

```text
playlist.db
001 | playlist_position=1 | YTM source ID | pending
```

## Step B — Download

Produce:

```text
temp/001/master.mp3
temp/001/master.info.json
thumbnail candidates
```

## Step C — Normalize

Extract title/artist/album/duration/source IDs.

## Step D — Spotify

Search:

```text
Urike Urike Urike Urike (From "Hit 2")
```

Select first duration match within tolerance.

Import Spotify catalog fields, IDs, ISRC, album artwork.

## Step E — Canonical ISRC

If Spotify returns valid ISRC:

```text
canonical_isrc = Spotify ISRC
```

Otherwise use valid source ISRC.

## Step F — Duplicate

Query:

```sql
songs.isrc = canonical_isrc
```

If no result: continue.

If result: prompt operator.

## Step G — YouTube

Search:

```text
Urike Urike Urike Urike (From "Hit 2") official video song
```

Skip results whose titles contain `lyrics`.

Take first remaining result.

## Step H — LRCLIB

Call only:

```text
GET /api/get
```

Use current title/artist/album/duration.

Accept synchronized result only.

## Step I — Artwork

Use largest Spotify artwork if valid; otherwise YT Music fallback artwork.

## Step J — MP3

Write concise standard ID3/custom identity fields, artwork, SYLT and USLT.

## Step K — JSON

Write detailed sidecar.

## Step L — Validate/hash/promote

Reopen → validate → SHA-256 → atomic promotion.

## Step M — Database

Insert `songs.db` row and mark playlist `completed` transactionally.

---

# 36. Sidecar vs MP3 Responsibility Matrix

| Data | MP3 | JSON |
|---|---:|---:|
| Title | Yes | Yes |
| Artist | Yes | Yes |
| Album | Yes | Yes |
| Album artist | Yes | Yes |
| Release date | Yes | Yes |
| Track/disc | Yes | Yes |
| Genre | Yes | Yes |
| Composer | Yes | Yes |
| Publisher/label | Yes | Yes |
| Copyright | Yes | Yes |
| Language | Yes | Yes |
| BPM | Yes | Yes |
| Compilation | Yes | Yes |
| Actual duration | Yes | Yes |
| Canonical ISRC | Yes | Yes |
| YT Music ID | Yes | Yes |
| YouTube video ID | Yes | Yes |
| YouTube video URL/title | Yes | Yes |
| Spotify track/album IDs | Yes | Yes |
| Spotify ISRC | Yes | Yes |
| Artwork | Yes | Yes (provenance) |
| Synced lyrics | Yes | Yes |
| `.lrc` path/status | Small metadata only | Yes |
| Source descriptions | No | Yes |
| Age-limit fields | No | Yes |
| Channel internals | No | Yes |
| Raw yt-dlp JSON | No | Yes |
| Raw YT Music JSON | No | Yes |
| Raw Spotify JSON | No | Yes |
| Raw YouTube JSON | No | Yes |
| Raw LRCLIB JSON | No | Yes |
| Search details | No | Yes |
| File hash | TXXX/sidecar optional; DB authoritative | Yes |

---

# 37. Duplicate Behavior Matrix

| Condition | Action |
|---|---|
| Valid ISRC, no matching song | Process normally |
| Valid ISRC, matching song | Prompt |
| Missing/invalid ISRC | Skip duplicate lookup; process normally |
| Duplicate + keep previous | Current becomes `duplicate`; retained song unchanged |
| Duplicate + keep current | New validated song replaces retained song; old playlist serial returns to `pending` |

---

# 38. Lyrics Output Matrix

| LRCLIB result | MP3 folder | `.lrc` | Embedded lyrics | JSON |
|---|---|---:|---:|---:|
| Valid synced lyrics | `synced_lyrics` | Yes | SYLT + USLT | Yes |
| Plain only | `no_synced_lyrics` | No | No synced lyric embedding | Yes |
| No result | `no_synced_lyrics` | No | No | Yes |
| API error with nonfatal setting | `no_synced_lyrics` | No | No | Yes |

---

# 39. Artwork Output Matrix

| Condition | Artwork source | Transformation |
|---|---|---|
| Spotify matched + valid album images | Spotify largest image | None; bytes preserved |
| Spotify unavailable + valid YT Music artwork | YT Music/yt-dlp | Candidate selection + possible square normalization |
| No usable artwork | None/controlled failure | MP3 completion behavior depends on validation/config |

---

# 40. Testing Strategy

The test suite should be deterministic and offline wherever possible by mocking network boundaries.

Minimum coverage areas:

1. normal playlist ingestion;
2. unavailable playlist entry (`videoId=None`);
3. serial preservation;
4. repeated playlist occurrences;
5. existing database migration;
6. yt-dlp command contract;
7. source validation;
8. metadata normalization;
9. Spotify duration matching;
10. Spotify returned-order selection;
11. Spotify largest artwork selection;
12. Spotify artwork byte-for-byte preservation;
13. Spotify failure nonfatal behavior;
14. ISRC normalization;
15. ISRC duplicate detection;
16. missing ISRC skip;
17. keep-previous duplicate behavior;
18. keep-current replacement safety;
19. YouTube exact query;
20. YouTube lyrics title filtering;
21. all-lyrics/no-result behavior;
22. LRCLIB `/api/get` only;
23. synchronized lyric parsing;
24. plain-only lyric rejection;
25. SYLT/USLT embedding;
26. synced/unsynced output directory rules;
27. complete sidecar creation;
28. metadata validation;
29. artwork validation;
30. hash calculation;
31. Windows filename safety;
32. transaction/recovery behavior;
33. invariant checks;
34. archive extraction/retest.

The latest prepared repository was regression-tested offline after extraction from the release archive.

---

# 41. Acceptance Criteria

The build is considered functionally complete when all of the following are true:

### Playlist

- Complete playlist can be ingested.
- Returned order is preserved.
- Every occurrence has a permanent serial.
- Unavailable entries do not crash the ingestion run.

### Download

- Usable entries download successfully through the YT Music source.
- Complete source JSON is retained.
- Artwork acquisition is available from the same source acquisition phase.

### Spotify

- Can be disabled.
- Correctly authenticates when enabled.
- Searches title + album.
- Uses first duration-matching result.
- Imports catalog identifiers/metadata.
- Extracts ISRC.
- Selects largest album artwork.
- Preserves Spotify artwork bytes unchanged.

### Duplicate

- ISRC-only.
- No fallback matching.
- Missing/invalid ISRC skips check.
- User controls duplicate decision.
- Keep-current is replacement-safe.

### YouTube

- Correct query format.
- Returned order preserved.
- `lyrics` filtering is case-insensitive.
- First acceptable result selected.
- Main MP3 gets YouTube video ID/URL/title.

### Lyrics

- Only `/api/get`.
- Only synchronized lyrics accepted.
- Synced `.lrc` exists with MP3.
- No `.lrc` for unsynced songs.
- Synced lyrics embedded into MP3.

### Metadata

- Main MP3 contains concise player-facing tags.
- Main MP3 contains important external identities.
- Raw/verbose data goes to JSON.
- Sidecar exists for every finalized MP3.

### Finalization

- Final MP3 is reopened and validated.
- Hash is over final MP3 bytes.
- File promotion is atomic.
- Database only reports completed after final artifact is valid.
- Temporary files are cleaned safely.

---

# 42. Known Design Decisions and Their Reasons

## Permanent serial rather than source ID

A playlist occurrence is an occurrence, not just a recording. Repeated source IDs therefore remain independent playlist entries.

## Separate playlist and songs databases

Playlist history/state and retained-library state answer different questions and should not be conflated.

## ISRC as sole duplicate identifier

The design intentionally avoids heuristic duplicate matching. This makes duplicate behavior deterministic and explicitly dependent on one catalog identifier.

## Spotify as enrichment, not audio source

Spotify provides catalog metadata/artwork/ISRC but does not provide the audio used by this downloader.

## YouTube music video is enrichment only

The selected YouTube video does not replace the YT Music audio source and its duration does not replace the audio duration.

## LRCLIB only `/api/get`

The current requirement deliberately prohibits broad `/api/search` discovery and limits lyrics retrieval to metadata-based lookup.

## Raw JSON in sidecar

ID3 is for player-facing metadata. The sidecar preserves complete provenance without polluting the MP3 with raw implementation data.

## Spotify artwork preserved unchanged

Avoids unnecessary transformations and retains the returned catalog artwork as supplied.

## YT Music fallback normalized separately

The YT Music ecosystem can expose padded/widescreen thumbnails, so fallback artwork requires candidate selection and optional square normalization.

---

# 43. Migration / Compatibility Requirements

When an older project database is opened:

- detect schema version;
- add missing columns/indexes safely;
- preserve existing rows and serials;
- migrate Spotify/source ISRC into canonical `songs.isrc` when possible;
- preserve existing retained MP3 paths;
- never recycle serials;
- do not silently discard previous sidecar associations.

When metadata export format changes, increment metadata export version in sidecars and keep migration/re-embedding tools compatible where practical.

---

# 44. Existing-MP3 Re-Embedding

`scripts/reembed_existing.py` exists for rebuilding metadata on already-produced MP3 files without requiring a fresh audio download when sufficient sidecar/database/source information exists.

Recommended safety flow:

```powershell
python scripts/reembed_existing.py --dry-run
python scripts/reembed_existing.py
```

The re-embed process must create a validated replacement before replacing an existing file.

---

# 45. Operational Workflow for a Windows User

## First installation

1. Install Python 3.11+.
2. Install FFmpeg/FFprobe and make sure they are discoverable.
3. Install a supported JavaScript runtime if yt-dlp requires it for the chosen extraction path.
4. Extract the project.
5. Configure `config.json`.
6. Put optional YT Music cookies in `cookies.txt` if needed.
7. Configure Spotify credentials if Spotify enrichment is enabled.

## Initial verification

```powershell
python main.py --doctor
```

## Start pipeline

```powershell
python main.py
```

## Inspect state

```powershell
python main.py --status
python main.py --check-invariants
```

## Retry errors

```powershell
python main.py --retry-errors
```

---

# 46. Example Final Output

For a song with synced lyrics:

```text
songs/
└── synced_lyrics/
    ├── 001_Urike_Urike_M.M._Sreelekha_Sid_Sriram_Ramya_Behara.mp3
    ├── 001_Urike_Urike_M.M._Sreelekha_Sid_Sriram_Ramya_Behara.lrc
    └── 001_Urike_Urike_M.M._Sreelekha_Sid_Sriram_Ramya_Behara.json
```

For a song without synced lyrics:

```text
songs/
└── no_synced_lyrics/
    ├── 002_Another_Song_Artist.mp3
    └── 002_Another_Song_Artist.json
```

The MP3 contains concise metadata/identities/cover/lyrics.

The JSON contains the complete detailed record.

---

# 47. Example Main MP3 Metadata

A representative enriched MP3 can expose:

```text
Title                         Urike Urike
Artist                        M.M. Sreelekha; Sid Sriram; Ramya Behara
Album                         Urike Urike (From "Hit 2")
Album Artist                  catalog/source value
Release Date                  2022-11-10
Genre                         Music
Composer                      M.M. Sreelekha
Publisher                     catalog/source label
Copyright                     catalog/source copyright
Duration                      actual downloaded audio duration
ISRC                          Spotify ISRC when available

YT Music ID                   S072HjMJZY0
YT Music URL                  https://music.youtube.com/watch?v=S072HjMJZY0

YouTube Video ID              A3Im3P0--aE
YouTube Video URL             https://www.youtube.com/watch?v=A3Im3P0--aE
YouTube Video Title           Urike Urike - Video Song ...

Spotify Track ID              <matched Spotify ID>
Spotify Album ID              <matched Spotify album ID>
Spotify Track URL             <matched Spotify URL>

Artwork                       embedded APIC
Lyrics                        synchronized SYLT + USLT
```

The exact values vary by the actual source/API response.

---

# 48. Example Detailed Sidecar Structure

Conceptually:

```json
{
  "schema_version": "...",
  "playlist": {
    "serial_number": 1,
    "playlist_position": 1,
    "ytm_playlist_id": "...",
    "ytm_video_id": "...",
    "ytm_url": "..."
  },
  "song": {
    "title": "...",
    "artist": "...",
    "artists": ["..."],
    "album": "...",
    "album_artist": "...",
    "release_date": "...",
    "duration": 276
  },
  "isrc": {
    "canonical": "...",
    "source": "spotify"
  },
  "spotify": {
    "matched": true,
    "track_id": "...",
    "album_id": "...",
    "isrc": "...",
    "raw_track": {},
    "raw_album": {},
    "artwork": {}
  },
  "youtube_video": {
    "selected": true,
    "video_id": "...",
    "url": "...",
    "title": "...",
    "raw_info": {}
  },
  "lyrics": {
    "status": "synced",
    "lrclib_id": 123,
    "lrc_path": "...",
    "synced_lyrics": "[00:...] ...",
    "raw_response": {}
  },
  "artwork": {
    "provider": "spotify",
    "source_url": "...",
    "width": 640,
    "height": 640,
    "sha256": "..."
  },
  "source": {
    "ytm_playlist_item": {},
    "yt_dlp_info": {}
  },
  "files": {
    "mp3_path": "...",
    "mp3_size": 12345678,
    "mp3_sha256": "...",
    "json_path": "...",
    "lrc_path": "..."
  }
}
```

The exact implementation may include additional fields from the current normalized model.

---

# 49. Full Current Module API Inventory

The current implementation contains these major callable/class responsibilities:

## Artwork module

- `ArtworkError`
- `ArtworkCandidate`
- square/area/provider utilities
- OpenGraph retrieval
- thumbnail candidate discovery
- artwork selection
- normalization
- Spotify artwork download

## Playlist DB

- initialization
- schema migration
- transactions
- max serial
- all rows
- serial lookup
- next pending
- insert/update
- retry errors
- counts
- integrity assertions

## Songs DB

- initialization
- schema migration
- transactions
- insert/update
- ISRC lookup
- serial lookup
- list/count
- integrity assertions

## Downloader

- yt-dlp command builder
- executable/runtime argument handling
- acquisition
- source artifact validation

## Duplicate checker

- ISRC duplicate model
- ISRC lookup

## Embedder

- text conversion
- TXXX
- WXXX
- UFID
- LRC parsing
- lyrics embedding
- core metadata embedding
- final MP3 embedding

## LRCLIB

- GET request
- throttle
- duration comparison
- synced lyric validation
- result normalization
- lookup

## Metadata

- load/dump source JSON
- string/list/date/integer/bool helpers
- ISRC normalization
- album/artist extraction
- URL parsing
- metadata merge
- canonical metadata normalization
- metadata field list

## Pipeline

- duplicate resolver
- project-path resolution
- final filename construction
- playlist record construction
- old serial cleanup
- one-entry processing
- run loop
- invariant checks
- DB coordinator commits

## Playlist ingestion

- artist extraction
- duration conversion
- album extraction
- URL construction
- playlist track extraction
- existing-entry matching
- playlist retrieval
- track retrieval
- ingestion

## Sidecar

- JSON-safe conversion
- sidecar construction
- write/read

## Spotify

- token retrieval
- HTTP request
- artist/album/image helpers
- track search
- metadata overlay

## YouTube finder

- exact search query
- JSON result parsing
- publication fields
- result selection

---

# 50. Quality Gates Before Release

Before calling a build final:

## Source quality

- compile all Python modules;
- no dead/duplicate path handling;
- no accidental `/api/search` usage;
- no accidental non-ISRC duplicate matcher;
- no accidental raw metadata dumping into MP3;
- no credential leakage.

## Tests

- entire test suite passes;
- extracted archive passes tests again;
- current DB schema initializes from empty;
- previous schema migrates;
- invariants pass.

## Manual sample inspection

At least one real MP3 should be inspected using `scripts/inspect_mp3.py` and an external tag viewer/player to confirm:

- title/artist/album display correctly;
- YT Music ID is present;
- YouTube video ID is present;
- Spotify IDs/ISRC are present when matched;
- artwork is correct;
- synchronized lyrics are present when LRCLIB returns them;
- no unwanted verbose fields clutter the main tag display.

## Live integration smoke test

Run on a real Windows machine with:

- valid YTMusic playlist/auth;
- FFmpeg/FFprobe;
- supported yt-dlp JS runtime;
- Spotify credentials if enabled;
- network access to LRCLIB.

---

# 51. Out of Scope

Unless explicitly added later, the following remain outside this phase:

- Demucs vocal separation
- Whisper transcription
- MMS/speech models
- instrumental extraction
- manual metadata editor UI
- audio hashing as duplicate identity
- fuzzy duplicate matching
- title/artist/duration fallback duplicate matching
- generalized YouTube candidate scoring
- automatic editorial judgment about officialness beyond the specified selection rule
- Spotify audio downloading
- LRCLIB `/api/search`
- lyrics other than accepted synchronized lyrics for `.lrc` output

---

# 52. Historical Changes From the Original Plan

The original specification established the permanent serial architecture, two databases, one yt-dlp acquisition, Mutagen-only final tag authority, ISRC duplicate identity, deterministic YouTube filtering, validation, hashing, and cleanup. fileciteturn0file0L15-L38

Subsequent requirements changed/enhanced the system as follows:

1. **Unavailable YTMusic entries:** `videoId=None` is now a recoverable playlist-entry condition rather than an ingestion-fatal exception.
2. **Spotify enrichment:** optional catalog enrichment was added.
3. **Spotify artwork:** largest Spotify album artwork is now preferred and preserved unchanged.
4. **LRCLIB:** only `/api/get` is used and synchronized lyrics are accepted.
5. **Lyrics output:** `.lrc` files are created only for synced lyrics; synced lyrics are also embedded in the MP3.
6. **Sidecar JSON:** every MP3 gets a same-basename detailed JSON record.
7. **MP3 metadata:** verbose source/API material was moved out of the main ID3 tag set; only concise player-facing metadata and important IDs/URLs remain.
8. **ISRC duplicate logic:** the duplicate identifier is restored as ISRC-only, with Spotify ISRC preferred and source ISRC as fallback.

The current build must be understood through the active rules in this document; the original plan is retained below as a historical appendix.

---

# 53. Implementation Principles for Future Changes

Any future modification should preserve these core contracts unless explicitly revising them:

- playlist serials are permanent;
- source identity and playlist occurrence identity remain separate;
- Spotify remains an optional enrichment layer;
- actual audio remains the YT Music source;
- YouTube video remains enrichment only;
- ISRC remains the sole duplicate identifier;
- no `/api/search` for LRCLIB;
- only synchronized lyrics create `.lrc` files;
- the main MP3 remains concise;
- the sidecar remains the detailed provenance store;
- final metadata authority remains Mutagen;
- final MP3 validation occurs before DB completion;
- hashes are computed on final bytes;
- replacement never destroys a previous valid retained song prematurely.

---

# 54. Final Release Checklist

```text
[ ] config.json reviewed
[ ] Spotify credentials configured or disabled intentionally
[ ] cookies configured if needed
[ ] FFmpeg available
[ ] FFprobe available
[ ] JS runtime available/recognized
[ ] python main.py --doctor passes
[ ] databases initialized/migrated
[ ] playlist ingestion tested
[ ] unavailable item handling tested
[ ] Spotify match tested
[ ] Spotify artwork tested
[ ] ISRC duplicate detection tested
[ ] YouTube search tested
[ ] LRCLIB /api/get-only behavior tested
[ ] synced lyrics embedded
[ ] synced .lrc written
[ ] unsynced song correctly routed
[ ] JSON sidecar created
[ ] final MP3 validation passes
[ ] SHA-256 stored
[ ] atomic finalization passes
[ ] DB invariants pass
[ ] extracted release archive passes tests
```

---

# Appendix A — Historical Original Specification

> The following is preserved verbatim from the original `pipeline.md`. It is historical because later user requirements introduced Spotify enrichment, LRCLIB, detailed JSON sidecars, updated artwork behavior, and restored ISRC duplicate detection. The appendix exists so the complete original plan remains available without information loss.

---

# PHASE 1 — YOUTUBE MUSIC PLAYLIST DOWNLOADER & ENRICHER

**Status:** Final project specification

**Purpose:** Implementation-ready specification for Phase 1 of the YouTube Music playlist downloader/enricher.

---

## 0. DOCUMENT PURPOSE

This document is the complete Phase 1 project plan.

It consolidates the final architecture and all decisions established during planning:

- `playlist.db` is the permanent playlist record.
- `songs.db` contains the currently retained/downloaded songs.
- Every playlist entry receives one permanent, unique serial number.
- The serial number never changes and is never reused.
- The same serial number is used in `songs.db` when that playlist entry owns the retained song.
- Playlist order is captured from the YTMusic API in its returned/default order.
- Processing happens one playlist entry at a time.
- The initial acquisition uses one complete `yt-dlp` command to obtain the audio, complete `info.json`, and artwork.
- The initial `yt-dlp` command does **not** use `--add-metadata`.
- Python/Mutagen is the single authority responsible for final ID3 metadata and artwork embedding.
- ISRC is the only duplicate-detection key.
- Missing ISRC is stored as `NULL` and does not trigger duplicate detection.
- Duplicate handling never removes a playlist entry from `playlist.db`.
- When a duplicate is detected, the user chooses whether to keep the previous retained song or the current downloaded song.
- YouTube video discovery uses exactly the query `{title} {album_name} official video song`.
- YouTube results are used in returned order.
- Any result whose title contains the word `lyrics` is skipped, case-insensitively.
- The first remaining result is selected immediately.
- There is no YouTube result scoring, ranking, confidence system, or manual weighting.
- The final MP3 contains rich metadata, artwork, source identity, and selected YouTube music-video metadata.
- The final MP3 is validated before it is committed to `songs.db`.
- The final MP3 receives a SHA-256 hash after all metadata and artwork have been written.
- Temporary files are removed only after successful finalization.
- Lyrics, Demucs, Whisper, MMS, vocal separation, instrumental extraction, and manual metadata editing are outside Phase 1.

This document is intentionally detailed so that the final implementation can be built directly from it without redesigning the architecture during coding.

---

# 1. PROJECT OVERVIEW

## 1.1 Objective

Build a standalone automated pipeline that takes one YouTube Music playlist and produces a local library of richly tagged MP3 files while maintaining a permanent record of every playlist entry.

The project is not simply an audio downloader. It is a playlist ingestion, identity, metadata, duplicate-management, video-enrichment, and MP3 finalization system.

The complete lifecycle is:

```text
YouTube Music Playlist
        |
        v
YTMusic API ingestion
        |
        v
Preserve returned playlist order
        |
        v
Assign permanent serial numbers
        |
        v
playlist.db
        |
        v
Select next pending entry
        |
        v
ONE complete yt-dlp acquisition
        |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
     master.mp3       master.info.json      master.jpg
        |                   |                   |
        +-------------------+-------------------+
                            |
                            v
                  Source validation
                            |
                            v
                  Metadata extraction
                            |
                            v
                    Metadata normalization
                            |
                            v
                       Extract ISRC
                            |
                            v
                    Search songs.db by ISRC
                            |
                 +----------+----------+
                 |                     |
                 v                     v
             no match              duplicate
                 |                     |
                 |                Ask user:
                 |              previous/current
                 |                     |
                 +----------+----------+
                            |
                            v
                 YouTube video search
                            |
                            v
        {title} {album_name} official video song
                            |
                            v
                Skip titles containing lyrics
                            |
                            v
                First remaining result
                            |
                            v
                  Retrieve video metadata
                            |
                            v
                 Use already-downloaded artwork
                            |
                            v
                    Build final MP3
                            |
                            v
                Mutagen writes ALL final tags
                            |
                            v
                     Validate MP3
                            |
                            v
                    Calculate SHA-256
                            |
                            v
                   Atomic final rename
                            |
                            v
                       songs.db
                            |
                            v
                playlist.db -> completed
                            |
                            v
                       Cleanup temp
                            |
                            v
                   Process next pending
```

---

# 2. SCOPE

## 2.1 Phase 1 INCLUDES

- YouTube Music playlist ingestion through `ytmusicapi`.
- Preservation of playlist ordering.
- Permanent serial assignment.
- Two SQLite databases.
- Pending/completed/duplicate/error processing states.
- Direct download of the selected YTMusic source audio.
- Detailed source metadata acquisition using `yt-dlp` `info.json`.
- Artwork acquisition during the same initial `yt-dlp` run.
- ISRC extraction and normalization.
- ISRC-only duplicate detection.
- User-controlled duplicate resolution.
- YouTube official music-video search.
- Simple result filtering based only on the presence of `lyrics` in the result title.
- Selection of the first acceptable result.
- Final metadata normalization.
- Final ID3 tag writing with Mutagen.
- Artwork embedding with Mutagen.
- YouTube metadata embedding using custom ID3 `TXXX` frames.
- Final MP3 validation.
- SHA-256 file hashing.
- SQLite state tracking.
- Temporary working-directory cleanup.
- Recovery from errors through status tracking.

## 2.2 Phase 1 EXCLUDES

- Lyrics retrieval.
- Lyrics embedding.
- Demucs processing.
- Whisper transcription.
- MMS or other speech/audio models.
- Vocal/instrumental separation.
- Manual metadata editing UI.
- Fuzzy duplicate matching.
- Title/artist/duration duplicate matching.
- YouTube candidate scoring.
- YouTube candidate ranking.
- YouTube confidence scoring.
- Automatic editorial judgment about which video is "most official" beyond the specified search rule.

---

# 3. CORE DESIGN PRINCIPLES

## 3.1 Playlist Entry Identity

A playlist entry is a specific occurrence inside the playlist.

Its permanent identity is the serial number.

Example:

```text
001 -> Song A
002 -> Song B
003 -> Song A
```

`001` and `003` are two different playlist entries.

They may refer to the same recording, but they remain different playlist identities.

## 3.2 Serial Number Rules

The serial number:

1. Is assigned once.
2. Is assigned in the order returned by the playlist ingestion process.
3. Is never reused.
4. Is never changed.
5. Is never deleted from `playlist.db`.
6. Is not replaced by ISRC.
7. Is not replaced by YTM video ID.
8. Is used in `songs.db` when the playlist entry owns the current retained song.
9. Is used in the final MP3 filename.
10. Is used when linking physical files back to playlist entries.

## 3.3 Playlist Database vs Song Database

`playlist.db` answers:

> What entries exist in my playlist, and what is their processing state?

`songs.db` answers:

> Which playlist entries currently have retained downloaded songs, and what are the metadata and file details of those retained songs?

They are deliberately separate.

## 3.4 Duplicate Identity

Only ISRC is a duplicate key.

If ISRC is missing:

```text
isrc = NULL
```

No other duplicate matching is attempted.

## 3.5 Final Metadata Authority

`yt-dlp` obtains source material and source metadata.

`yt-dlp` does **not** write the final MP3 metadata.

Mutagen is the single authority for final ID3 metadata.

This prevents competing metadata writers.

---

# 4. SYSTEM ARCHITECTURE

```text
                       +----------------------+
                       | YouTube Music        |
                       | Playlist             |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | YTMusic API           |
                       | Playlist ingestion    |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | playlist.db           |
                       | Permanent serials     |
                       | Status                |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | Processing Queue      |
                       | Next pending serial   |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | yt-dlp                |
                       | ONE initial command   |
                       +----------+-----------+
                                  |
                   +--------------+--------------+
                   |              |              |
                   v              v              v
              master.mp3    master.info.json  master.jpg
                   |              |              |
                   +--------------+--------------+
                                  |
                                  v
                       +----------------------+
                       | Metadata Normalizer   |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | ISRC Duplicate Check |
                       | songs.db              |
                       +----------+-----------+
                                  |
                         +--------+--------+
                         |                 |
                         v                 v
                       unique          duplicate
                         |                 |
                         |            user decision
                         |                 |
                         +--------+--------+
                                  |
                                  v
                       +----------------------+
                       | YouTube Search       |
                       | title + album +      |
                       | official video song  |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | First result whose  |
                       | title lacks lyrics   |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | Metadata / Artwork   |
                       | preparation          |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | Mutagen              |
                       | Final ID3 writer     |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | Final MP3 validation |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | SHA-256              |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | Atomic finalization  |
                       +----------+-----------+
                                  |
                         +--------+--------+
                         |                 |
                         v                 v
                    songs.db         playlist.db
                                     status=completed
```

---

# 5. PROJECT DIRECTORY STRUCTURE

```text
phase1_project/
│
├── main.py                         # Application entry point
├── config.json                     # User configuration
├── cookies.txt                     # Optional YouTube cookies
├── requirements.txt                # Python dependencies
├── README.md                       # Project documentation
│
├── src/
│   ├── __init__.py
│   ├── db_playlist.py              # playlist.db schema and helpers
│   ├── db_songs.py                 # songs.db schema and helpers
│   ├── playlist_ingest.py          # YTM playlist ingestion
│   ├── downloader.py               # yt-dlp acquisition
│   ├── metadata.py                 # info.json extraction/normalization
│   ├── duplicate_checker.py        # ISRC-only duplicate logic
│   ├── youtube_finder.py           # simple YouTube search/filter
│   ├── embedder.py                 # Mutagen ID3 writer
│   ├── validator.py                # final MP3 validation
│   ├── hashing.py                  # SHA-256 calculation
│   └── pipeline.py                 # end-to-end orchestration
│
├── songs/
│   └── original/                   # Retained final MP3 files
│
├── temp/                            # Per-entry temporary working folders
│
└── db/
    ├── playlist.db
    └── songs.db
```

---

# 6. CONFIGURATION

Suggested `config.json`:

```json
{
    "ytmusic_playlist_id": "YOUR_PLAYLIST_ID",

    "paths": {
        "songs": "songs/original",
        "temp": "temp",
        "database": "db"
    },

    "download": {
        "audio_format": "mp3",
        "audio_quality": "0",
        "write_info_json": true,
        "write_thumbnail": true,
        "convert_thumbnail": "jpg"
    },

    "youtube_video_search": {
        "results_to_fetch": 10,
        "skip_title_keyword": "lyrics"
    },

    "retry": {
        "max_attempts": 3
    }
}
```

Configuration values must not change the architectural rules.

In particular:

- duplicate matching remains ISRC-only;
- YouTube result scoring remains disabled;
- `lyrics` remains the only search-result title exclusion keyword defined by Phase 1;
- final ID3 writing remains Mutagen-only.

---

# 7. REQUIRED SOFTWARE

The implementation requires:

```text
Python
ytmusicapi
yt-dlp
mutagen
requests
FFmpeg
FFprobe
```

The runtime should also include whatever JavaScript-runtime support is required by the installed `yt-dlp` version for current YouTube extraction.

Dependency versions should be pinned in `requirements.txt` once implementation begins.

Example structure:

```text
yt...==...
yt-dlp==...
mutagen==...
requests==...
```

The exact versions should be selected at implementation time and tested together rather than being casually mixed.

---

# 8. DATABASE SCHEMA — `playlist.db`

## 8.1 Table

```sql
CREATE TABLE IF NOT EXISTS playlist_entries (
    serial_number INTEGER PRIMARY KEY,

    playlist_position INTEGER NOT NULL,

    ytm_video_id TEXT NOT NULL,
    ytm_url TEXT NOT NULL,

    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    duration INTEGER,

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            status IN (
                'pending',
                'completed',
                'duplicate',
                'error'
            )
        ),

    error_message TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 8.2 Why `ytm_video_id` is not UNIQUE

The same YTMusic track can appear more than once in a playlist.

Example:

```text
001 | Song A
002 | Song B
003 | Song A
```

Both `001` and `003` must survive as separate playlist entries.

Therefore:

```text
ytm_video_id -> not the permanent identity
serial_number -> permanent identity
```

## 8.3 `playlist_position`

`playlist_position` records the position returned by the playlist ingestion.

It is deliberately different from `serial_number`.

The serial is permanent.

The position describes playlist order.

This allows the project to preserve identity while still recording ordering information.

---

# 9. DATABASE SCHEMA — `songs.db`

## 9.1 Table

```sql
CREATE TABLE IF NOT EXISTS songs (
    serial_number INTEGER PRIMARY KEY,

    -- Core song metadata
    title TEXT NOT NULL,
    title_original TEXT,

    primary_artist TEXT,
    artist TEXT,
    artists_json TEXT,
    album TEXT,
    album_artist TEXT,

    -- Dates
    release_date TEXT,
    release_date_source TEXT,
    upload_date TEXT,

    -- Music identifiers
    isrc TEXT,
    isrc_source TEXT,

    -- Audio information
    duration INTEGER,
    source_duration INTEGER,
    source_codec TEXT,
    source_bitrate INTEGER,
    source_sample_rate INTEGER,
    source_channels INTEGER,

    -- Original YouTube Music source
    ytm_video_id TEXT,
    ytm_url TEXT,

    -- Final retained file
    mp3_path TEXT NOT NULL,
    mp3_size INTEGER,
    mp3_sha256 TEXT,

    -- Selected YouTube music video
    yt_video_id TEXT,
    yt_video_url TEXT,
    yt_video_title TEXT,
    yt_video_channel TEXT,
    yt_video_channel_id TEXT,
    yt_video_views INTEGER,
    yt_video_published_at TEXT,

    -- Search method
    yt_video_match_method TEXT,

    -- Working/source artwork path when retained in metadata
    artwork_path TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 9.2 ISRC Index

```sql
CREATE INDEX IF NOT EXISTS idx_songs_isrc
ON songs(isrc)
WHERE isrc IS NOT NULL;
```

Only non-NULL ISRC values are indexed for duplicate detection.

---

# 10. DATABASE INVARIANTS

The implementation must maintain these rules at all times after a successful commit.

## 10.1 Serial uniqueness

A serial appears at most once in `playlist.db`.

A serial appears at most once in `songs.db`.

## 10.2 Completed relationship

If:

```text
playlist.db.status = completed
```

then there must be:

```text
songs.db.serial_number = same serial
```

and the referenced MP3 must exist and be valid.

## 10.3 Duplicate relationship

If:

```text
playlist.db.status = duplicate
```

then that playlist entry does not own a retained song row in `songs.db`.

## 10.4 Pending relationship

If:

```text
playlist.db.status = pending
```

then it should not currently have a retained `songs.db` row for that serial.

## 10.5 Error relationship

If:

```text
playlist.db.status = error
```

there is no requirement for a retained `songs.db` row for that serial.

---

# 11. STATUS STATE MACHINE

The basic state machine is:

```text
                 +-----------+
                 |  pending  |
                 +-----+-----+
                       |
                 start processing
                       |
                       v
               download/process
                       |
          +------------+-------------+
          |                          |
          v                          v
       success                    failure
          |                          |
          v                          v
     duplicate check              error
          |                          |
    +-----+------+                   |
    |            |                   |
    v            v                   |
  unique      duplicate              |
    |            |                   |
    |        user decision           |
    |         /       \              |
    |        v         v             |
    |   previous     current         |
    |      |           |             |
    |      v           v             |
    |  duplicate   completed         |
    |                  |             |
    v                  |             |
 completed <-----------+-------------+
```

Additional transition:

```text
old completed entry
       |
 current duplicate chooses "keep current"
       |
       v
old entry -> pending
current entry -> completed
```

And retry:

```text
error -> pending
```

---

# 12. STEP 1 — PLAYLIST INGESTION

## 12.1 Read configuration

Read:

```text
yt...music_playlist_id
```

from `config.json`.

## 12.2 Initialize YTMusic

Create the `ytmusicapi.YTMusic` client.

Cookies/authentication may be supplied according to the local configuration if required by the environment.

## 12.3 Retrieve playlist

Retrieve the complete playlist using the YTMusic API.

The project must preserve the order returned by the API.

Do not sort alphabetically.

Do not sort by artist.

Do not sort by duration.

Do not sort by popularity.

Do not sort by ISRC.

The playlist order is authoritative for initial serial assignment.

## 12.4 Extract entry fields

For each returned track, extract at minimum:

```text
video_id
song title
artist(s)
duration
```

Construct:

```text
https://music.youtube.com/watch?v={video_id}
```

## 12.5 Assign serials

Assign serial numbers sequentially in the ingestion order.

Example:

```text
API order:
1. Song A
2. Song B
3. Song C
4. Song D

serials:
001 -> Song A
002 -> Song B
003 -> Song C
004 -> Song D
```

The serial is stored as an integer in SQLite. Zero-padding is a filename/display convention, not a numeric database requirement.

## 12.6 Initial status

New entries receive:

```text
status = pending
```

## 12.7 Existing database behavior

When the application is restarted, existing playlist entries must not be assigned new serials.

Existing serials remain unchanged.

New playlist entries can receive new serials according to the project's append-only serial-allocation policy.

The implementation must never recycle a previously used serial.

## 12.8 Ingestion summary

Print a summary such as:

```text
Playlist ingestion complete.

Total playlist entries: 120
New entries:            14
Existing entries:       106
Pending entries:        12
Completed entries:      91
Duplicate entries:      2
Error entries:          1
```

---

# 13. STEP 2 — SELECT NEXT PENDING ENTRY

Query `playlist.db` for the next entry where:

```text
status = pending
```

Process in playlist order.

Conceptually:

```sql
SELECT *
FROM playlist_entries
WHERE status = 'pending'
ORDER BY playlist_position ASC, serial_number ASC
LIMIT 1;
```

The serial returned becomes the active processing identity.

Example:

```text
003 | Song C | pending
```

The processing directory becomes:

```text
temp/003/
```

---

# 14. STEP 3 — CREATE WORKING DIRECTORY

Create:

```text
temp/{serial_number}/
```

Example:

```text
temp/003/
```

Everything generated for the current processing attempt belongs inside this directory until finalization.

Expected temporary files after acquisition:

```text
temp/003/
├── master.mp3
├── master.info.json
└── master.jpg
```

Additional yt-dlp/FFmpeg temporary files may exist during execution but should be cleaned after successful completion or failure handling.

---

# 15. STEP 4 — ONE COMPLETE YT-DLP ACQUISITION

This step intentionally acquires everything needed from the YTMusic source in one `yt-dlp` operation.

The command is conceptually:

```bash
yt-dlp \
    -x \
    --audio-format mp3 \
    --audio-quality 0 \
    --write-info-json \
    --write-thumbnail \
    --convert-thumbnails jpg \
    -o "temp/{serial_number}/master.%(ext)s" \
    "{ytm_url}"
```

The exact command-line details may be adjusted during implementation to match the installed `yt-dlp`/FFmpeg environment, but the behavior must remain the same.

## 15.1 Acquisition requirements

The single initial command must obtain:

### A. Audio

The exact selected YTMusic source audio.

### B. Complete source metadata

`master.info.json` containing the complete metadata returned by yt-dlp.

### C. Artwork

The highest-quality available thumbnail/artwork selected by yt-dlp from the source.

## 15.2 No general YouTube audio search

The audio is not found by searching general YouTube.

The source audio URL is the stored YTMusic URL belonging to the selected playlist entry.

## 15.3 No `--add-metadata`

Do **not** use:

```text
--add-metadata
```

The initial yt-dlp output is an acquisition artifact, not the final tagged library file.

## 15.4 Why there is no `--add-metadata`

The project intentionally has one final metadata authority:

```text
yt-dlp -> acquisition
Mutagen -> final MP3 metadata
```

This avoids having yt-dlp write one version of tags and Mutagen later overwrite another version.

---

# 16. EXPECTED INITIAL ACQUISITION RESULT

After a successful acquisition:

```text
temp/003/
├── master.mp3
├── master.info.json
└── master.jpg
```

## `master.mp3`

Contains the acquired audio.

It is not yet considered the final library MP3.

## `master.info.json`

Contains the source metadata.

It is parsed by Python.

## `master.jpg`

Contains the acquired artwork.

It is used later by Mutagen.

No second artwork download is performed.

---

# 17. STEP 5 — SOURCE ACQUISITION VALIDATION

Before proceeding, validate the source package.

## 17.1 Required checks

- `master.mp3` exists.
- `master.info.json` exists.
- `master.info.json` is valid JSON.
- `master.mp3` can be opened/read.
- Audio duration can be obtained.
- `master.jpg` exists when the source supplied usable artwork.
- `master.jpg` can be decoded as an image.

## 17.2 Failure

If a required acquisition item is invalid:

1. record the error;
2. set the playlist entry to `error`;
3. do not insert a `songs.db` row;
4. preserve the serial;
5. allow later retry by moving the entry back to `pending`.

---

# 18. STEP 6 — READ `master.info.json`

Parse the complete JSON object.

Do not throw away the source information before the normalized metadata has been built.

The parser should be defensive because individual fields can be absent or `null`.

Important fields to inspect include:

```text
title
artist
artists
album
album_artist
release_date
upload_date
duration
isrc
description
uploader
channel
channel_id
view_count
thumbnails
codec / format data
abr / bitrate
asr / sample rate
channels
```

The exact names/availability depend on the returned yt-dlp metadata.

---

# 19. STEP 7 — METADATA LAYERS

The system should conceptually maintain three metadata layers.

## Layer A — Raw source metadata

Exactly what is supplied by `master.info.json`.

## Layer B — Normalized application metadata

Cleaned fields that are suitable for databases and final tagging.

Examples:

```text
normalized_title
normalized_artist
normalized_album
normalized_isrc
normalized_release_date
```

## Layer C — Final MP3 metadata

The exact ID3 frames written by Mutagen.

This separation makes the system easier to debug.

---

# 20. STEP 8 — CORE SONG METADATA

Extract, where available:

```text
title
title_original
primary_artist
artist
artists_json
album
album_artist
```

## 20.1 Title

`title` is the cleaned display title.

`title_original` preserves the original source title when useful.

## 20.2 Artist

`artist` is the display string written to the main artist field.

`artists_json` can preserve multiple artist contributors without flattening information unnecessarily.

Example:

```json
[
  "Artist A",
  "Artist B"
]
```

## 20.3 Album

Store the album exactly when supplied.

If unavailable:

```text
album = NULL
```

## 20.4 Album Artist

Store album artist separately from track artist when available.

---

# 21. STEP 9 — DATE METADATA

Store:

```text
release_date
release_date_source
upload_date
```

Do not silently treat upload date as release date.

If a real release date is unavailable:

```text
release_date = NULL
```

The source upload date remains separately available as `upload_date`.

---

# 22. STEP 10 — ISRC EXTRACTION

ISRC is extracted from the structured metadata when available.

The application may normalize the representation, for example by trimming whitespace and normalizing case.

If no ISRC is available:

```text
isrc = NULL
isrc_source = NULL
```

Do not invent one.

Do not infer one from unrelated metadata.

Do not generate an internal pseudo-ISRC.

---

# 23. ISRC-ONLY DUPLICATE RULE

This is a locked design rule.

The duplicate checker must only do:

```text
current.isrc != NULL
        |
        v
find songs.db where songs.isrc == current.isrc
```

No other duplicate heuristic is permitted.

Do NOT duplicate-match using:

- title;
- artist;
- album;
- duration;
- YTM video ID;
- YouTube video ID;
- filename;
- audio hash;
- fuzzy title similarity;
- normalized artist/title combinations.

If `isrc = NULL`, the song is simply treated as having no ISRC-based duplicate match.

---

# 24. STEP 11 — DUPLICATE SEARCH

Example current entry:

```text
Serial: 004
Title: Song A
Artist: Artist A
ISRC: USABC1234567
```

Query:

```sql
SELECT *
FROM songs
WHERE isrc = ?
LIMIT 1;
```

If there is no row:

```text
unique -> continue
```

If there is a row:

```text
duplicate -> ask user
```

If the current ISRC is `NULL`:

```text
no duplicate check
```

---

# 25. STEP 12 — DUPLICATE USER DECISION

When a duplicate exists, show both entries clearly.

Example:

```text
DUPLICATE DETECTED

CURRENT ENTRY
Serial: 004
Title: Song A
Artist: Artist A
Album: Album X
ISRC: USABC1234567

EXISTING RETAINED ENTRY
Serial: 001
Title: Song A
Artist: Artist A
Album: Album X
ISRC: USABC1234567

Choose:

1. Keep previous
2. Keep current
```

No automatic winner is chosen.

---

# 26. DUPLICATE OPTION 1 — KEEP PREVIOUS

User selects:

```text
1
```

Actions:

1. Do not modify the previous retained song.
2. Do not delete the previous MP3.
3. Do not modify its `songs.db` row.
4. Delete the current temporary acquisition:
   - `master.mp3`;
   - `master.info.json`;
   - `master.jpg`;
   - any other temporary files.
5. Do not create a current `songs.db` row.
6. Set the current playlist entry to:

```text
status = duplicate
```

Example:

```text
playlist.db

001 | Song A | completed
004 | Song A | duplicate
```

`songs.db`:

```text
001 | Song A
```

Serial `004` remains permanently present in `playlist.db`.

---

# 27. DUPLICATE OPTION 2 — KEEP CURRENT

User selects:

```text
2
```

The current playlist entry becomes the retained song.

Actions:

1. Identify the previous `songs.db` row.
2. Read its `mp3_path`.
3. Delete the previous physical MP3.
4. Delete the previous row from `songs.db`.
5. Continue processing the current temporary acquisition.
6. Search YouTube for the current entry.
7. Build the current final MP3.
8. Validate it.
9. Insert current serial into `songs.db`.
10. Set current playlist entry to `completed`.
11. Set previous playlist entry to `pending`.

Example before:

```text
playlist.db

001 | Song A | completed
004 | Song A | pending
```

`songs.db`:

```text
001 | Song A
```

After choosing current:

```text
playlist.db

001 | Song A | pending
004 | Song A | completed
```

`songs.db`:

```text
004 | Song A
```

The old playlist entry `001` remains permanently assigned to serial `001`.

---

# 28. IMPORTANT DUPLICATE BEHAVIOR

A duplicate decision changes the retained song record, not playlist identity.

The system never does:

```text
rename serial 001 to 004
```

It instead does:

```text
remove retained song 001
retain playlist entry 001 as pending
retain song 004
```

This preserves the playlist history/identity while allowing the currently retained recording to move to the playlist entry chosen by the user.

---

# 29. STEP 13 — YOUTUBE OFFICIAL MUSIC VIDEO SEARCH

After the song has been acquired and duplicate handling has been resolved, perform the YouTube search.

The exact search string is:

```text
{title} {album_name} official video song
```

Use the normalized/current song title and album name being used for enrichment.

If the album is missing, the implementation should follow the exact established query construction rules used by the application rather than inventing a new search strategy.

---

# 30. NO SEARCH SCORING

The video finder must NOT:

- calculate a candidate score;
- compare view counts;
- compare durations;
- compare channels;
- calculate title similarity;
- calculate artist similarity;
- calculate confidence;
- rank candidate videos after retrieval;
- choose the most viewed result;
- choose the closest duration result.

The returned order is authoritative for this Phase 1 selection method.

---

# 31. STEP 14 — YOUTUBE RESULT FILTERING

Retrieve the search results in their returned order.

For each result:

1. Read its title.
2. Convert the title to a case-insensitive comparison form.
3. If the title contains the word:

```text
lyrics
```

skip that result.

4. Otherwise select it immediately.

Example:

```text
1. Song Name - Lyrics Video
2. Song Name - Official Video
3. Song Name - Live Performance
```

Result 1:

```text
lyrics -> skip
```

Result 2:

```text
no lyrics -> select immediately
```

Result 3 is never considered after selection.

---

# 32. NO ACCEPTABLE YOUTUBE RESULT

If all returned results contain `lyrics`, then no acceptable video is selected.

Store:

```text
yt_video_id = NULL
yt_video_url = NULL
yt_video_title = NULL
yt_video_channel = NULL
yt_video_channel_id = NULL
yt_video_views = NULL
yt_video_published_at = NULL
yt_video_match_method = NULL
```

The song can still be successfully completed.

Failure to find an acceptable video is **not** a failure of the song download.

---

# 33. STEP 15 — FETCH SELECTED YOUTUBE VIDEO METADATA

For the selected result, retrieve/store:

```text
yt_video_id
yt_video_url
yt_video_title
yt_video_channel
yt_video_channel_id
yt_video_views
yt_video_published_at
```

Set:

```text
yt_video_match_method = youtube_search
```

No score or confidence field is needed.

---

# 34. STEP 16 — ARTWORK HANDLING

The artwork is already available from the initial yt-dlp command:

```text
temp/{serial_number}/master.jpg
```

Do not download artwork again.

Do not perform a second yt-dlp command just for artwork.

Do not fetch another image source unless the implementation explicitly establishes that the initial acquisition failed to produce usable artwork and a separate fallback is added later as a deliberate scope change.

For the current Phase 1 specification, the intended artwork source is `master.jpg` from the initial acquisition.

---

# 35. STEP 17 — FINAL FILENAME

The final MP3 filename uses the permanent serial number.

Format:

```text
{serial:03d}_{safe_title}_{safe_artist}.mp3
```

Example:

```text
004_Song_A_Artist_A.mp3
```

Directory:

```text
songs/original/
```

Full path:

```text
songs/original/004_Song_A_Artist_A.mp3
```

Filename sanitization must remove or replace filesystem-invalid characters while preserving as much readable information as possible.

The serial number must never be removed.

---

# 36. STEP 18 — FINAL MP3 BUILD STRATEGY

The initial `master.mp3` is the acquired audio source.

The final output should be created as a temporary production file:

```text
songs/original/004_Song_A_Artist_A.mp3.tmp
```

The final metadata-writing stage then writes all desired tags into that file.

After validation:

```text
.mp3.tmp
    |
    | atomic rename
    v
.mp3
```

---

# 37. FINAL METADATA WRITER — MUTAGEN ONLY

Mutagen is the sole final metadata writer.

No `yt-dlp --add-metadata`.

No second metadata utility should overwrite the final tags after Mutagen.

The logical sequence is:

```text
source acquisition
    -> raw metadata
    -> normalization
    -> build final MP3
    -> Mutagen ID3 write
    -> artwork APIC write
    -> custom TXXX write
    -> save
    -> reopen
    -> validate
```

---

# 38. STANDARD ID3 FIELDS

The final MP3 should contain, when values are available:

```text
TIT2 -> Title
TPE1 -> Primary Artist / Track Artist
TPE2 -> Album Artist
TALB -> Album
TDRC -> Release Date
TRCK -> Album Track Number, when actually known
TSRC -> ISRC, when available
```

Do not use playlist serial number as `TRCK`.

The serial number is playlist identity, not album track numbering.

---

# 39. PLAYLIST-SPECIFIC CUSTOM FIELDS

The final MP3 may include playlist/source identity using `TXXX` frames.

Recommended fields:

```text
TXXX:serial_number
TXXX:playlist_position
TXXX:ytm_video_id
TXXX:ytm_url
```

These fields preserve playlist context inside the MP3.

---

# 40. YOUTUBE MUSIC VIDEO CUSTOM FIELDS

Embed selected video details using `TXXX` frames:

```text
TXXX:yt_video_id
TXXX:yt_video_url
TXXX:yt_video_title
TXXX:yt_video_channel
TXXX:yt_video_channel_id
TXXX:yt_video_views
TXXX:yt_video_published_at
```

If no acceptable video is found, those fields should be omitted or left absent rather than being filled with fake values.

---

# 41. ISRC TAGGING

If ISRC exists:

```text
TSRC = normalized ISRC
```

If ISRC is `NULL`:

```text
TSRC is omitted
```

Do not write the string `NULL` into `TSRC`.

---

# 42. ARTWORK EMBEDDING

Use:

```text
temp/{serial_number}/master.jpg
```

Embed it as the front-cover artwork using the ID3 `APIC` frame.

Recommended:

```text
type = 3
```

for front cover.

The artwork becomes physically embedded in the final MP3.

The final MP3 therefore remains usable without the original temporary artwork file.

---

# 43. SOURCE DESCRIPTION

If desired and technically practical, the source description can be stored in a `COMM` frame.

Example:

```text
COMM -> source description
```

Do not blindly embed extremely large or unsuitable text if it would create unnecessary file bloat.

The structured metadata remains in `songs.db`.

---

# 44. STEP 19 — FINAL MP3 VALIDATION

Validation must happen after all final metadata and artwork have been written.

Do not validate only the original `master.mp3`.

The final validation target is:

```text
songs/original/{serial}_{title}_{artist}.mp3.tmp
```

before its atomic rename.

Required checks:

1. File exists.
2. File size is greater than zero.
3. MP3 can be opened.
4. Audio duration can be read.
5. Title tag exists.
6. Artist tag exists.
7. Album tag exists when source metadata supplied it.
8. Release-date tag is valid when present.
9. ISRC is present when expected.
10. ISRC is omitted when source ISRC is `NULL`.
11. Artwork exists inside the final MP3.
12. Artwork can be decoded/read.
13. YouTube fields are correct when a video was found.
14. YouTube fields are absent/empty when no acceptable video was found.
15. The file is readable after closing and reopening it.

---

# 45. STEP 20 — FINAL FILE HASH

After all metadata and artwork have been written and validation succeeds, calculate:

```text
SHA-256(final MP3 bytes)
```

Store:

```text
mp3_size
mp3_sha256
```

The hash must be calculated on the **final fully tagged MP3**, not `master.mp3`.

If metadata is changed later, the file hash will legitimately change.

---

# 46. STEP 21 — ATOMIC FINALIZATION

The finalization sequence should be:

```text
1. Acquire source
2. Extract metadata
3. Resolve duplicate
4. Find YouTube video
5. Prepare final MP3
6. Write Mutagen tags
7. Embed artwork
8. Save temporary final MP3
9. Reopen final MP3
10. Validate final MP3
11. Calculate file size
12. Calculate SHA-256
13. Rename .tmp -> final .mp3
14. Insert/update songs.db
15. Update playlist.db
16. Delete temp directory
```

The physical final rename should occur only after the final MP3 passes validation.

---

# 47. STEP 22 — `songs.db` COMMIT

For a unique/non-duplicate song:

```text
songs.db
INSERT current serial
```

Store all normalized metadata and final file information.

Example conceptual row:

```text
serial_number      = 004
isrc               = USABC1234567
title              = Song A
artist             = Artist A
album              = Album X
release_date       = 2025-01-01
duration           = 243
mp3_path           = songs/original/004_Song_A_Artist_A.mp3
mp3_size           = 8123456
mp3_sha256         = ...
ytm_video_id       = ...
yt_video_id        = ...
yt_video_title     = ...
yt_video_channel   = ...
```

Then:

```text
playlist.db status = completed
```

---

# 48. STEP 23 — SUCCESSFUL COMPLETION

A song is considered successfully completed only when all of the following are true:

- source acquisition succeeded;
- source metadata was successfully parsed;
- duplicate logic was resolved;
- YouTube search completed or was intentionally left without a match;
- artwork handling completed;
- final MP3 was built;
- Mutagen metadata write succeeded;
- final MP3 validation succeeded;
- SHA-256 was calculated;
- final MP3 was atomically finalized;
- `songs.db` commit succeeded;
- `playlist.db` status was updated to `completed`;
- temporary files can be safely deleted.

---

# 49. STEP 24 — ERROR HANDLING

Any unrecoverable processing failure should result in:

```text
playlist.db.status = error
```

and:

```text
playlist.db.error_message = descriptive error
```

The serial remains unchanged.

No serial is reused.

No playlist entry is deleted.

If a final MP3 was only partially created, it must not be registered as a completed `songs.db` record.

Incomplete `.tmp` output must be cleaned or explicitly handled during the next recovery run.

---

# 50. RETRY MODEL

An entry with:

```text
status = error
```

can be returned to:

```text
status = pending
```

for another processing attempt.

The implementation may track retry count separately if desired.

The serial never changes.

---

# 51. TEMP DIRECTORY CLEANUP

For serial `004`:

```text
temp/004/
```

is removed only after finalization succeeds.

Expected cleanup removes:

```text
master.mp3
master.info.json
master.jpg
any other temporary artifacts
```

The retained production MP3 remains:

```text
songs/original/004_....mp3
```

---

# 52. NORMAL NON-DUPLICATE END-TO-END EXAMPLE

Playlist entry:

```text
Serial: 004
Title: Song A
Artist: Artist A
Album: Album X
Status: pending
```

## Acquisition

```text
temp/004/
├── master.mp3
├── master.info.json
└── master.jpg
```

## Metadata extraction

```text
isrc = USABC1234567
```

## Duplicate lookup

No existing `songs.db` row has that ISRC.

## YouTube search

```text
Song A Album X official video song
```

Results:

```text
1. Song A Lyrics Video
2. Song A Official Video
```

Result 1 is skipped.

Result 2 is selected.

## Final MP3

```text
songs/original/004_Song_A_Artist_A.mp3
```

Mutagen writes:

```text
TIT2
TPE1
TPE2
TALB
TDRC
TSRC
APIC
TXXX:serial_number
TXXX:playlist_position
TXXX:ytm_video_id
TXXX:ytm_url
TXXX:yt_video_id
TXXX:yt_video_url
TXXX:yt_video_title
TXXX:yt_video_channel
...
```

## Final result

```text
playlist.db
004 | completed
```

```text
songs.db
004 | Song A | USABC1234567 | songs/original/004_Song_A_Artist_A.mp3
```

---

# 53. DUPLICATE — KEEP PREVIOUS EXAMPLE

Existing:

```text
playlist.db
001 | Song A | completed
004 | Song A | pending
```

`songs.db`:

```text
001 | Song A | USABC1234567
```

Serial `004` is downloaded.

Its ISRC is:

```text
USABC1234567
```

Duplicate found.

User selects:

```text
1. Keep previous
```

Actions:

```text
Delete temp/004/
Keep songs.db/001
Keep MP3 001
Set playlist 004 -> duplicate
```

Final:

```text
playlist.db
001 | completed
004 | duplicate
```

```text
songs.db
001 | Song A
```

---

# 54. DUPLICATE — KEEP CURRENT EXAMPLE

Existing:

```text
playlist.db
001 | Song A | completed
004 | Song A | pending
```

`songs.db`:

```text
001 | Song A | USABC1234567
```

Serial `004` is downloaded.

Its ISRC matches `001`.

User selects:

```text
2. Keep current
```

Actions:

```text
Delete MP3 belonging to 001
Delete songs.db row 001
Finish processing serial 004
Create final MP3 004
Insert songs.db row 004
Set playlist 004 -> completed
Set playlist 001 -> pending
```

Final:

```text
playlist.db
001 | pending
004 | completed
```

```text
songs.db
004 | Song A
```

Serial `001` remains permanent and available for future processing.

---

# 55. MISSING ISRC EXAMPLE

Suppose:

```text
serial = 005
isrc = NULL
```

The system does:

```text
No ISRC
   |
   v
No songs.db duplicate lookup
   |
   v
Continue normally
```

If the song is successfully finalized:

```text
playlist.db
005 | completed
```

and:

```text
songs.db
005 | isrc = NULL
```

Do not write the literal string `NULL` into the MP3 `TSRC` field.

Do not perform title/artist fallback matching.

---

# 56. YOUTUBE SEARCH EXAMPLE

For:

```text
Title = Song A
Album = Album X
```

Search exactly:

```text
Song A Album X official video song
```

Returned:

```text
1. Song A Lyrics Video
2. Song A Official Video
3. Song A Live
4. Song A Cover
```

Processing:

```text
1 -> contains lyrics -> skip
2 -> does not contain lyrics -> select
3 -> not examined
4 -> not examined
```

No view count is compared.

No duration is compared.

No channel is compared.

---

# 57. FILE NAMING RULES

## Final MP3

```text
{serial:03d}_{safe_title}_{safe_artist}.mp3
```

## Temporary working directory

```text
temp/{serial}/
```

## Temporary final file

```text
songs/original/{serial}_{safe_title}_{safe_artist}.mp3.tmp
```

The serial must always be included.

---

# 58. FILESYSTEM SAFETY

Filename sanitization must:

- remove filesystem-invalid characters;
- prevent unintended directory traversal;
- avoid accidental reserved filenames;
- preserve the serial prefix;
- preserve readable title and artist text where possible.

The sanitized filename must never change the database identity.

---

# 59. DATABASE SAFETY

The implementation should use transactions for state changes that must remain consistent.

Examples:

### Normal completion

```text
BEGIN TRANSACTION
    INSERT songs.db row
    UPDATE playlist.db status = completed
COMMIT
```

### Keep previous duplicate

```text
BEGIN TRANSACTION
    UPDATE playlist.db current serial = duplicate
COMMIT
```

### Keep current duplicate

```text
BEGIN TRANSACTION
    DELETE songs.db previous serial
    INSERT songs.db current serial
    UPDATE playlist.db previous serial = pending
    UPDATE playlist.db current serial = completed
COMMIT
```

Filesystem deletions should be coordinated carefully with database transactions because SQLite transactions cannot roll back a physical file deletion.

Therefore, the implementation should structure operations so that a final valid file exists before a successful database commit whenever possible.

---

# 60. KEEP-CURRENT DUPLICATE SAFETY

The most sensitive operation is replacing the existing retained song.

The implementation should not delete the old MP3 until the current song has successfully passed final validation.

Preferred sequence:

```text
1. Current download exists.
2. Current metadata is valid.
3. Current duplicate is confirmed.
4. User chooses current.
5. Current final MP3 is fully built and validated.
6. Current file is ready.
7. Old retained file is removed.
8. Old songs.db row is removed.
9. Current songs.db row is inserted.
10. Current playlist entry becomes completed.
11. Old playlist entry becomes pending.
```

The important principle is:

> Never destroy the previously retained song merely because the replacement download started; replace it only after the new song is valid.

---

# 61. MUTAGEN IMPLEMENTATION RESPONSIBILITY

The embedder module should be the single place responsible for writing final ID3 metadata.

Suggested API concept:

```python
embed_final_mp3(
    source_mp3,
    output_mp3,
    metadata,
    artwork_path,
)
```

It should:

1. open/create ID3 tags;
2. remove or replace the intended application-managed fields;
3. write standard ID3 frames;
4. write custom `TXXX` frames;
5. embed the front-cover `APIC` frame;
6. save;
7. close/reopen if needed for validation.

Do not scatter final tag-writing logic across unrelated modules.

---

# 62. METADATA FIELD OWNERSHIP

## Source-owned

Obtained from yt-dlp/YTMusic:

```text
title
artist
album
duration
release date
upload date
ISRC
source audio information
source video/source IDs
source descriptions
thumbnails
```

## Search-owned

Obtained from the selected YouTube result:

```text
yt_video_id
yt_video_url
yt_video_title
yt_video_channel
yt_video_channel_id
yt_video_views
yt_video_published_at
```

## Application-owned

Generated by the project:

```text
serial_number
playlist_position
status
mp3_path
mp3_size
mp3_sha256
yt_video_match_method
```

---

# 63. SOURCE VS FINAL MP3

The following distinction is important:

```text
master.mp3
```

is the temporary acquired audio.

```text
songs/original/004_....mp3
```

is the final application-owned MP3.

The final MP3 is the file that:

- contains final tags;
- contains embedded artwork;
- contains custom YouTube fields;
- receives the SHA-256 hash;
- is referenced by `songs.db`;
- survives temporary cleanup.

---

# 64. PIPELINE MODULE RESPONSIBILITIES

## `main.py`

Application entry point.

Responsibilities:

- load configuration;
- initialize directories;
- initialize databases;
- start ingestion/processing;
- handle top-level errors.

## `db_playlist.py`

Responsibilities:

- create `playlist.db` schema;
- insert playlist entries;
- allocate/query serials;
- update statuses;
- store errors.

## `db_songs.py`

Responsibilities:

- create `songs.db` schema;
- insert/update/delete song records;
- search by ISRC;
- retrieve retained-song file paths.

## `playlist_ingest.py`

Responsibilities:

- call YTMusic playlist API;
- preserve returned order;
- extract playlist metadata;
- assign serials;
- populate `playlist.db`.

## `downloader.py`

Responsibilities:

- build the single yt-dlp acquisition command;
- execute it;
- locate `master.mp3`;
- locate `master.info.json`;
- locate `master.jpg`;
- validate acquisition output.

## `metadata.py`

Responsibilities:

- parse `master.info.json`;
- normalize metadata;
- extract ISRC;
- derive final structured metadata object.

## `duplicate_checker.py`

Responsibilities:

- accept normalized ISRC;
- query `songs.db` by ISRC;
- trigger duplicate decision when a match exists;
- perform no fallback matching.

## `youtube_finder.py`

Responsibilities:

- construct exact search query;
- retrieve results;
- skip results whose title contains `lyrics`;
- select first remaining result;
- retrieve selected video metadata.

## `embedder.py`

Responsibilities:

- create final MP3 tags;
- embed artwork;
- write custom TXXX fields;
- save final MP3.

## `validator.py`

Responsibilities:

- reopen final MP3;
- validate audio;
- validate tags;
- validate artwork;
- validate expected custom metadata.

## `hashing.py`

Responsibilities:

- calculate SHA-256 of final MP3;
- return byte size and digest.

## `pipeline.py`

Responsibilities:

- orchestrate each stage;
- enforce state transitions;
- coordinate duplicate decisions;
- coordinate finalization;
- guarantee cleanup.

---

# 65. DETAILED SINGLE-SONG EXECUTION ORDER

For one serial, the exact high-level implementation order is:

```text
1. Load playlist row.
2. Confirm status = pending.
3. Create temp/{serial}/.
4. Execute one yt-dlp acquisition.
5. Validate master.mp3/info.json/artwork.
6. Parse info.json.
7. Normalize title/artist/album/dates/ISRC/audio metadata.
8. If ISRC is non-NULL, query songs.db.
9. If duplicate exists, ask user.
10. If user keeps previous:
       delete temp
       mark current duplicate
       finish this serial
11. If user keeps current:
       keep current temporary source
       prepare current final MP3
       only after current is valid, remove old retained MP3
       replace old songs.db record
       mark old playlist entry pending
12. Build YouTube search query.
13. Retrieve YouTube results.
14. Walk results in returned order.
15. Skip titles containing lyrics.
16. Select first remaining result.
17. Retrieve selected video metadata.
18. Use existing master.jpg.
19. Create final .mp3.tmp.
20. Write all final ID3 metadata with Mutagen.
21. Embed APIC artwork with Mutagen.
22. Save.
23. Reopen final file.
24. Validate audio and metadata.
25. Calculate SHA-256 and file size.
26. Atomically rename .tmp -> .mp3.
27. Insert songs.db row.
28. Update playlist.db to completed.
29. Delete temp/{serial}/.
30. Move to next pending playlist entry.
```

---

# 66. COMPLETE PROJECT PIPELINE — EXPANDED

```text
┌──────────────────────────────────────────────────────────────┐
│                    YOUTUBE MUSIC PLAYLIST                   │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                     YTMUSIC API INGESTION                    │
│                                                              │
│ - read playlist ID                                           │
│ - retrieve complete playlist                                 │
│ - preserve returned/default order                            │
│ - extract video ID/title/artists/duration                    │
│ - assign permanent serial number                             │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                         playlist.db                           │
│                                                              │
│ serial | position | YTM ID | title | artist | status       │
│                                                              │
│ status = pending                                              │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                  SELECT NEXT PENDING ENTRY                   │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                   temp/{serial_number}/                      │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                   ONE COMPLETE YT-DLP RUN                    │
│                                                              │
│                         yt-dlp                               │
│                                                              │
│                    -x / MP3                                  │
│                    info.json                                 │
│                    thumbnail/artwork                         │
│                                                              │
│                 NO --add-metadata                             │
└───────────────┬────────────────┬────────────────┬────────────┘
                │                │                │
                v                v                v
          master.mp3      master.info.json    master.jpg
                │                │                │
                └────────────────┼────────────────┘
                                 │
                                 v
┌──────────────────────────────────────────────────────────────┐
│                     SOURCE VALIDATION                        │
│                                                              │
│ - audio exists                                              │
│ - JSON valid                                                 │
│ - artwork readable                                           │
│ - duration readable                                          │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                   METADATA EXTRACTION                        │
│                                                              │
│ title / artists / album / dates / duration                  │
│ ISRC / source audio / source IDs / description              │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                    METADATA NORMALIZATION                    │
│                                                              │
│ source metadata -> application metadata                      │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
                     ┌─────────┴─────────┐
                     │                   │
                 ISRC != NULL        ISRC == NULL
                     │                   │
                     v                   │
             search songs.db             │
                     │                   │
               ┌─────┴──────┐            │
               │            │            │
            no match      match          │
               │            │            │
               │            v            │
               │      DUPLICATE PROMPT   │
               │        /          \     │
               │   previous        current
               │      │                │
               │      v                v
               │  discard current   keep current
               │  temp + mark       replace old
               │  duplicate         retained song
               │                       │
               └──────────┬────────────┘
                          │
                          v
┌──────────────────────────────────────────────────────────────┐
│                 YOUTUBE OFFICIAL VIDEO SEARCH                │
│                                                              │
│ query:                                                       │
│ {title} {album_name} official video song                     │
│                                                              │
│ returned result order is authoritative                       │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                   SIMPLE RESULT FILTER                       │
│                                                              │
│ If result title contains "lyrics" -> skip                   │
│ Otherwise -> select immediately                              │
│                                                              │
│ No ranking. No scoring. No confidence.                       │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                  SELECTED VIDEO METADATA                     │
│                                                              │
│ ID / URL / title / channel / channel ID / views / date      │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                    FINAL MP3 BUILD                           │
│                                                              │
│ source audio + master.jpg                                    │
│                                                              │
│ final file: .mp3.tmp                                         │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                 MUTAGEN FINAL TAG WRITER                     │
│                                                              │
│ Standard ID3 + custom TXXX + APIC artwork                   │
│                                                              │
│ Mutagen is the sole final metadata authority                 │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                     FINAL VALIDATION                         │
│                                                              │
│ - audio playable                                             │
│ - duration valid                                             │
│ - tags readable                                               │
│ - artwork embedded                                           │
│ - expected YouTube fields present                            │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                    HASH + FILE SIZE                          │
│                                                              │
│ SHA-256(final fully-tagged MP3)                              │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                      ATOMIC RENAME                           │
│                                                              │
│ .mp3.tmp -> final .mp3                                       │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                         songs.db                             │
│                                                              │
│ current serial + metadata + file path + hash                │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                       playlist.db                            │
│                                                              │
│ current serial -> completed                                 │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────┐
│                      CLEANUP TEMP                            │
│                                                              │
│ delete temp/{serial}/                                        │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               v
                    NEXT PENDING ENTRY
```

---

# 67. COMPLETE STATUS EXAMPLES

## Initial

```text
playlist.db

001 pending
002 pending
003 pending
004 pending
```

## After normal processing

```text
playlist.db

001 completed
002 completed
003 completed
004 completed
```

`songs.db`:

```text
001
002
003
004
```

## After duplicate — keep previous

```text
playlist.db

001 completed
002 completed
003 duplicate
004 pending
```

`songs.db`:

```text
001
002
004
```

## After duplicate — keep current

```text
playlist.db

001 pending
002 completed
003 completed
004 pending
```

`songs.db`:

```text
002
003
```

The old serial still exists in the playlist database.

---

# 68. WHAT `playlist.db` MUST NEVER DO

`playlist.db` must never:

- delete a playlist entry because of duplicate detection;
- change a serial number;
- recycle a serial number;
- replace one playlist entry with another;
- use ISRC as its primary identity;
- use YouTube video ID as its primary identity.

---

# 69. WHAT `songs.db` MUST NEVER DO

`songs.db` must never:

- contain two rows with the same serial;
- contain the discarded current duplicate when the user chose previous;
- retain an old row after its MP3 has been intentionally replaced by the current duplicate;
- invent ISRC values;
- use fallback duplicate matching when ISRC is `NULL`.

---

# 70. WHAT YT-DLP MUST DO

The initial yt-dlp stage must:

- use the selected YTM source URL;
- download the source audio;
- write `info.json`;
- write thumbnail/artwork;
- convert the artwork to the selected image type when necessary;
- not perform final ID3 tagging;
- not be called a second time for artwork only.

---

# 71. WHAT MUTAGEN MUST DO

Mutagen must:

- write standard ID3 tags;
- write ISRC when present;
- write custom source/YouTube fields;
- embed artwork;
- save the final MP3;
- provide the final metadata state that is subsequently validated.

---

# 72. WHAT THE VIDEO FINDER MUST DO

It must:

1. construct the exact query;
2. retrieve results;
3. inspect titles in returned order;
4. skip titles containing `lyrics`;
5. select the first remaining result;
6. stop immediately after selection;
7. retrieve that video's metadata.

It must not:

- score;
- rank;
- compare views;
- compare durations;
- compare channels;
- calculate confidence.

---

# 73. RESTART / RESUME BEHAVIOR

The application must be restart-safe.

If it exits unexpectedly:

- already finalized `completed` rows remain completed;
- duplicate decisions already committed remain committed;
- permanent serials remain unchanged;
- new processing continues from the next `pending` entry;
- `error` entries can be retried.

If a temporary directory remains after a crash, startup/recovery logic should inspect and clean stale temporary directories as appropriate rather than assuming they represent completed songs.

---

# 74. LOGGING REQUIREMENTS

The application should log enough information to understand every processing attempt.

Minimum useful information per serial:

```text
serial
playlist position
title
artist
status before processing
status after processing
ISRC
whether duplicate detected
existing duplicate serial when applicable
user duplicate decision
YouTube search query
selected YouTube video ID when applicable
final MP3 path
final MP3 size
SHA-256
error message when applicable
```

Logs must not replace the databases.

The databases remain authoritative for persistent state.

---

# 75. USER PROMPTS

Normal successful processing should be automatic.

The only required interactive prompt is duplicate handling.

Example:

```text
[DUPLICATE]
Current: 004 - Song A - Artist A
Existing: 001 - Song A - Artist A
ISRC: USABC1234567

1) Keep previous
2) Keep current
Selection:
```

No prompt is required for ordinary YouTube video selection.

The YouTube selection rule is deterministic:

```text
first result whose title does not contain lyrics
```

---

# 76. TEST PLAN

The final implementation should test at least the following cases.

## Test 1 — New unique song

Expected:

```text
pending -> completed
songs.db row created
MP3 created
```

## Test 2 — Duplicate with keep previous

Expected:

```text
current -> duplicate
old song retained
current songs.db row absent
```

## Test 3 — Duplicate with keep current

Expected:

```text
old playlist entry -> pending
current playlist entry -> completed
old songs.db row deleted
current songs.db row created
old MP3 deleted
current MP3 retained
```

## Test 4 — NULL ISRC

Expected:

```text
isrc = NULL
no duplicate query
song processes normally
```

## Test 5 — YouTube result with lyrics first

Expected:

```text
result 1 skipped
result 2 selected
```

## Test 6 — All YouTube results contain lyrics

Expected:

```text
yt_video fields = NULL
song can still complete
```

## Test 7 — YouTube search returns an acceptable result first

Expected:

```text
result 1 selected immediately
```

## Test 8 — Source acquisition fails

Expected:

```text
status = error
no completed songs.db row
serial preserved
```

## Test 9 — Final MP3 validation fails

Expected:

```text
no completed songs.db commit
no playlist completed state
```

## Test 10 — Restart after error

Expected:

```text
error -> pending
retry uses same serial
```

## Test 11 — Duplicate replacement after current file validation

Expected:

```text
old MP3 is not deleted until replacement MP3 validates successfully
```

## Test 12 — Playlist contains same YTM entry twice

Expected:

```text
separate serials
separate playlist rows
no serial collision
```

---

# 77. FINAL ACCEPTANCE CRITERIA

Phase 1 is complete when the system can demonstrate all of the following:

## Playlist identity

- complete playlist is ingested;
- returned order is preserved;
- every playlist entry gets a permanent serial;
- serials never collide;
- serials are never reused.

## Source acquisition

- the exact YTM source is downloaded;
- one yt-dlp command obtains audio + info.json + artwork;
- `--add-metadata` is not used;
- acquisition artifacts are validated.

## Metadata

- detailed source metadata is parsed;
- ISRC is extracted when available;
- missing ISRC is stored as NULL;
- no fallback duplicate match is used.

## Duplicate handling

- ISRC match is found in `songs.db`;
- user chooses previous/current;
- keep previous marks current playlist entry duplicate;
- keep current deletes the old retained song and changes old playlist entry to pending;
- playlist entries are never deleted.

## YouTube video discovery

- exact search query is used;
- results are processed in returned order;
- `lyrics` results are skipped;
- first remaining result is selected;
- no scoring/ranking is used;
- no acceptable result is allowed to leave the song otherwise incomplete.

## Final MP3

- final MP3 is created;
- Mutagen writes all final metadata;
- artwork is embedded;
- YouTube metadata is embedded;
- final file validates after writing;
- SHA-256 is calculated;
- final filename contains permanent serial.

## Persistence

- `songs.db` accurately reflects retained files;
- `playlist.db` accurately reflects processing status;
- completed records point to existing valid MP3 files;
- temporary directories are cleaned after finalization.

---

# 78. FINAL LOCKED RULES

These are the final rules for implementation and should not be changed casually during coding.

1. `playlist.db` is the permanent playlist database.
2. `songs.db` is the retained-song database.
3. Every playlist entry receives one permanent serial number.
4. Serial numbers are unique.
5. Serial numbers are never reused.
6. Serial numbers never change.
7. Serial numbers are assigned according to playlist ingestion order.
8. The API/default playlist order is preserved.
9. `playlist_position` is stored separately from the permanent serial.
10. `ytm_video_id` is not the permanent playlist identity.
11. The same YTM entry can appear multiple times in a playlist.
12. Such repeated entries receive different serial numbers.
13. `pending`, `completed`, `duplicate`, and `error` are the playlist processing statuses.
14. `completed` requires a retained song in `songs.db`.
15. `duplicate` means the entry was processed but the previous retained song was kept.
16. `error` means processing failed and may later be retried.
17. ISRC is the only duplicate key.
18. Missing ISRC is stored as `NULL`.
19. Missing ISRC does not trigger duplicate detection.
20. No fallback duplicate matching is permitted.
21. Duplicate detection is performed against `songs.db`.
22. The user decides whether to keep previous or current duplicate.
23. Keep previous -> current playlist entry becomes `duplicate`.
24. Keep previous -> previous song remains unchanged.
25. Keep current -> previous physical MP3 is deleted only after current replacement is valid.
26. Keep current -> previous `songs.db` row is deleted.
27. Keep current -> previous playlist entry becomes `pending`.
28. Keep current -> current playlist entry becomes `completed`.
29. Playlist entries are never deleted because of duplicates.
30. Initial source acquisition uses one complete yt-dlp command.
31. That acquisition gets audio.
32. That acquisition gets `info.json`.
33. That acquisition gets artwork.
34. No second artwork download is performed.
35. yt-dlp does not write final ID3 metadata.
36. `--add-metadata` is not used.
37. Mutagen is the single final metadata writer.
38. Mutagen writes standard ID3 fields.
39. Mutagen writes custom TXXX source/YouTube fields.
40. Mutagen embeds front-cover artwork.
41. The final MP3 is validated after metadata writing.
42. SHA-256 is calculated after final metadata writing.
43. The final MP3 is atomically renamed after successful validation.
44. YouTube search query is exactly `{title} {album_name} official video song`.
45. Results remain in returned order.
46. Titles containing `lyrics` are skipped case-insensitively.
47. The first remaining result is selected.
48. No YouTube scoring exists.
49. No YouTube ranking exists.
50. No YouTube confidence score exists.
51. No view-count ranking exists.
52. No duration ranking exists.
53. No channel ranking exists.
54. If no acceptable YouTube result exists, the YouTube video fields remain NULL/absent.
55. The song can still complete without an acceptable YouTube video.
56. Final MP3 filename uses the permanent serial.
57. Temporary files are deleted only after successful finalization.
58. Database state must reflect physical file state.
59. A failed processing attempt must never be marked `completed`.
60. Lyrics and Phase 2 audio-analysis features remain outside the Phase 1 scope.

---

# 79. FINAL ONE-PAGE SUMMARY

```text
PLAYLIST
   |
   | YTMusic API
   v
playlist.db
   |
   | permanent serial
   v
PENDING ENTRY
   |
   | ONE yt-dlp command
   +-------------------------------+
   |               |               |
   v               v               v
audio.mp3      info.json       artwork.jpg
   |               |               |
   +---------------+---------------+
                   |
                   v
          metadata normalization
                   |
                   v
              ISRC check
                   |
          +--------+--------+
          |                 |
       NULL/unique       duplicate
          |                 |
          |             ask user
          |             /      \
          |       previous     current
          |          |            |
          |          v            v
          |       duplicate   replace old
          |                       |
          +-----------+-----------+
                      |
                      v
           YouTube search
                      |
       title + album + official video song
                      |
                      v
          skip title containing lyrics
                      |
                      v
          first remaining result
                      |
                      v
         selected video metadata
                      |
                      v
             use master.jpg
                      |
                      v
              final MP3.tmp
                      |
                      v
             Mutagen writes tags
                      |
                      v
              validate final MP3
                      |
                      v
                 SHA-256
                      |
                      v
              atomic final MP3
                      |
                      v
                  songs.db
                      |
                      v
          playlist.db -> completed
                      |
                      v
                cleanup temp
                      |
                      v
              NEXT PENDING ENTRY
```

---

# 80. END STATE

At the end of a successful full run, the project contains:

```text
phase1_project/
│
├── db/
│   ├── playlist.db
│   └── songs.db
│
├── songs/
│   └── original/
│       ├── 001_....mp3
│       ├── 002_....mp3
│       ├── 003_....mp3
│       └── ...
│
├── temp/
│   └── empty after successful cleanup
│
├── config.json
├── cookies.txt
├── requirements.txt
├── main.py
└── src/
```

`playlist.db` preserves the complete playlist-entry identity and status history required by Phase 1.

`songs.db` contains only the currently retained song assets.

Each retained MP3 is self-contained with its final ID3 metadata and embedded artwork.

This is the complete Phase 1 architecture and implementation specification.
