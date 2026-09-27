from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .metadata import normalize_isrc


@dataclass(frozen=True)
class DuplicateMatch:
    serial_number: int
    isrc: str
    title: str | None
    artist: str | None
    album: str | None
    mp3_path: str | None


def find_isrc_duplicate(
    songs_db: Any,
    *,
    isrc: str | None,
    exclude_serial: int | None = None,
) -> DuplicateMatch | None:
    """Return one retained song with the same normalized ISRC, excluding the current serial."""
    normalized = normalize_isrc(isrc)
    if not normalized:
        return None
    row = songs_db.find_by_isrc(normalized, exclude_serial=exclude_serial)
    if not row:
        return None
    return DuplicateMatch(
        serial_number=int(row["serial_number"]),
        isrc=normalized,
        title=row.get("title"),
        artist=row.get("artist"),
        album=row.get("album"),
        mp3_path=row.get("mp3_path"),
    )
