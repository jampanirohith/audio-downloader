from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

SCHEMA_VERSION = 4
VALID_STATUSES = ("pending", "completed", "duplicate", "error")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS playlist_entries (
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
CREATE INDEX IF NOT EXISTS idx_playlist_status_position
ON playlist_entries(status, playlist_position, serial_number);
CREATE INDEX IF NOT EXISTS idx_playlist_video_id
ON playlist_entries(ytm_video_id);
"""


class PlaylistDB:
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
            conn.execute("PRAGMA foreign_keys=OFF")
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            self._migrate_schema(conn, version)
            conn.executescript(SCHEMA_SQL)
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            conn.commit()

    def _migrate_schema(self, conn: sqlite3.Connection, version: int) -> None:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='playlist_entries'").fetchone()
        if not exists:
            return
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(playlist_entries)").fetchall()}
        required = {
            "serial_number", "playlist_position", "ytm_playlist_id", "ytm_video_id", "ytm_url",
            "title", "artist", "album", "duration", "ytm_playlist_item_json", "status", "error_message",
            "created_at", "updated_at",
        }
        if version >= SCHEMA_VERSION and columns == required:
            return

        legacy_rows = conn.execute("SELECT * FROM playlist_entries ORDER BY playlist_position, serial_number").fetchall()
        conn.execute("ALTER TABLE playlist_entries RENAME TO playlist_entries_legacy_migration")
        conn.executescript(SCHEMA_SQL)
        for row in legacy_rows:
            values = dict(row)
            status = values.get("status")
            if status not in VALID_STATUSES:
                status = "pending"
            title = str(values.get("title") or "Untitled")
            artist = str(values.get("artist") or "Unknown Artist")
            conn.execute(
                """
                INSERT INTO playlist_entries (
                    serial_number, playlist_position, ytm_playlist_id, ytm_video_id, ytm_url,
                    title, artist, album, duration, ytm_playlist_item_json, status, error_message,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values.get("serial_number"), values.get("playlist_position") or 0,
                    values.get("ytm_playlist_id"), values.get("ytm_video_id"), values.get("ytm_url"),
                    title, artist, values.get("album"), values.get("duration"), values.get("ytm_playlist_item_json"),
                    status, values.get("error_message") if status == "error" else None,
                    values.get("created_at"), values.get("updated_at"),
                ),
            )
        conn.execute("DROP TABLE playlist_entries_legacy_migration")

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

    def max_serial(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COALESCE(MAX(serial_number), 0) AS max_serial FROM playlist_entries").fetchone()["max_serial"])

    def get_all(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM playlist_entries ORDER BY playlist_position ASC, serial_number ASC").fetchall()
            return [dict(row) for row in rows]

    def get_by_serial(self, serial_number: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM playlist_entries WHERE serial_number = ?", (serial_number,)).fetchone()
            return dict(row) if row else None

    def get_next_pending(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT * FROM playlist_entries
                   WHERE status='pending' AND ytm_url IS NOT NULL AND ytm_url <> ''
                   ORDER BY playlist_position ASC, serial_number ASC LIMIT 1"""
            ).fetchone()
            return dict(row) if row else None

    def insert_entry(
        self, *, serial_number: int, playlist_position: int, ytm_playlist_id: str | None,
        ytm_video_id: str | None, ytm_url: str | None, title: str, artist: str,
        album: str | None, duration: int | None, ytm_playlist_item_json: str | None,
        status: str = "pending", error_message: str | None = None,
    ) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid playlist status: {status}")
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO playlist_entries (
                    serial_number, playlist_position, ytm_playlist_id, ytm_video_id, ytm_url,
                    title, artist, album, duration, ytm_playlist_item_json, status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (serial_number, playlist_position, ytm_playlist_id, ytm_video_id, ytm_url, title, artist, album, duration, ytm_playlist_item_json, status, error_message),
            )

    def update_ingested_fields(
        self, *, serial_number: int, playlist_position: int, ytm_playlist_id: str | None,
        ytm_video_id: str | None, ytm_url: str | None, title: str, artist: str,
        album: str | None, duration: int | None, ytm_playlist_item_json: str | None,
        status: str | None = None, error_message: str | None = None,
    ) -> None:
        if status is not None and status not in VALID_STATUSES:
            raise ValueError(f"Invalid playlist status: {status}")
        with self.transaction() as conn:
            if status is None:
                cur = conn.execute(
                    """UPDATE playlist_entries SET playlist_position=?, ytm_playlist_id=?, ytm_video_id=?, ytm_url=?,
                       title=?, artist=?, album=?, duration=?, ytm_playlist_item_json=?, updated_at=CURRENT_TIMESTAMP
                       WHERE serial_number=?""",
                    (playlist_position, ytm_playlist_id, ytm_video_id, ytm_url, title, artist, album, duration, ytm_playlist_item_json, serial_number),
                )
            else:
                cur = conn.execute(
                    """UPDATE playlist_entries SET playlist_position=?, ytm_playlist_id=?, ytm_video_id=?, ytm_url=?,
                       title=?, artist=?, album=?, duration=?, ytm_playlist_item_json=?, status=?, error_message=?, updated_at=CURRENT_TIMESTAMP
                       WHERE serial_number=?""",
                    (playlist_position, ytm_playlist_id, ytm_video_id, ytm_url, title, artist, album, duration, ytm_playlist_item_json, status, error_message, serial_number),
                )
            if cur.rowcount != 1:
                raise KeyError(f"Playlist serial {serial_number} not found")

    def update_status(self, serial_number: int, status: str, *, error_message: str | None = None) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid playlist status: {status}")
        with self.transaction() as conn:
            cur = conn.execute(
                "UPDATE playlist_entries SET status=?, error_message=?, updated_at=CURRENT_TIMESTAMP WHERE serial_number=?",
                (status, error_message, serial_number),
            )
            if cur.rowcount != 1:
                raise KeyError(f"Playlist serial {serial_number} not found")

    def retry_all_errors(self) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                """UPDATE playlist_entries SET status='pending', error_message=NULL, updated_at=CURRENT_TIMESTAMP
                   WHERE status='error' AND ytm_url IS NOT NULL AND ytm_url <> ''"""
            )
            return int(cur.rowcount)

    def counts(self) -> dict[str, int]:
        with self.connect() as conn:
            counts = {row["status"]: int(row["count"]) for row in conn.execute("SELECT status, COUNT(*) AS count FROM playlist_entries GROUP BY status")}
        return {
            "total": sum(counts.values()),
            "pending": counts.get("pending", 0),
            "completed": counts.get("completed", 0),
            "duplicate": counts.get("duplicate", 0),
            "error": counts.get("error", 0),
        }

    def assert_serial_integrity(self) -> None:
        with self.connect() as conn:
            row = conn.execute("SELECT serial_number, COUNT(*) AS c FROM playlist_entries GROUP BY serial_number HAVING c>1 LIMIT 1").fetchone()
            if row:
                raise RuntimeError(f"Duplicate playlist serial detected: {row['serial_number']}")
