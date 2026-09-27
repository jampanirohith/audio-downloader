from __future__ import annotations

import argparse
import io
import json
import logging
import os
from pathlib import Path
import shutil
import sys

from PIL import Image, ImageOps
from mutagen.id3 import ID3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.artwork import fetch_ytmusic_og_image, normalize_artwork  # noqa: E402
from src.db_playlist import PlaylistDB  # noqa: E402
from src.db_songs import SongsDB  # noqa: E402
from src.embedder import embed_final_mp3  # noqa: E402
from src.hashing import hash_file  # noqa: E402
from src.metadata import dump_json, normalized_metadata_from_record  # noqa: E402
from src.validator import validate_final_mp3  # noqa: E402
from src.youtube_finder import VideoResult  # noqa: E402
from src.spotify import SpotifyImage, SpotifyResult  # noqa: E402
from src.lrclib import LyricsResult  # noqa: E402


def _json_value(value: object, default: object) -> object:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default


def video_from_row(row: dict) -> VideoResult | None:
    video_id = row.get("yt_video_id")
    if not video_id:
        return None
    raw = _json_value(row.get("yt_video_info_json"), {})
    if not isinstance(raw, dict):
        raw = {}
    return VideoResult(
        video_id=str(video_id),
        video_url=str(row.get("yt_video_url") or raw.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"),
        title=row.get("yt_video_title") or raw.get("title"),
        fulltitle=row.get("yt_video_fulltitle") or raw.get("fulltitle"),
        alt_title=row.get("yt_video_alt_title") or raw.get("alt_title"),
        channel=row.get("yt_video_channel") or raw.get("channel") or raw.get("uploader"),
        channel_id=row.get("yt_video_channel_id") or raw.get("channel_id"),
        uploader=row.get("yt_video_uploader") or raw.get("uploader"),
        uploader_id=row.get("yt_video_uploader_id") or raw.get("uploader_id"),
        upload_date=row.get("yt_video_upload_date") or raw.get("upload_date"),
        timestamp=row.get("yt_video_timestamp") or raw.get("timestamp"),
        release_date=row.get("yt_video_release_date") or raw.get("release_date"),
        release_timestamp=row.get("yt_video_release_timestamp") or raw.get("release_timestamp"),
        duration=row.get("yt_video_duration") or raw.get("duration"),
        views=row.get("yt_video_views") if row.get("yt_video_views") is not None else raw.get("view_count"),
        likes=row.get("yt_video_likes") if row.get("yt_video_likes") is not None else raw.get("like_count"),
        comments=row.get("yt_video_comments") if row.get("yt_video_comments") is not None else raw.get("comment_count"),
        thumbnail=row.get("yt_video_thumbnail") or raw.get("thumbnail"),
        description=row.get("yt_video_description") or raw.get("description"),
        categories=[str(x) for x in (_json_value(row.get("yt_video_categories_json"), raw.get("categories") or [])) or []],
        tags=[str(x) for x in (_json_value(row.get("yt_video_tags_json"), raw.get("tags") or [])) or []],
        extractor=row.get("yt_video_extractor") or raw.get("extractor"),
        extractor_key=row.get("yt_video_extractor_key") or raw.get("extractor_key"),
        raw=raw,
        search_query=str(row.get("yt_video_search_query") or ""),
        search_result_index=int(row.get("yt_video_search_result_index") or 1),
        search_results_fetched=int(row.get("yt_video_search_results_fetched") or 0),
        match_method=str(row.get("yt_video_match_method") or "youtube_search"),
    )


def existing_artwork(mp3_path: Path, destination: Path) -> tuple[Path, int, int]:
    tags = ID3(mp3_path)
    fronts = [a for a in tags.getall("APIC") if getattr(a, "type", None) == 3]
    if not fronts:
        raise RuntimeError("Existing MP3 has no front-cover artwork and refreshed artwork was unavailable")
    destination.write_bytes(fronts[0].data)
    with Image.open(destination) as source:
        image = ImageOps.exif_transpose(source).copy()
        size = image.size
        image.convert("RGB").save(destination, format="JPEG", quality=98, subsampling=0, optimize=True)
        image.close()
    return destination, int(size[0]), int(size[1])



def spotify_from_row(row: dict) -> SpotifyResult | None:
    track_id = row.get("spotify_track_id")
    if not track_id:
        return None
    def list_value(key: str) -> list[str]:
        value = _json_value(row.get(key), [])
        return [str(x) for x in value] if isinstance(value, list) else []
    raw = _json_value(row.get("spotify_raw_json"), {})
    album_raw = _json_value(row.get("spotify_album_raw_json"), {})
    if not isinstance(raw, dict): raw = {}
    if not isinstance(album_raw, dict): album_raw = {}
    return SpotifyResult(
        track_id=str(track_id), track_name=str(row.get("spotify_track_name") or row.get("title") or ""),
        track_url=row.get("spotify_track_url"), uri=row.get("spotify_uri"), artists=list_value("spotify_artists_json"),
        artist_ids=list_value("spotify_artist_ids_json"), artist_urls=list_value("spotify_artist_urls_json"),
        album_name=row.get("spotify_album_name"), album_id=row.get("spotify_album_id"), album_url=row.get("spotify_album_url"),
        album_type=row.get("spotify_album_type"), album_release_date=row.get("spotify_album_release_date"),
        album_release_precision=row.get("spotify_album_release_precision"), album_total_tracks=row.get("spotify_album_total_tracks"),
        album_artwork_url=row.get("spotify_album_artwork_url"), album_artwork_width=int(row["spotify_album_artwork_width"]) if row.get("spotify_album_artwork_width") is not None else None,
        album_artwork_height=int(row["spotify_album_artwork_height"]) if row.get("spotify_album_artwork_height") is not None else None,
        album_images=[SpotifyImage(str(x.get("url")), x.get("width"), x.get("height")) for x in (album_raw.get("images") or []) if isinstance(x, dict) and x.get("url")], album_label=row.get("spotify_album_label"),
        album_copyrights=list_value("spotify_album_copyrights_json"), duration_ms=int(row.get("spotify_duration_ms") or 0),
        duration_seconds=int(row.get("spotify_duration_seconds") or 0), duration_delta_ms=int(row.get("spotify_duration_delta_ms") or 0),
        explicit=bool(row.get("spotify_explicit")) if row.get("spotify_explicit") is not None else None,
        popularity=int(row["spotify_popularity"]) if row.get("spotify_popularity") is not None else None,
        isrc=row.get("spotify_isrc"), track_number=int(row["spotify_track_number"]) if row.get("spotify_track_number") is not None else None,
        disc_number=int(row["spotify_disc_number"]) if row.get("spotify_disc_number") is not None else None,
        search_query=str(row.get("spotify_search_query") or ""), search_result_index=int(row.get("spotify_search_result_index") or 1),
        raw=raw, album_raw=album_raw,
    )


def lyrics_from_row(row: dict) -> tuple[LyricsResult | None, Path | None, str]:
    status = str(row.get("lyrics_status") or "none")
    path_value = row.get("lyrics_path")
    if status != "synced" or not path_value:
        return None, None, status
    path = Path(str(path_value))
    actual = path if path.is_absolute() else ROOT / path
    if not actual.exists():
        raise RuntimeError(f"Synced LRC file is missing: {actual}")
    raw = _json_value(row.get("lrclib_raw_json"), {})
    if not isinstance(raw, dict): raw = {}
    text = actual.read_text(encoding="utf-8")
    result = LyricsResult(
        lyrics_id=int(row["lrclib_id"]) if row.get("lrclib_id") is not None else None,
        track_name=row.get("lrclib_track_name"), artist_name=row.get("lrclib_artist_name"), album_name=row.get("lrclib_album_name"),
        duration=int(row["lrclib_duration"]) if row.get("lrclib_duration") is not None else None, instrumental=None,
        synced_lyrics=text, query_track=str(row.get("title") or ""), query_artist=str(row.get("artist") or ""), query_album=str(row.get("album") or ""),
        duration_delta_seconds=float(row["lrclib_duration_delta_seconds"]) if row.get("lrclib_duration_delta_seconds") is not None else None,
        match_method=str(row.get("lrclib_match_method") or "lrclib_api_get"), raw=raw,
    )
    return result, actual, status


def detect_artwork_mime(path: Path) -> str:
    from PIL import Image
    with Image.open(path) as image:
        fmt = (image.format or "").upper()
    return Image.MIME.get(fmt) or "image/jpeg"

def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild complete Phase 1 metadata on existing retained MP3s")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--serial", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--refresh-artwork", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    import sys as _sys
    sys.path.insert(0, str(ROOT))
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    config = json.loads(config_path.read_text(encoding="utf-8"))
    db_dir_value = Path(config["paths"]["database"])
    db_dir = db_dir_value if db_dir_value.is_absolute() else ROOT / db_dir_value
    playlist_db = PlaylistDB(db_dir / "playlist.db")
    songs_db = SongsDB(db_dir / "songs.db")
    temp_root = ROOT / config["paths"]["temp"] / "reembed"
    temp_root.mkdir(parents=True, exist_ok=True)

    rows = songs_db.get_all()
    if args.serial is not None:
        rows = [r for r in rows if int(r["serial_number"]) == args.serial]
    if args.limit is not None:
        rows = rows[: args.limit]

    failures = 0
    for row in rows:
        serial = int(row["serial_number"])
        original_value = Path(str(row["mp3_path"]))
        original_path = original_value if original_value.is_absolute() else ROOT / original_value
        print(f"[{serial:03d}] {row['title']} — {row.get('artist')}")
        if not original_path.exists():
            print("  ERROR: MP3 file is missing")
            failures += 1
            continue
        if args.dry_run:
            print(f"  would re-embed: {original_path}")
            continue

        work = temp_root / f"{serial:03d}"
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)
        try:
            info_json = work / "master.info.json"
            source_raw = _json_value(row.get("source_info_json"), {})
            if not isinstance(source_raw, dict):
                source_raw = {}
            info_json.write_text(dump_json(source_raw), encoding="utf-8")

            artwork_source_url = None
            artwork_width = None
            artwork_height = None
            artwork_path = work / "artwork.jpg"
            if args.refresh_artwork and row.get("ytm_url"):
                fetched, source_url, width, height = fetch_ytmusic_og_image(
                    str(row["ytm_url"]), work / "ytm_og_image",
                    cookies_file=config.get("cookies_file"),
                    timeout_seconds=int(config.get("artwork", {}).get("og_image_timeout_seconds", 30)),
                )
                if fetched:
                    normalize_artwork(fetched, artwork_path, force_square=True, max_dimension=int(config.get("artwork", {}).get("max_dimension", 1200)), jpeg_quality=int(config.get("artwork", {}).get("jpeg_quality", 98)))
                    artwork_source_url, artwork_width, artwork_height = source_url, width, height
            if not artwork_path.exists():
                extracted, width, height = existing_artwork(original_path, work / "existing_cover.jpg")
                normalize_artwork(extracted, artwork_path, force_square=True, max_dimension=int(config.get("artwork", {}).get("max_dimension", 1200)), jpeg_quality=int(config.get("artwork", {}).get("jpeg_quality", 98)))
                artwork_width, artwork_height = width, height
                artwork_source_url = row.get("artwork_source_url")

            metadata = normalized_metadata_from_record(row)
            playlist_entry = playlist_db.get_by_serial(serial) or {
                "serial_number": serial,
                "playlist_position": serial,
                "ytm_playlist_id": row.get("ytm_playlist_id"),
                "ytm_video_id": row.get("ytm_video_id"),
                "ytm_url": row.get("ytm_url"),
                "ytm_playlist_item_json": row.get("ytm_playlist_item_json"),
            }
            video = video_from_row(row)
            spotify = spotify_from_row(row)
            lyrics, lyrics_file_path, lyrics_status = lyrics_from_row(row)
            lyrics_tag_path = Path(str(row.get("lyrics_path"))) if row.get("lyrics_path") else None
            temp_final = work / "final.mp3.tmp"
            embed_final_mp3(
                source_mp3=original_path, output_mp3=temp_final, playlist_entry=playlist_entry,
                metadata=metadata, video=video, artwork_path=artwork_path,
                artwork_source_url=artwork_source_url, artwork_width=artwork_width, artwork_height=artwork_height,
                max_description_chars=int(config.get("max_description_chars", 0)),
                youtube_search_query=row.get("yt_video_search_query"),
                spotify=spotify, lyrics=lyrics, lyrics_path=lyrics_tag_path, lyrics_status=lyrics_status,
                metadata_json_path=(Path(str(row.get("metadata_json_path"))) if row.get("metadata_json_path") else original_path.with_suffix(".json").relative_to(ROOT)),
                artwork_provider=str(row.get("artwork_provider") or "existing"),
            )
            validate_final_mp3(
                path=temp_final, playlist_entry=playlist_entry, metadata=metadata, video=video,
                youtube_search_query=row.get("yt_video_search_query"), artwork_source_url=artwork_source_url,
                artwork_width=artwork_width, artwork_height=artwork_height, spotify=spotify, lyrics=lyrics,
                lyrics_path=lyrics_tag_path, lyrics_file_path=lyrics_file_path, lyrics_status=lyrics_status,
            )
            size, digest = hash_file(temp_final)
            os.replace(temp_final, original_path)
            songs_db.update_song_file_fields(serial, mp3_size=size, mp3_sha256=digest, artwork_source_url=artwork_source_url, artwork_width=artwork_width, artwork_height=artwork_height)
            print("  OK: metadata rebuilt and file replaced atomically")
        except Exception as exc:
            failures += 1
            print(f"  ERROR: {type(exc).__name__}: {exc}")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    print(f"Processed: {len(rows)} | Failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
