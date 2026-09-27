from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

SCHEMA_VERSION = 6

SONG_COLUMNS = [
    "serial_number", "ytm_playlist_id", "title", "title_original", "primary_artist", "artist", "artists_json",
    "album", "album_artist", "track_number", "disc_number", "release_date", "release_date_source", "upload_date",
    "upload_timestamp", "release_timestamp", "modified_date", "modified_timestamp", "description", "genre", "composer",
    "publisher", "copyright", "license", "comment", "language", "bpm", "compilation", "encoder", "duration",
    "source_duration", "source_ext", "source_container", "source_codec", "source_format_id", "source_format_note",
    "source_bitrate", "source_sample_rate", "source_channels", "source_filesize", "source_filesize_approx", "source_language",
    "source_video_id", "source_webpage_url", "source_original_url", "source_display_id", "source_webpage_url_basename", "source_webpage_url_domain",
    "source_extractor", "source_extractor_key", "source_channel", "source_channel_id", "source_channel_url", "source_channel_follower_count",
    "source_channel_is_verified", "source_uploader", "source_uploader_id", "source_uploader_url", "source_views", "source_location",
    "source_availability", "source_age_limit", "source_live_status", "source_media_type", "source_thumbnail",
    "source_thumbnails_json", "source_categories_json", "source_tags_json", "source_playlist", "source_playlist_id", "source_playlist_count",
    "source_playlist_index", "source_playlist_uploader", "source_playlist_uploader_id", "source_playlist_channel", "source_playlist_channel_id",
    "source_playlist_webpage_url", "ytm_video_id", "ytm_url", "ytm_playlist_item_json",
    "source_info_json", "mp3_path", "mp3_size", "mp3_sha256", "yt_video_id", "yt_video_url", "yt_video_title", "yt_video_fulltitle",
    "yt_video_alt_title", "yt_video_channel", "yt_video_channel_id", "yt_video_uploader", "yt_video_uploader_id", "yt_video_upload_date",
    "yt_video_timestamp", "yt_video_release_date", "yt_video_release_timestamp", "yt_video_duration", "yt_video_views",
    "yt_video_likes", "yt_video_comments", "yt_video_thumbnail", "yt_video_description", "yt_video_categories_json",
    "yt_video_tags_json", "yt_video_extractor", "yt_video_extractor_key", "yt_video_info_json", "yt_video_search_query",
    "yt_video_search_result_index", "yt_video_search_results_fetched", "yt_video_match_method", "artwork_source_url", "artwork_width",
    "artwork_height", "artwork_path", "artwork_provider", "metadata_json_path",
    "spotify_track_id", "spotify_track_name", "spotify_track_url", "spotify_uri", "spotify_artists_json", "spotify_artist_ids_json",
    "spotify_artist_urls_json", "spotify_album_id", "spotify_album_name", "spotify_album_url", "spotify_album_type",
    "spotify_album_release_date", "spotify_album_release_precision", "spotify_album_total_tracks", "spotify_album_artwork_url",
    "spotify_album_label", "spotify_album_copyrights_json", "spotify_duration_ms", "spotify_duration_seconds", "spotify_duration_delta_ms",
    "spotify_explicit", "spotify_popularity", "spotify_isrc", "spotify_track_number", "spotify_disc_number",
    "spotify_search_query", "spotify_search_result_index", "spotify_raw_json", "spotify_album_raw_json",
    "lyrics_status", "lyrics_path", "lrclib_id", "lrclib_track_name", "lrclib_artist_name", "lrclib_album_name",
    "lrclib_duration", "lrclib_duration_delta_seconds", "lrclib_match_method", "lrclib_raw_json", "lyrics_embedded",
]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS songs (
    serial_number INTEGER PRIMARY KEY,
    ytm_playlist_id TEXT,
    title TEXT NOT NULL,
    title_original TEXT,
    primary_artist TEXT,
    artist TEXT,
    artists_json TEXT,
    album TEXT,
    album_artist TEXT,
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
CREATE INDEX IF NOT EXISTS idx_songs_ytm_video_id ON songs(ytm_video_id);
CREATE INDEX IF NOT EXISTS idx_songs_yt_video_id ON songs(yt_video_id);
"""


class SongsDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=FULL")
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            self._migrate_schema(conn, version)
            conn.executescript(SCHEMA_SQL)
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            conn.commit()

    def _migrate_schema(self, conn: sqlite3.Connection, version: int) -> None:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='songs'").fetchone():
            return
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(songs)").fetchall()]
        expected = set(SONG_COLUMNS + ["created_at", "updated_at"])
        if version >= SCHEMA_VERSION and set(columns) == expected:
            return
        legacy_rows = conn.execute("SELECT * FROM songs").fetchall()
        for idx in conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='songs'").fetchall():
            name = str(idx["name"])
            if not name.startswith("sqlite_"):
                quoted = '"' + name.replace('"', '""') + '"'
                conn.execute(f"DROP INDEX IF EXISTS {quoted}")
        conn.execute("ALTER TABLE songs RENAME TO songs_legacy_migration")
        conn.executescript(SCHEMA_SQL)
        for row in legacy_rows:
            record = {column: row[column] for column in row.keys() if column in SONG_COLUMNS}
            record.setdefault("title", "Untitled")
            record.setdefault("mp3_path", "")
            source_raw = record.get("source_info_json")
            if not source_raw:
                source_raw = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
            record["source_info_json"] = source_raw
            placeholders = ", ".join("?" for _ in SONG_COLUMNS)
            conn.execute(
                f"INSERT INTO songs ({', '.join(SONG_COLUMNS)}) VALUES ({placeholders})",
                [record.get(column) for column in SONG_COLUMNS],
            )
        conn.execute("DROP TABLE songs_legacy_migration")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def insert_song(self, record: dict[str, Any], *, conn: sqlite3.Connection | None = None, table_prefix: str = "") -> None:
        placeholders = ", ".join("?" for _ in SONG_COLUMNS)
        qualified = f"{table_prefix}songs" if table_prefix else "songs"
        sql = f"INSERT INTO {qualified} ({', '.join(SONG_COLUMNS)}) VALUES ({placeholders})"
        values = [record.get(column) for column in SONG_COLUMNS]
        if conn is not None:
            conn.execute(sql, values)
            return
        with self.transaction() as tx:
            tx.execute(sql, values)

    def update_song_file_fields(self, serial_number: int, *, mp3_size: int, mp3_sha256: str, artwork_source_url: str | None = None,
                                artwork_width: int | None = None, artwork_height: int | None = None) -> None:
        with self.transaction() as conn:
            conn.execute(
                """UPDATE songs SET mp3_size=?, mp3_sha256=?, artwork_source_url=?, artwork_width=?, artwork_height=?, updated_at=CURRENT_TIMESTAMP WHERE serial_number=?""",
                (mp3_size, mp3_sha256, artwork_source_url, artwork_width, artwork_height, serial_number),
            )

    def get_by_serial(self, serial_number: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM songs WHERE serial_number = ?", (serial_number,)).fetchone()
            return dict(row) if row else None

    def count(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS c FROM songs").fetchone()["c"])

    def get_all(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM songs ORDER BY serial_number ASC").fetchall()
            return [dict(row) for row in rows]

    def assert_serial_integrity(self) -> None:
        with self.connect() as conn:
            dup = conn.execute("SELECT serial_number, COUNT(*) AS c FROM songs GROUP BY serial_number HAVING c > 1 LIMIT 1").fetchone()
            if dup:
                raise RuntimeError(f"Duplicate song serial detected: {dup['serial_number']}")
