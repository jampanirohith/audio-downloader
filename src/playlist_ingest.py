from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
import json
from typing import Any, Callable


def _artists_to_list(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, list):
        for item in value:
            name = item.get("name") if isinstance(item, dict) else item
            if name not in (None, ""):
                text = str(name).strip()
                if text and text not in result:
                    result.append(text)
    elif value not in (None, ""):
        text = str(value).strip()
        if text:
            result.append(text)
    return result


def _artists_to_string(value: Any) -> str:
    return ", ".join(_artists_to_list(value))


def _duration_to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return max(0, int(round(value)))
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
        if ":" in text:
            try:
                parts = [int(p) for p in text.split(":")]
                seconds = 0
                for part in parts:
                    seconds = seconds * 60 + part
                return seconds
            except ValueError:
                return None
    return None


def _album_name(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("name")
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _build_ytm_url(video_id: str) -> str:
    return f"https://music.youtube.com/watch?v={video_id}"


def _extract_playlist_track(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one YTMusic playlist item while preserving unavailable occurrences."""
    title = str(item.get("title") or "").strip()
    if not title:
        title = "Untitled"
    artist = _artists_to_string(item.get("artists")) or _artists_to_string(item.get("artist")) or "Unknown Artist"
    album = _album_name(item.get("album"))
    video_id = item.get("videoId")
    if video_id:
        return {
            "video_id": str(video_id),
            "title": title,
            "artist": artist,
            "album": album,
            "duration": _duration_to_int(item.get("duration_seconds")) or _duration_to_int(item.get("duration")),
            "url": _build_ytm_url(str(video_id)),
            "available": item.get("isAvailable", True) is not False,
            "ingest_error": None if item.get("isAvailable", True) is not False else "YTMusic playlist entry is marked unavailable",
            "raw_json": json.dumps(item, ensure_ascii=False, sort_keys=True, default=str),
        }

    reason = "YTMusic playlist entry has no videoId"
    if item.get("isAvailable") is False:
        reason += " (entry is unavailable)"
    return {
        "video_id": None,
        "title": title,
        "artist": artist,
        "album": album,
        "duration": _duration_to_int(item.get("duration_seconds")) or _duration_to_int(item.get("duration")),
        "url": None,
        "available": False,
        "ingest_error": reason,
        "raw_json": json.dumps(item, ensure_ascii=False, sort_keys=True, default=str),
    }


def _match_existing_rows(
    existing_rows: list[dict[str, Any]], tracks: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    """Reconcile playlist occurrences while never merging song records.

    A usable YTMusic video ID is the strongest source-side occurrence reference and is
    matched globally, in the order those source IDs previously appeared. This means a
    playlist reorder does not needlessly create new serials. Repeated source IDs remain
    separate occurrences because one existing row is consumed per incoming occurrence.
    Unavailable rows with no source ID fall back to their prior position plus visible text.
    """
    by_video_id: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    by_position: dict[int, deque[dict[str, Any]]] = defaultdict(deque)
    for row in sorted(existing_rows, key=lambda item: (int(item["playlist_position"]), int(item["serial_number"]))):
        row_copy = dict(row)
        video_id = str(row_copy.get("ytm_video_id") or "").strip()
        if video_id:
            by_video_id[video_id].append(row_copy)
        else:
            by_position[int(row_copy["playlist_position"])].append(row_copy)

    used_serials: set[int] = set()
    matches: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for position, track in enumerate(tracks, start=1):
        existing = None
        video_id = str(track.get("video_id") or "").strip()
        if video_id:
            while by_video_id.get(video_id):
                candidate = by_video_id[video_id].popleft()
                serial = int(candidate["serial_number"])
                if serial not in used_serials:
                    existing = candidate
                    break
        # Position/text fallback is intentionally limited to an existing occurrence
        # that has no source ID. It lets an unavailable playlist occurrence acquire a
        # real source ID later without allocating a second permanent serial.
        candidates = by_position.get(position, deque())
        if existing is None:
            for _ in range(len(candidates)):
                candidate = candidates.popleft()
                serial = int(candidate["serial_number"])
                if serial in used_serials:
                    continue
                same_text = (
                    str(candidate.get("title") or "") == str(track.get("title") or "")
                    and str(candidate.get("artist") or "") == str(track.get("artist") or "")
                )
                if not candidate.get("ytm_video_id") and same_text:
                    existing = candidate
                    break
                candidates.append(candidate)

        if existing is not None:
            used_serials.add(int(existing["serial_number"]))
        matches.append((track, existing))
    return matches


class PlaylistIngestor:
    def __init__(
        self,
        playlist_db: Any,
        *,
        auth_file: str | Path | None = None,
        ytmusic_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.playlist_db = playlist_db
        self.auth_file = Path(auth_file) if auth_file else None
        self.ytmusic_factory = ytmusic_factory

    def _client(self) -> Any:
        factory = self.ytmusic_factory
        if factory is None:
            try:
                from ytmusicapi import YTMusic
            except ImportError as exc:
                raise RuntimeError("ytmusicapi is not installed. Install requirements.txt before running playlist ingestion.") from exc
            factory = YTMusic
        if self.auth_file:
            if not self.auth_file.exists():
                raise FileNotFoundError(f"YTMusic auth file does not exist: {self.auth_file}")
            return factory(str(self.auth_file))
        return factory()

    def fetch_playlist(self, playlist_id: str) -> dict[str, Any]:
        client = self._client()
        return client.get_playlist(playlist_id, limit=None, related=False, suggestions_limit=0)

    def fetch_tracks(self, playlist_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        playlist = self.fetch_playlist(playlist_id)
        raw_tracks = playlist.get("tracks") or []
        return playlist, [_extract_playlist_track(item) for item in raw_tracks]

    def ingest(self, playlist_id: str) -> dict[str, int]:
        playlist, tracks = self.fetch_tracks(playlist_id)
        playlist_title = str(playlist.get("title") or "").strip() or None
        existing_rows = self.playlist_db.get_all()
        matches = _match_existing_rows(existing_rows, tracks)
        next_serial = self.playlist_db.max_serial() + 1
        new_count = 0
        existing_count = 0

        for position, (track, existing) in enumerate(matches, start=1):
            is_usable = bool(track.get("video_id")) and bool(track.get("url")) and track.get("available", True)
            target_status = "pending" if is_usable else "error"
            target_error = None if is_usable else str(track.get("ingest_error") or "YTMusic playlist entry is unavailable")

            if existing is None:
                serial = next_serial
                next_serial += 1
                self.playlist_db.insert_entry(
                    serial_number=serial,
                    playlist_position=position,
                    ytm_playlist_id=playlist_id,
                    ytm_video_id=track["video_id"],
                    ytm_url=track["url"],
                    title=track["title"],
                    artist=track["artist"],
                    album=track["album"],
                    duration=track["duration"],
                    ytm_playlist_item_json=track["raw_json"],
                    status=target_status,
                    error_message=target_error,
                )
                new_count += 1
                continue

            serial = int(existing["serial_number"])
            # Never downgrade a successfully retained or intentionally deduplicated occurrence
            # merely because ingestion refreshed the same usable source item.
            existing_status = existing.get("status")
            same_source = str(existing.get("ytm_video_id") or "") == str(track.get("video_id") or "") and bool(track.get("video_id"))
            if not is_usable and existing_status == "completed" and existing.get("ytm_video_id"):
                existing_count += 1
                continue
            if is_usable and existing_status in {"completed", "duplicate"} and same_source:
                self.playlist_db.update_ingested_fields(
                    serial_number=serial, playlist_position=position, ytm_playlist_id=playlist_id,
                    ytm_video_id=track["video_id"], ytm_url=track["url"], title=track["title"],
                    artist=track["artist"], album=track["album"], duration=track["duration"],
                    ytm_playlist_item_json=track["raw_json"], status=existing_status, error_message=None,
                )
                existing_count += 1
                continue

            self.playlist_db.update_ingested_fields(
                serial_number=serial,
                playlist_position=position,
                ytm_playlist_id=playlist_id,
                ytm_video_id=track["video_id"],
                ytm_url=track["url"],
                title=track["title"],
                artist=track["artist"],
                album=track["album"],
                duration=track["duration"],
                ytm_playlist_item_json=track["raw_json"],
                status=target_status,
                error_message=target_error,
            )
            existing_count += 1

        counts = self.playlist_db.counts()
        return {
            "total_entries": len(tracks),
            "new_entries": new_count,
            "existing_entries": existing_count,
            "pending_entries": counts["pending"],
            "completed_entries": counts["completed"],
            "error_entries": counts["error"],
        }
