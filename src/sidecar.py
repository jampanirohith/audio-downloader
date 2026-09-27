from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

SIDECAR_SCHEMA_VERSION = 1


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, bytes):
        return value.hex()
    return value


def build_song_sidecar(
    *,
    project_version: str,
    playlist_entry: Mapping[str, Any],
    metadata: Any,
    source_info: Mapping[str, Any],
    youtube_video: Any,
    youtube_search_query: str,
    spotify: Any,
    spotify_artwork: Mapping[str, Any] | None,
    lyrics: Any,
    lyrics_path: str | None,
    lyrics_status: str = "none",
    artwork: Mapping[str, Any],
    mp3_path: str,
    mp3_size: int,
    mp3_sha256: str,
    lrc_path: str | None,
    json_path: str,
    duplicate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    def obj(value: Any) -> Any:
        return _jsonable(value)

    return {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "project_version": project_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "playlist": {
            "serial_number": playlist_entry.get("serial_number"),
            "playlist_position": playlist_entry.get("playlist_position"),
            "playlist_id": playlist_entry.get("ytm_playlist_id"),
            "ytmusic_video_id": playlist_entry.get("ytm_video_id"),
            "ytmusic_url": playlist_entry.get("ytm_url"),
            "playlist_item": obj(_load_json_value(playlist_entry.get("ytm_playlist_item_json"))),
        },
        "song": {
            "normalized": obj(metadata),
            "actual_duration_seconds": metadata.duration,
        },
        "sources": {
            "yt_dlp_info_json": obj(source_info),
            "ytmusic_playlist_item": obj(_load_json_value(playlist_entry.get("ytm_playlist_item_json"))),
        },
        "spotify": {
            "matched": spotify is not None,
            "selected_result": obj(spotify) if spotify is not None else None,
            "artwork": dict(spotify_artwork or {}),
        },
        "youtube_video": {
            "search_query": youtube_search_query,
            "selected": youtube_video is not None,
            "metadata": obj(youtube_video) if youtube_video is not None else None,
        },
        "duplicate_detection": dict(duplicate or {}),
        "lyrics": {
            "status": "synced" if lyrics is not None else lyrics_status,
            "lrc_path": lrc_path,
            "embedded_in_mp3": lyrics is not None,
            "record": obj(lyrics) if lyrics is not None else None,
            "synced_lyrics": lyrics.synced_lyrics if lyrics is not None else None,
        },
        "artwork": dict(artwork),
        "files": {
            "mp3_path": mp3_path,
            "mp3_size": mp3_size,
            "mp3_sha256": mp3_sha256,
            "lrc_path": lrc_path,
            "json_path": json_path,
        },
    }


def _load_json_value(value: Any) -> Any:
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return None


def write_sidecar(path: str | Path, payload: Mapping[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def read_sidecar(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Sidecar JSON must contain an object: {path}")
    if int(value.get("schema_version", -1)) != SIDECAR_SCHEMA_VERSION:
        raise ValueError(f"Unsupported sidecar schema in {path}: {value.get('schema_version')}")
    return value
