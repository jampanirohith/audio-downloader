from __future__ import annotations

from typing import Any

from .db_songs import SongsDB


class DuplicateChecker:
    def __init__(self, songs_db: SongsDB) -> None:
        self.songs_db = songs_db

    def find_duplicate(self, isrc: str | None) -> dict[str, Any] | None:
        # Locked Phase 1 rule: ISRC is the only duplicate key. NULL means no duplicate lookup.
        if isrc is None:
            return None
        return self.songs_db.find_by_isrc(isrc)
