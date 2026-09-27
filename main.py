from __future__ import annotations

import argparse
import importlib.util
import json
import logging
from pathlib import Path
import shutil
import sys
from typing import Any

from src.db_playlist import PlaylistDB
from src.db_songs import SongsDB
from src.downloader import Downloader, YTDlpInvoker
from src.pipeline import Pipeline
from src.playlist_ingest import PlaylistIngestor
from src.youtube_finder import YouTubeFinder
from src.spotify import SpotifyClient
from src.lrclib import LRCLIBClient


REQUIRED_DOWNLOAD_RULES = {
    "audio_format": "mp3",
    "audio_quality": "0",
    "write_info_json": True,
    "write_thumbnail": True,
    "convert_thumbnail": "jpg",
    "write_all_thumbnails": True,
}


def load_config(path: Path) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid config JSON: {path}: {exc}") from exc
    if not isinstance(config, dict):
        raise SystemExit("config.json must contain a JSON object")
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    paths = config.get("paths")
    if not isinstance(paths, dict):
        raise SystemExit("config.paths must be an object")
    for key in ("songs", "temp", "database"):
        if not paths.get(key):
            raise SystemExit(f"config.paths.{key} is required")
    for key in ("songs_with_synced_lyrics", "songs_without_synced_lyrics"):
        if paths.get(key) is not None and not str(paths.get(key)).strip():
            raise SystemExit(f"config.paths.{key} cannot be empty")

    download = config.get("download")
    if not isinstance(download, dict):
        raise SystemExit("config.download must be an object")
    for key, expected in REQUIRED_DOWNLOAD_RULES.items():
        if download.get(key) != expected:
            raise SystemExit(f"download.{key} must remain {expected!r}")

    artwork = config.get("artwork", {})
    if not isinstance(artwork, dict):
        raise SystemExit("config.artwork must be an object")
    if int(artwork.get("max_dimension", 1200)) < 1:
        raise SystemExit("config.artwork.max_dimension must be >= 1")
    if not 1 <= int(artwork.get("jpeg_quality", 98)) <= 100:
        raise SystemExit("config.artwork.jpeg_quality must be 1..100")

    search = config.get("youtube_video_search")
    if not isinstance(search, dict):
        raise SystemExit("youtube_video_search must be an object")
    if int(search.get("results_to_fetch", 0)) < 1:
        raise SystemExit("youtube_video_search.results_to_fetch must be >= 1")
    if str(search.get("skip_title_keyword", "")).lower() != "lyrics":
        raise SystemExit("youtube_video_search.skip_title_keyword must be 'lyrics'")

    spotify = config.get("spotify", {})
    if not isinstance(spotify, dict):
        raise SystemExit("config.spotify must be an object")
    if int(spotify.get("search_limit", 10)) < 1 or int(spotify.get("search_limit", 10)) > 50:
        raise SystemExit("spotify.search_limit must be 1..50")
    if int(spotify.get("duration_tolerance_seconds", 2)) < 0:
        raise SystemExit("spotify.duration_tolerance_seconds must be >= 0")
    if int(spotify.get("timeout_seconds", 30)) < 5:
        raise SystemExit("spotify.timeout_seconds must be >= 5")

    spotify_artwork = spotify.get("artwork", {})
    if not isinstance(spotify_artwork, dict):
        raise SystemExit("spotify.artwork must be an object")
    if int(spotify_artwork.get("max_dimension", 0)) < 0:
        raise SystemExit("spotify.artwork.max_dimension must be >= 0 (0 means original maximum)")
    if not 1 <= int(spotify_artwork.get("jpeg_quality", 100)) <= 100:
        raise SystemExit("spotify.artwork.jpeg_quality must be 1..100")
    lyrics = config.get("lyrics", {})
    if not isinstance(lyrics, dict):
        raise SystemExit("config.lyrics must be an object")
    if int(lyrics.get("timeout_seconds", 30)) < 5:
        raise SystemExit("lyrics.timeout_seconds must be >= 5")
    if float(lyrics.get("request_delay_seconds", 0.35)) < 0.2:
        raise SystemExit("lyrics.request_delay_seconds must be >= 0.2")
    if str(lyrics.get("endpoint", "/api/get")) != "/api/get":
        raise SystemExit("lyrics.endpoint must remain /api/get")

    retry = config.get("retry", {})
    if not isinstance(retry, dict) or int(retry.get("max_attempts", 1)) < 1:
        raise SystemExit("retry.max_attempts must be >= 1")
    if float(retry.get("backoff_seconds", 0)) < 0:
        raise SystemExit("retry.backoff_seconds must be >= 0")


def resolve_path(root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else root / path


def setup_logger(root: Path, config: dict[str, Any]) -> logging.Logger:
    logs_dir = resolve_path(root, config.get("paths", {}).get("logs", "logs")) or (root / "logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("phase1")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    file_handler = logging.FileHandler(logs_dir / "phase1.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(stream)
    logger.addHandler(file_handler)
    return logger


def make_components(root: Path, config: dict[str, Any], logger: logging.Logger):
    db_dir = resolve_path(root, config["paths"]["database"])
    assert db_dir is not None
    db_dir.mkdir(parents=True, exist_ok=True)
    playlist_db = PlaylistDB(db_dir / "playlist.db")
    songs_db = SongsDB(db_dir / "songs.db")
    auth_file = resolve_path(root, config.get("ytmusic_auth_file"))
    ingestor = PlaylistIngestor(playlist_db, auth_file=auth_file)
    downloader = Downloader(config, root)
    youtube_finder = YouTubeFinder(config, root)
    spotify_cfg = config.get("spotify", {}) if isinstance(config.get("spotify", {}), dict) else {}
    spotify_client = SpotifyClient(spotify_cfg) if bool(spotify_cfg.get("enabled", False)) else None
    lyrics_cfg = config.get("lyrics", {}) if isinstance(config.get("lyrics", {}), dict) else {}
    lrclib_client = LRCLIBClient(lyrics_cfg) if bool(lyrics_cfg.get("enabled", True)) else None
    pipeline = Pipeline(
        project_root=root,
        config=config,
        playlist_db=playlist_db,
        songs_db=songs_db,
        downloader=downloader,
        youtube_finder=youtube_finder,
        spotify_client=spotify_client,
        lrclib_client=lrclib_client,
        logger=logger,
    )
    return playlist_db, songs_db, pipeline, ingestor


def command_doctor(root: Path, config: dict[str, Any]) -> int:
    errors: list[str] = []
    for module_name, display_name in (
        ("ytmusicapi", "ytmusicapi"),
        ("yt_dlp", "yt-dlp"),
        ("mutagen", "mutagen"),
        ("requests", "requests"),
        ("PIL", "Pillow"),
    ):
        if importlib.util.find_spec(module_name) is None:
            errors.append(f"Missing Python dependency: {display_name}")
        else:
            print(f"Python package: {display_name} OK")
    if sys.version_info < (3, 11):
        errors.append(f"Python 3.11+ required; found {sys.version.split()[0]}")
    for executable in ("ffmpeg", "ffprobe"):
        path = shutil.which(executable)
        if path:
            print(f"Executable: {executable} -> {path}")
        else:
            errors.append(f"Missing executable: {executable}")
    spotify_cfg = config.get("spotify", {}) if isinstance(config.get("spotify", {}), dict) else {}
    if bool(spotify_cfg.get("enabled", False)):
        client = SpotifyClient(spotify_cfg)
        if client.configured:
            print("Spotify enrichment: enabled and credentials configured")
        else:
            errors.append("Spotify enrichment is enabled but client_id/client_secret are not configured")
    else:
        print("Spotify enrichment: disabled")
    lyrics_cfg = config.get("lyrics", {}) if isinstance(config.get("lyrics", {}), dict) else {}
    print(f"LRCLIB synced lyrics: {'enabled' if bool(lyrics_cfg.get('enabled', True)) else 'disabled'}")

    try:
        invoker = YTDlpInvoker(config, root)
        runtime_args = invoker.runtime_args()
        print(f"yt-dlp JavaScript runtime args: {runtime_args or 'none'}")
        if not runtime_args:
            errors.append("No supported yt-dlp JavaScript runtime detected (Deno/Node/QuickJS)")
    except Exception as exc:
        errors.append(str(exc))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Doctor: OK")
    return 0


def print_status(playlist_db: PlaylistDB, songs_db: SongsDB) -> None:
    counts = playlist_db.counts()
    for key in ("total", "pending", "completed", "error"):
        print(f"{key:10s}: {counts[key]}")
    print(f"Retained songs: {songs_db.count()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube Music playlist downloader/enricher")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--ingest-only", action="store_true")
    parser.add_argument("--no-ingest", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--check-invariants", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    config = load_config(config_path)
    logger = setup_logger(root, config)
    playlist_db, songs_db, pipeline, ingestor = make_components(root, config, logger)

    if args.doctor:
        return command_doctor(root, config)
    if args.status:
        print_status(playlist_db, songs_db)
        return 0
    if args.check_invariants:
        errors = pipeline.check_invariants()
        if errors:
            for error in errors:
                print(f"INVARIANT ERROR: {error}")
            return 1
        print("Invariants: OK")
        return 0

    if args.retry_errors:
        changed = playlist_db.retry_all_errors()
        print(f"Retry queue: {changed} error entries returned to pending.")

    if config.get("ytmusic_playlist_id") in (None, "", "YOUR_PLAYLIST_ID") and (not args.no_ingest or args.ingest_only):
        raise SystemExit("Set config.json -> ytmusic_playlist_id before playlist ingestion.")

    playlist_id = str(config.get("ytmusic_playlist_id") or "").strip()
    if not args.no_ingest:
        summary = ingestor.ingest(playlist_id)
        print(json.dumps(summary, indent=2))
        if args.ingest_only:
            return 0

    result = pipeline.run(max_entries=args.limit)
    print(json.dumps(result, indent=2))
    return 0 if result["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
