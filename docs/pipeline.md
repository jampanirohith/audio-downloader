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
