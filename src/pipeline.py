from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any, Callable, Mapping

from .db_playlist import PlaylistDB
from .db_songs import SONG_COLUMNS, SongsDB
from .downloader import AcquisitionResult, Downloader
from .embedder import embed_final_mp3
from .artwork import ArtworkError, download_spotify_artwork
from .hashing import hash_file
from .metadata import NormalizedMetadata, dump_json, load_info_json, normalize_metadata
from .spotify import SpotifyResult, apply_spotify_metadata
from .lrclib import LyricsResult
from .sidecar import build_song_sidecar, write_sidecar
from .validator import validate_final_mp3
from .youtube_finder import VideoResult, YouTubeFinder


@dataclass(frozen=True)
class ProcessOutcome:
    serial_number: int
    status: str
    attempts: int


class PipelineError(RuntimeError):
    pass


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_WINDOWS_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_filename_component(value: str, fallback: str) -> str:
    text = value.strip() or fallback
    text = INVALID_FILENAME_CHARS.sub("_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        text = fallback
    if text.upper() in RESERVED_WINDOWS_NAMES:
        text = f"_{text}_"
    return text[:180]


class DatabaseCoordinator:
    """Commit retained-song insertion and playlist completion together across the two SQLite files."""

    def __init__(self, playlist_db: PlaylistDB, songs_db: SongsDB) -> None:
        self.playlist_db = playlist_db
        self.songs_db = songs_db

    def _connect(self):
        import sqlite3
        conn = sqlite3.connect(self.playlist_db.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("ATTACH DATABASE ? AS songsdb", (str(self.songs_db.path),))
        return conn

    def commit_song_and_complete(self, song_record: Mapping[str, Any]) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM songsdb.songs WHERE serial_number=?", (int(song_record["serial_number"]),)).fetchone():
                raise PipelineError(f"songs.db already contains serial {song_record['serial_number']}")
            columns = list(SONG_COLUMNS)
            placeholders = ", ".join("?" for _ in columns)
            conn.execute(
                f"INSERT INTO songsdb.songs ({', '.join(columns)}) VALUES ({placeholders})",
                [song_record.get(column) for column in columns],
            )
            cur = conn.execute(
                """
                UPDATE main.playlist_entries
                SET status='completed', error_message=NULL, updated_at=CURRENT_TIMESTAMP
                WHERE serial_number=? AND status='pending'
                """,
                (int(song_record["serial_number"]),),
            )
            if cur.rowcount != 1:
                raise PipelineError("Playlist entry was not pending during completion commit")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


class Pipeline:
    def __init__(
        self,
        *, project_root: str | Path,
        config: Mapping[str, Any],
        playlist_db: PlaylistDB,
        songs_db: SongsDB,
        downloader: Downloader,
        youtube_finder: YouTubeFinder,
        spotify_client: Any = None,
        lrclib_client: Any = None,
        validator_func: Callable[..., None] = validate_final_mp3,
        embedder_func: Callable[..., None] = embed_final_mp3,
        logger: logging.Logger | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.config = config
        self.playlist_db = playlist_db
        self.songs_db = songs_db
        self.downloader = downloader
        self.youtube_finder = youtube_finder
        self.spotify_client = spotify_client
        self.lrclib_client = lrclib_client
        self.validator_func = validator_func
        self.embedder_func = embedder_func
        self.logger = logger or logging.getLogger("phase1.pipeline")
        self.coordinator = DatabaseCoordinator(playlist_db, songs_db)
        paths = config["paths"]
        self.songs_dir = self.project_root / paths["songs"]
        self.synced_songs_dir = self.project_root / paths.get("songs_with_synced_lyrics", "songs/synced_lyrics")
        self.unsynced_songs_dir = self.project_root / paths.get("songs_without_synced_lyrics", "songs/no_synced_lyrics")
        self.temp_root = self.project_root / paths["temp"]
        self.songs_dir.mkdir(parents=True, exist_ok=True)
        self.synced_songs_dir.mkdir(parents=True, exist_ok=True)
        self.unsynced_songs_dir.mkdir(parents=True, exist_ok=True)
        self.temp_root.mkdir(parents=True, exist_ok=True)

    def _temp_dir(self, serial: int) -> Path:
        return self.temp_root / str(serial)

    def _manifest_path(self, serial: int) -> Path:
        return self._temp_dir(serial) / "manifest.json"

    def _write_manifest(self, serial: int, **changes: Any) -> None:
        path = self._manifest_path(serial)
        state: dict[str, Any] = {}
        if path.exists():
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                state = {}
        state.update(changes)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def _cleanup_temp(self, serial: int) -> None:
        shutil.rmtree(self._temp_dir(serial), ignore_errors=False)

    def _resolve_project_path(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else self.project_root / p

    def _final_filename(self, serial: int, metadata: NormalizedMetadata) -> str:
        prefix = f"{serial:03d}_"
        title = safe_filename_component(metadata.title, "untitled")
        artist = safe_filename_component(metadata.artist, "unknown-artist")
        max_stem_length = int(self.config.get("filesystem", {}).get("max_filename_length", 180))
        max_stem_length = max(64, min(max_stem_length, 240))
        budget = max_stem_length - len(prefix) - 1  # final separator between title and artist
        title_budget = max(20, budget // 2)
        artist_budget = max(20, budget - title_budget)
        if title_budget + artist_budget > budget:
            artist_budget = max(1, budget - title_budget)
        if title_budget < 1:
            title_budget = 1
        if artist_budget < 1:
            artist_budget = 1
        title = title[:title_budget].rstrip(" ._") or "untitled"
        artist = artist[:artist_budget].rstrip(" ._") or "unknown-artist"
        stem = f"{prefix}{title}_{artist}"
        extension = ".mp3"
        max_total_length = max_stem_length
        if len(stem) + len(extension) > max_total_length:
            stem = stem[: max_total_length - len(extension)].rstrip(" ._")
        return stem + extension

    def _playlist_song_record(
        self, *, entry: Mapping[str, Any], metadata: NormalizedMetadata, video: VideoResult | None,
        final_path: Path, size: int, sha256: str, artwork_source_url: str | None,
        artwork_width: int | None, artwork_height: int | None, artwork_provider: str | None, artwork_mime_type: str | None, metadata_json_path: str | None, query: str,
        spotify: SpotifyResult | None = None, lyrics: LyricsResult | None = None,
        lyrics_path: Path | None = None, lyrics_status: str = "none",
    ) -> dict[str, Any]:
        relative_mp3 = final_path.relative_to(self.project_root).as_posix()
        return {
            "serial_number": int(entry["serial_number"]),
            "ytm_playlist_id": entry.get("ytm_playlist_id"),
            "title": metadata.title,
            "title_original": metadata.title_original,
            "primary_artist": metadata.primary_artist,
            "artist": metadata.artist,
            "artists_json": dump_json(metadata.artists),
            "album": metadata.album,
            "album_artist": metadata.album_artist,
            "track_number": metadata.track_number,
            "disc_number": metadata.disc_number,
            "release_date": metadata.release_date,
            "release_date_source": metadata.release_date_source,
            "upload_date": metadata.upload_date,
            "upload_timestamp": metadata.upload_timestamp,
            "release_timestamp": metadata.release_timestamp,
            "modified_date": metadata.modified_date,
            "modified_timestamp": metadata.modified_timestamp,
            "description": metadata.description,
            "genre": metadata.genre,
            "composer": metadata.composer,
            "publisher": metadata.publisher,
            "copyright": metadata.copyright,
            "license": metadata.license,
            "comment": metadata.comment,
            "language": metadata.language,
            "bpm": metadata.bpm,
            "compilation": int(metadata.compilation) if metadata.compilation is not None else None,
            "encoder": metadata.encoder,
            "duration": metadata.duration,
            "source_duration": metadata.source_duration,
            "source_ext": metadata.source_ext,
            "source_container": metadata.source_container,
            "source_codec": metadata.source_codec,
            "source_format_id": metadata.source_format_id,
            "source_format_note": metadata.source_format_note,
            "source_bitrate": metadata.source_bitrate,
            "source_sample_rate": metadata.source_sample_rate,
            "source_channels": metadata.source_channels,
            "source_filesize": metadata.source_filesize,
            "source_filesize_approx": metadata.source_filesize_approx,
            "source_language": metadata.source_language,
            "source_video_id": metadata.source_video_id,
            "source_webpage_url": metadata.source_webpage_url,
            "source_original_url": metadata.source_original_url,
            "source_display_id": metadata.source_display_id,
            "source_webpage_url_basename": metadata.source_webpage_url_basename,
            "source_webpage_url_domain": metadata.source_webpage_url_domain,
            "source_extractor": metadata.source_extractor,
            "source_extractor_key": metadata.source_extractor_key,
            "source_channel": metadata.source_channel,
            "source_channel_id": metadata.source_channel_id,
            "source_channel_url": metadata.source_channel_url,
            "source_channel_follower_count": metadata.source_channel_follower_count,
            "source_channel_is_verified": int(metadata.source_channel_is_verified) if metadata.source_channel_is_verified is not None else None,
            "source_uploader": metadata.source_uploader,
            "source_uploader_id": metadata.source_uploader_id,
            "source_uploader_url": metadata.source_uploader_url,
            "source_views": metadata.source_views,
            "source_location": metadata.source_location,
            "source_availability": metadata.source_availability,
            "source_age_limit": metadata.source_age_limit,
            "source_live_status": metadata.source_live_status,
            "source_media_type": metadata.source_media_type,
            "source_thumbnail": metadata.source_thumbnail,
            "source_thumbnails_json": dump_json(metadata.source_thumbnails),
            "source_categories_json": dump_json(metadata.source_categories),
            "source_tags_json": dump_json(metadata.source_tags),
            "source_playlist": metadata.source_playlist,
            "source_playlist_id": metadata.source_playlist_id,
            "source_playlist_count": metadata.source_playlist_count,
            "source_playlist_index": metadata.source_playlist_index,
            "source_playlist_uploader": metadata.source_playlist_uploader,
            "source_playlist_uploader_id": metadata.source_playlist_uploader_id,
            "source_playlist_channel": metadata.source_playlist_channel,
            "source_playlist_channel_id": metadata.source_playlist_channel_id,
            "source_playlist_webpage_url": metadata.source_playlist_webpage_url,
            "ytm_video_id": entry.get("ytm_video_id"),
            "ytm_url": entry.get("ytm_url"),
            "ytm_playlist_item_json": entry.get("ytm_playlist_item_json"),
            "source_info_json": dump_json(metadata.raw),
            "mp3_path": relative_mp3,
            "mp3_size": size,
            "mp3_sha256": sha256,
            "yt_video_id": video.video_id if video else None,
            "yt_video_url": video.video_url if video else None,
            "yt_video_title": video.title if video else None,
            "yt_video_fulltitle": video.fulltitle if video else None,
            "yt_video_alt_title": video.alt_title if video else None,
            "yt_video_channel": video.channel if video else None,
            "yt_video_channel_id": video.channel_id if video else None,
            "yt_video_uploader": video.uploader if video else None,
            "yt_video_uploader_id": video.uploader_id if video else None,
            "yt_video_upload_date": video.upload_date if video else None,
            "yt_video_timestamp": video.timestamp if video else None,
            "yt_video_release_date": video.release_date if video else None,
            "yt_video_release_timestamp": video.release_timestamp if video else None,
            "yt_video_duration": video.duration if video else None,
            "yt_video_views": video.views if video else None,
            "yt_video_likes": video.likes if video else None,
            "yt_video_comments": video.comments if video else None,
            "yt_video_thumbnail": video.thumbnail if video else None,
            "yt_video_description": video.description if video else None,
            "yt_video_categories_json": dump_json(video.categories) if video else None,
            "yt_video_tags_json": dump_json(video.tags) if video else None,
            "yt_video_extractor": video.extractor if video else None,
            "yt_video_extractor_key": video.extractor_key if video else None,
            "yt_video_info_json": dump_json(video.raw) if video else None,
            "yt_video_search_query": query,
            "yt_video_search_result_index": video.search_result_index if video else None,
            "yt_video_search_results_fetched": video.search_results_fetched if video else None,
            "yt_video_match_method": video.match_method if video else None,
            "artwork_source_url": artwork_source_url,
            "artwork_width": artwork_width,
            "artwork_height": artwork_height,
            "artwork_path": None,  # The artwork is embedded in the MP3; source provenance is in sidecar JSON.
            "artwork_provider": artwork_provider,
            "artwork_mime_type": artwork_mime_type,
            "metadata_json_path": metadata_json_path,
            "spotify_track_id": spotify.track_id if spotify else None,
            "spotify_track_name": spotify.track_name if spotify else None,
            "spotify_track_url": spotify.track_url if spotify else None,
            "spotify_uri": spotify.uri if spotify else None,
            "spotify_artists_json": dump_json(spotify.artists) if spotify else None,
            "spotify_artist_ids_json": dump_json(spotify.artist_ids) if spotify else None,
            "spotify_artist_urls_json": dump_json(spotify.artist_urls) if spotify else None,
            "spotify_album_id": spotify.album_id if spotify else None,
            "spotify_album_name": spotify.album_name if spotify else None,
            "spotify_album_url": spotify.album_url if spotify else None,
            "spotify_album_type": spotify.album_type if spotify else None,
            "spotify_album_release_date": spotify.album_release_date if spotify else None,
            "spotify_album_release_precision": spotify.album_release_precision if spotify else None,
            "spotify_album_total_tracks": spotify.album_total_tracks if spotify else None,
            "spotify_album_artwork_url": spotify.album_artwork_url if spotify else None,
            "spotify_album_artwork_width": spotify.album_artwork_width if spotify else None,
            "spotify_album_artwork_height": spotify.album_artwork_height if spotify else None,
            "spotify_album_label": spotify.album_label if spotify else None,
            "spotify_album_copyrights_json": dump_json(spotify.album_copyrights) if spotify else None,
            "spotify_duration_ms": spotify.duration_ms if spotify else None,
            "spotify_duration_seconds": spotify.duration_seconds if spotify else None,
            "spotify_duration_delta_ms": spotify.duration_delta_ms if spotify else None,
            "spotify_explicit": int(spotify.explicit) if spotify and spotify.explicit is not None else None,
            "spotify_popularity": spotify.popularity if spotify else None,
            "spotify_isrc": spotify.isrc if spotify else None,
            "spotify_track_number": spotify.track_number if spotify else None,
            "spotify_disc_number": spotify.disc_number if spotify else None,
            "spotify_search_query": spotify.search_query if spotify else None,
            "spotify_search_result_index": spotify.search_result_index if spotify else None,
            "spotify_raw_json": dump_json(spotify.raw) if spotify else None,
            "spotify_album_raw_json": dump_json(spotify.album_raw) if spotify else None,
            "lyrics_status": lyrics_status,
            "lyrics_path": lyrics_path.relative_to(self.project_root).as_posix() if lyrics_path else None,
            "lrclib_id": lyrics.lyrics_id if lyrics else None,
            "lrclib_track_name": lyrics.track_name if lyrics else None,
            "lrclib_artist_name": lyrics.artist_name if lyrics else None,
            "lrclib_album_name": lyrics.album_name if lyrics else None,
            "lrclib_duration": lyrics.duration if lyrics else None,
            "lrclib_duration_delta_seconds": lyrics.duration_delta_seconds if lyrics else None,
            "lrclib_match_method": lyrics.match_method if lyrics else None,
            "lrclib_raw_json": dump_json(lyrics.raw) if lyrics else None,
            "lyrics_embedded": int(lyrics is not None),
        }

    def _cleanup_previous_serial_files(self, serial: int, keep: set[Path]) -> None:
        """Remove orphaned artifacts from an older folder assignment for this serial."""
        for root in (self.songs_dir, self.synced_songs_dir, self.unsynced_songs_dir):
            if not root.exists():
                continue
            for path in root.glob(f"{serial:03d}_*"):
                if path in keep or path.is_dir():
                    continue
                try:
                    path.unlink()
                except OSError:
                    self.logger.warning("serial=%s could not remove old artifact: %s", serial, path)

    def _process_entry_once(self, entry: Mapping[str, Any], *, mark_error: bool = True) -> str:
        serial = int(entry["serial_number"])
        temp_dir = self._temp_dir(serial)
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        self._write_manifest(serial, serial_number=serial, stage="created")
        final_path: Path | None = None
        final_json_path: Path | None = None
        final_lyrics_path: Path | None = None
        committed = False

        try:
            if not entry.get("ytm_url"):
                raise PipelineError("Playlist entry is not currently downloadable: YTMusic returned no usable videoId/URL")

            acquisition = self.downloader.acquire(temp_dir=temp_dir, ytm_url=str(entry["ytm_url"]))
            selected_artwork_path = acquisition.artwork_jpg
            selected_artwork_source_url = acquisition.artwork_source_url
            selected_artwork_width = acquisition.artwork_width
            selected_artwork_height = acquisition.artwork_height
            artwork_provider = "ytmusic"
            artwork_mime_type = "image/jpeg"
            spotify_artwork_info: dict[str, Any] = {}

            self._write_manifest(
                serial, stage="acquired",
                artwork_source_url=acquisition.artwork_source_url,
                artwork_width=acquisition.artwork_width,
                artwork_height=acquisition.artwork_height,
            )
            info = load_info_json(acquisition.info_json)
            playlist_item = json.loads(entry["ytm_playlist_item_json"]) if entry.get("ytm_playlist_item_json") else None
            metadata = normalize_metadata(
                info, playlist_item=playlist_item, actual_duration=acquisition.duration_seconds
            )
            self._write_manifest(serial, stage="metadata_normalized")

            spotify_result: SpotifyResult | None = None
            spotify_cfg = self.config.get("spotify", {})
            if bool(spotify_cfg.get("enabled", False)) and self.spotify_client is not None:
                try:
                    spotify_result = self.spotify_client.search_track(
                        title=metadata.title, album=metadata.album, duration_seconds=metadata.duration,
                    )
                    if spotify_result:
                        metadata = apply_spotify_metadata(metadata, spotify_result)
                        self._write_manifest(
                            serial, stage="spotify_matched",
                            spotify_track_id=spotify_result.track_id,
                            spotify_isrc=spotify_result.isrc,
                            spotify_duration_delta_ms=spotify_result.duration_delta_ms,
                        )

                        art_cfg = spotify_cfg.get("artwork", {}) if isinstance(spotify_cfg.get("artwork", {}), Mapping) else {}
                        if bool(art_cfg.get("enabled", True)) and spotify_result.album_images:
                            spotify_art_path = temp_dir / "spotify_artwork.jpg"
                            try:
                                _, sp_url, sp_width, sp_height, sp_mime = download_spotify_artwork(
                                    spotify_result.album_images,
                                    spotify_art_path,
                                    timeout_seconds=int(art_cfg.get("timeout_seconds", 30)),
                                )
                                selected_artwork_path = spotify_art_path
                                selected_artwork_source_url = sp_url
                                selected_artwork_width = sp_width
                                selected_artwork_height = sp_height
                                artwork_mime_type = sp_mime
                                artwork_provider = "spotify"
                                artwork_size, artwork_sha256 = hash_file(spotify_art_path)
                                spotify_artwork_info = {
                                    "used_as_embedded_cover": True,
                                    "source_url": sp_url,
                                    "width": sp_width,
                                    "height": sp_height,
                                    "mime_type": sp_mime,
                                    "sha256": artwork_sha256,
                                    "size": artwork_size,
                                    "available_images": [
                                        {"url": image.url, "width": image.width, "height": image.height}
                                        for image in spotify_result.album_images
                                    ],
                                }
                                self._write_manifest(
                                    serial, stage="spotify_artwork_selected",
                                    spotify_artwork_source_url=sp_url,
                                    spotify_artwork_width=sp_width,
                                    spotify_artwork_height=sp_height,
                                    spotify_artwork_mime_type=sp_mime,
                                )
                            except Exception as art_exc:
                                if bool(art_cfg.get("fail_on_error", False)):
                                    raise
                                self.logger.warning("serial=%s Spotify artwork unavailable; using YTMusic artwork: %s", serial, art_exc)
                                spotify_artwork_info = {
                                    "used_as_embedded_cover": False,
                                    "error": f"{type(art_exc).__name__}: {art_exc}",
                                    "available_images": [
                                        {"url": image.url, "width": image.width, "height": image.height}
                                        for image in spotify_result.album_images
                                    ],
                                }
                    else:
                        self.logger.info("serial=%s no Spotify result matched title+album+duration", serial)
                except Exception as exc:
                    if bool(spotify_cfg.get("fail_on_error", False)):
                        raise
                    self.logger.warning("serial=%s Spotify enrichment skipped: %s", serial, exc)
                    self._write_manifest(serial, spotify_error=f"{type(exc).__name__}: {exc}")

            query, video = self.youtube_finder.find(title=metadata.title, album=metadata.album)
            self._write_manifest(serial, stage="youtube_selected", youtube_query=query, yt_video_id=video.video_id if video else None)

            lyrics_result: LyricsResult | None = None
            lyrics_status = "none"
            lyrics_temp_path: Path | None = None
            lyrics_cfg = self.config.get("lyrics", {})
            if bool(lyrics_cfg.get("enabled", True)) and self.lrclib_client is not None:
                try:
                    alternate_signatures: list[tuple[str, str, str | None, int | None]] = []
                    # If Spotify changed the display metadata, also ask LRCLIB with the
                    # original YTMusic/yt-dlp signature. Both attempts use /api/get only.
                    original_album = normalize_metadata(
                        info, playlist_item=playlist_item, actual_duration=acquisition.duration_seconds
                    )
                    if (original_album.title, original_album.artist, original_album.album, original_album.duration) != (
                        metadata.title, metadata.artist, metadata.album, metadata.duration
                    ):
                        alternate_signatures.append((original_album.title, original_album.artist, original_album.album, original_album.duration))
                    lyrics_result = self.lrclib_client.get_synced(
                        title=metadata.title,
                        artist=metadata.artist,
                        album=metadata.album,
                        duration_seconds=metadata.duration,
                        alternate_signatures=alternate_signatures,
                    )
                    if lyrics_result:
                        lyrics_status = "synced"
                        lyrics_temp_path = temp_dir / "lyrics.lrc"
                        lyrics_temp_path.write_text(lyrics_result.synced_lyrics, encoding="utf-8", newline="\n")
                        self._write_manifest(
                            serial, stage="lyrics_found", lyrics_id=lyrics_result.lyrics_id, lyrics_status=lyrics_status
                        )
                    else:
                        self._write_manifest(serial, stage="lyrics_not_found", lyrics_status="none")
                except Exception as exc:
                    lyrics_status = "error"
                    if bool(lyrics_cfg.get("fail_on_error", False)):
                        raise
                    self.logger.warning("serial=%s LRCLIB /api/get skipped: %s", serial, exc)
                    self._write_manifest(serial, lyrics_error=f"{type(exc).__name__}: {exc}", lyrics_status=lyrics_status)

            filename = self._final_filename(serial, metadata)
            target_song_dir = self.synced_songs_dir if lyrics_status == "synced" else self.unsynced_songs_dir
            final_path = target_song_dir / filename
            final_json_path = final_path.with_suffix(".json")
            temp_final = target_song_dir / f"{filename}.tmp"
            temp_final.unlink(missing_ok=True)
            final_json_path.unlink(missing_ok=True)

            relative_json = final_json_path.relative_to(self.project_root).as_posix()
            relative_lrc = final_path.with_suffix(".lrc").relative_to(self.project_root).as_posix() if lyrics_result else None
            self.embedder_func(
                source_mp3=acquisition.master_mp3,
                output_mp3=temp_final,
                playlist_entry=entry,
                metadata=metadata,
                video=video,
                artwork_path=selected_artwork_path,
                artwork_source_url=selected_artwork_source_url,
                artwork_width=selected_artwork_width,
                artwork_height=selected_artwork_height,
                artwork_mime_type=artwork_mime_type,
                max_description_chars=0,
                youtube_search_query=query,
                spotify=spotify_result,
                lyrics=lyrics_result,
                lyrics_path=relative_lrc,
                lyrics_status=lyrics_status,
                metadata_json_path=relative_json,
                artwork_provider=artwork_provider,
            )
            self._write_manifest(serial, stage="final_tagged")

            if lyrics_result is not None and lyrics_temp_path is not None:
                final_lyrics_path = final_path.with_suffix(".lrc")
                lyrics_temp_final = Path(f"{final_lyrics_path}.tmp")
                lyrics_temp_final.unlink(missing_ok=True)
                os.replace(lyrics_temp_path, lyrics_temp_final)
                os.replace(lyrics_temp_final, final_lyrics_path)

            self.validator_func(
                path=temp_final,
                playlist_entry=entry,
                metadata=metadata,
                video=video,
                youtube_search_query=query,
                artwork_source_url=selected_artwork_source_url,
                artwork_width=selected_artwork_width,
                artwork_height=selected_artwork_height,
                artwork_mime_type=artwork_mime_type,
                spotify=spotify_result,
                lyrics=lyrics_result,
                lyrics_path=(final_lyrics_path.relative_to(self.project_root) if final_lyrics_path else None),
                lyrics_file_path=final_lyrics_path,
                lyrics_status=lyrics_status,
            )
            self._write_manifest(serial, stage="final_validated")
            size, digest = hash_file(temp_final)

            # Build the sidecar before promotion. It is the canonical home for the detailed
            # source/API metadata that should not clutter the MP3's player-facing ID3 tags.
            json_payload = build_song_sidecar(
                project_version="2.0",
                playlist_entry=entry,
                metadata=metadata,
                source_info=info,
                youtube_video=video,
                youtube_search_query=query,
                spotify=spotify_result,
                spotify_artwork=spotify_artwork_info,
                lyrics=lyrics_result,
                lyrics_path=relative_lrc,
                lyrics_status=lyrics_status,
                artwork={
                    "provider": artwork_provider,
                    "source_url": selected_artwork_source_url,
                    "width": selected_artwork_width,
                    "height": selected_artwork_height,
                    "mime_type": artwork_mime_type,
                    "file_size": hash_file(selected_artwork_path)[0],
                    "sha256": hash_file(selected_artwork_path)[1],
                    "ytmusic_fallback_source_url": acquisition.artwork_source_url,
                    "ytmusic_fallback_width": acquisition.artwork_width,
                    "ytmusic_fallback_height": acquisition.artwork_height,
                },
                mp3_path=final_path.relative_to(self.project_root).as_posix(),
                mp3_size=size,
                mp3_sha256=digest,
                lrc_path=relative_lrc,
                json_path=relative_json,
            )
            write_sidecar(final_json_path, json_payload)
            self._write_manifest(
                serial, stage="sidecar_written", mp3_size=size, mp3_sha256=digest, metadata_json_path=relative_json
            )

            os.replace(temp_final, final_path)
            self._write_manifest(
                serial,
                stage="final_renamed",
                final_path=final_path.relative_to(self.project_root).as_posix(),
                lyrics_path=relative_lrc,
                json_path=relative_json,
            )

            record = self._playlist_song_record(
                entry=entry,
                metadata=metadata,
                video=video,
                final_path=final_path,
                size=size,
                sha256=digest,
                artwork_source_url=selected_artwork_source_url,
                artwork_width=selected_artwork_width,
                artwork_height=selected_artwork_height,
                artwork_provider=artwork_provider,
                artwork_mime_type=artwork_mime_type,
                metadata_json_path=relative_json,
                query=query,
                spotify=spotify_result,
                lyrics=lyrics_result,
                lyrics_path=final_lyrics_path,
                lyrics_status=lyrics_status,
            )
            self.coordinator.commit_song_and_complete(record)
            committed = True
            self._write_manifest(serial, stage="database_committed")

            keep = {final_path, final_json_path}
            if final_lyrics_path is not None:
                keep.add(final_lyrics_path)
            self._cleanup_previous_serial_files(serial, keep=keep)
            try:
                self._cleanup_temp(serial)
            except Exception:
                self.logger.exception("serial=%s final temp cleanup failed after successful commit", serial)
            return "completed"
        except Exception as exc:
            self.logger.exception("serial=%s processing failed", serial)
            if final_path is not None and final_path.exists() and not committed:
                final_path.unlink(missing_ok=True)
            if final_json_path is not None and final_json_path.exists() and not committed:
                final_json_path.unlink(missing_ok=True)
            if final_lyrics_path is not None and final_lyrics_path.exists() and not committed:
                final_lyrics_path.unlink(missing_ok=True)
            for song_root in (self.songs_dir, self.synced_songs_dir, self.unsynced_songs_dir):
                for orphan_tmp in song_root.glob(f"{serial:03d}_*.mp3.tmp"):
                    orphan_tmp.unlink(missing_ok=True)
                for orphan_lrc in song_root.glob(f"{serial:03d}_*.lrc.tmp"):
                    orphan_lrc.unlink(missing_ok=True)
                for orphan_json in song_root.glob(f"{serial:03d}_*.json.tmp"):
                    orphan_json.unlink(missing_ok=True)
            if mark_error:
                try:
                    self.playlist_db.update_status(serial, "error", error_message=f"{type(exc).__name__}: {exc}")
                except Exception:
                    self.logger.exception("serial=%s could not persist error state", serial)
            return "error"

    def process_one(self) -> ProcessOutcome | None:
        entry = self.playlist_db.get_next_pending()
        if entry is None:
            return None
        serial = int(entry["serial_number"])
        retry_cfg = self.config.get("retry", {})
        max_attempts = max(1, int(retry_cfg.get("max_attempts", 1)))
        backoff_seconds = max(0.0, float(retry_cfg.get("backoff_seconds", 0)))
        last_status = "error"
        for attempt in range(1, max_attempts + 1):
            last_status = self._process_entry_once(entry, mark_error=attempt == max_attempts)
            if last_status == "completed":
                return ProcessOutcome(serial_number=serial, status=last_status, attempts=attempt)
            if attempt < max_attempts:
                delay = backoff_seconds * (2 ** (attempt - 1))
                if delay:
                    self.logger.warning("serial=%s attempt=%s/%s failed; retrying in %.1fs", serial, attempt, max_attempts, delay)
                    time.sleep(delay)
                else:
                    self.logger.warning("serial=%s attempt=%s/%s failed; retrying immediately", serial, attempt, max_attempts)
        return ProcessOutcome(serial_number=serial, status=last_status, attempts=max_attempts)

    def run(self, *, max_entries: int | None = None) -> dict[str, int]:
        processed = 0
        completed = 0
        errors = 0
        while max_entries is None or processed < max_entries:
            outcome = self.process_one()
            if outcome is None:
                break
            processed += 1
            if outcome.status == "completed":
                completed += 1
            else:
                errors += 1
        return {"processed": processed, "completed": completed, "errors": errors}

    def check_invariants(self) -> list[str]:
        errors: list[str] = []
        try:
            self.playlist_db.assert_serial_integrity()
            self.songs_db.assert_serial_integrity()
        except Exception as exc:
            errors.append(str(exc))
        playlist_rows = {int(r["serial_number"]): r for r in self.playlist_db.get_all()}
        song_rows = {int(r["serial_number"]): r for r in self.songs_db.get_all()}
        for serial, row in playlist_rows.items():
            if row["status"] == "completed":
                song = song_rows.get(serial)
                if not song:
                    errors.append(f"Completed playlist serial {serial} has no songs.db row")
                elif not self._resolve_project_path(str(song["mp3_path"])).exists():
                    errors.append(f"Completed playlist serial {serial} points to missing MP3: {song['mp3_path']}")
                elif str(song.get("lyrics_status") or "none") == "synced" and not song.get("lyrics_path"):
                    errors.append(f"Completed playlist serial {serial} says synced lyrics but has no lyrics_path")
                elif str(song.get("lyrics_status") or "none") == "synced" and not self._resolve_project_path(str(song["lyrics_path"])).exists():
                    errors.append(f"Completed playlist serial {serial} points to missing LRC: {song['lyrics_path']}")
            elif serial in song_rows and row["status"] != "completed":
                errors.append(f"Playlist serial {serial} has a retained song but status is {row['status']!r}")
        for serial in song_rows:
            if serial not in playlist_rows:
                errors.append(f"songs.db serial {serial} has no corresponding playlist entry")
        return errors
