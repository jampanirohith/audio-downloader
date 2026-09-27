from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Mapping

from PIL import Image
from mutagen.id3 import ID3, SYLT, USLT
from mutagen.mp3 import MP3

from .embedder import _parse_lrc
from .spotify import SpotifyResult
from .lrclib import LyricsResult


class ValidationError(RuntimeError):
    pass


def _first_text(id3: ID3, frame_id: str) -> str | None:
    frames = id3.getall(frame_id)
    if not frames:
        return None
    text = getattr(frames[0], "text", None)
    return str(text[0]) if text else None


def _txxx(id3: ID3) -> dict[str, str]:
    result: dict[str, str] = {}
    for frame in id3.getall("TXXX"):
        desc = getattr(frame, "desc", None)
        text = getattr(frame, "text", None)
        if desc is not None and text:
            result[str(desc)] = str(text[0])
    return result


def _ufid_value(id3: ID3, owner: str) -> str | None:
    frames = [f for f in id3.getall("UFID") if getattr(f, "owner", None) == owner]
    if not frames:
        return None
    try:
        return frames[0].data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"UFID:{owner} is not UTF-8") from exc


def _wxxx_urls(id3: ID3) -> dict[str, str]:
    result: dict[str, str] = {}
    for frame in id3.getall("WXXX"):
        desc = getattr(frame, "desc", None)
        url = getattr(frame, "url", None)
        if desc and url:
            result[str(desc)] = str(url)
    return result


def _check_artwork(id3: ID3, expected_width: int | None = None, expected_height: int | None = None) -> None:
    apics = id3.getall("APIC")
    if not apics:
        raise ValidationError("Final MP3 has no embedded artwork")
    front = [a for a in apics if getattr(a, "type", None) == 3]
    if len(front) != 1:
        raise ValidationError(f"Final MP3 must contain exactly one front-cover APIC; found {len(front)}")
    apic = front[0]
    try:
        with Image.open(io.BytesIO(apic.data)) as image:
            image.verify()
        with Image.open(io.BytesIO(apic.data)) as image:
            if image.width != image.height:
                raise ValidationError(f"Embedded cover is not square: {image.width}x{image.height}")
            if image.width <= 0 or image.height <= 0:
                raise ValidationError("Embedded cover has invalid dimensions")
            if expected_width is not None and image.width != expected_width:
                raise ValidationError("Embedded artwork width differs from recorded source width")
            if expected_height is not None and image.height != expected_height:
                raise ValidationError("Embedded artwork height differs from recorded source height")
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("Embedded artwork cannot be decoded") from exc


def _check_lyrics(id3: ID3, lyrics: LyricsResult | None) -> None:
    sylts = id3.getall("SYLT")
    uslts = id3.getall("USLT")
    if lyrics is None:
        if sylts or uslts:
            raise ValidationError("Lyrics frames must be absent when no synced lyrics were found")
        return
    if len(sylts) != 1 or len(uslts) != 1:
        raise ValidationError(f"Synced lyrics require exactly one SYLT and one USLT frame; found SYLT={len(sylts)}, USLT={len(uslts)}")
    expected_events, expected_plain = _parse_lrc(lyrics.synced_lyrics)
    sylt = sylts[0]
    actual_events = [(str(text), int(timestamp)) for text, timestamp in getattr(sylt, "text", [])]
    if actual_events != expected_events:
        raise ValidationError("Embedded SYLT lyrics do not match the downloaded LRC timestamps/text")
    uslt = uslts[0]
    actual_plain = str(getattr(uslt, "text", ""))
    if actual_plain != expected_plain:
        raise ValidationError("Embedded USLT lyrics do not match the downloaded LRC text")


def validate_final_mp3(
    *,
    path: str | Path,
    playlist_entry: Mapping[str, Any],
    metadata: Any,
    video: Any,
    youtube_search_query: str | None = None,
    artwork_source_url: str | None = None,
    artwork_width: int | None = None,
    artwork_height: int | None = None,
    artwork_mime_type: str | None = None,
    spotify: SpotifyResult | None = None,
    lyrics: LyricsResult | None = None,
    lyrics_path: str | Path | None = None,
    lyrics_file_path: str | Path | None = None,
    lyrics_status: str = "none",
) -> None:
    path = Path(path)
    if not path.exists() or path.stat().st_size <= 0:
        raise ValidationError(f"Final MP3 does not exist or is empty: {path}")

    try:
        audio = MP3(path)
        if audio.info.length <= 0:
            raise ValidationError("Final MP3 duration is invalid")
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(f"Final MP3 cannot be opened: {path}") from exc

    try:
        id3 = ID3(path)
    except Exception as exc:
        raise ValidationError("Final MP3 ID3 tags cannot be reopened") from exc

    # The MP3 intentionally contains only player-facing metadata and important IDs.
    # Large source/API details belong exclusively in the sidecar JSON.
    if id3.getall("GEOB"):
        raise ValidationError("GEOB metadata is not allowed in the final MP3; detailed metadata belongs in sidecar JSON")
    if id3.getall("COMM"):
        raise ValidationError("COMM source-description metadata is not allowed in the final MP3")

    standard = {
        "TIT2": metadata.title,
        "TPE1": metadata.artist,
        "TPE2": metadata.album_artist or (spotify.artist_string if spotify else None),
        "TALB": metadata.album,
        "TDRC": metadata.release_date,
        "TRCK": metadata.track_number,
        "TPOS": metadata.disc_number,
        "TCON": metadata.genre,
        "TCOM": metadata.composer,
        "TPUB": metadata.publisher,
        "TCOP": metadata.copyright,
        "TLAN": metadata.language,
        "TENC": metadata.encoder,
    }
    for frame_id, expected in standard.items():
        actual = _first_text(id3, frame_id)
        if expected is None:
            if actual is not None:
                raise ValidationError(f"{frame_id} should be absent")
        elif actual != str(expected):
            raise ValidationError(f"{frame_id} missing or incorrect: expected {expected!r}, got {actual!r}")

    if metadata.duration is not None and _first_text(id3, "TLEN") != str(int(metadata.duration) * 1000):
        raise ValidationError("TLEN duration missing or incorrect")
    if metadata.bpm is not None and _first_text(id3, "TBPM") != str(metadata.bpm):
        raise ValidationError("TBPM missing or incorrect")
    if metadata.compilation is not None and _first_text(id3, "TCMP") != ("1" if metadata.compilation else "0"):
        raise ValidationError("TCMP missing or incorrect")

    custom = _txxx(id3)
    expected_custom: dict[str, str] = {
        "metadata_export_version": "5",
        "serial_number": str(playlist_entry["serial_number"]),
        "playlist_position": str(playlist_entry["playlist_position"]),
    }
    optional_custom = {
        "ytm_playlist_id": playlist_entry.get("ytm_playlist_id"),
        "ytm_video_id": playlist_entry.get("ytm_video_id"),
        "yt_video_id": video.video_id if video is not None else None,
        "yt_video_title": video.title if video is not None else None,
        "spotify_track_id": spotify.track_id if spotify else None,
        "spotify_album_id": spotify.album_id if spotify else None,
        "spotify_isrc": spotify.isrc if spotify else None,
        "lyrics_status": "synced" if lyrics is not None else lyrics_status,
    }
    expected_custom.update({k: str(v) for k, v in optional_custom.items() if v is not None})
    for key, value in expected_custom.items():
        actual = custom.get(key)
        if actual != value:
            raise ValidationError(f"TXXX:{key} missing or incorrect: expected {value!r}, got {actual!r}")

    # Spotify ISRC is a normal tag, not a duplicate-detection key.
    actual_tsrc = _first_text(id3, "TSRC")
    if spotify is not None and spotify.isrc:
        if actual_tsrc != spotify.isrc:
            raise ValidationError("TSRC is missing or incorrect")
    elif actual_tsrc is not None:
        raise ValidationError("TSRC must be absent when Spotify does not provide an ISRC")

    # Machine-readable source IDs.
    expected_ytm_id = playlist_entry.get("ytm_video_id")
    actual_ytm_ufid = _ufid_value(id3, "https://music.youtube.com/")
    if (str(expected_ytm_id) if expected_ytm_id is not None else None) != actual_ytm_ufid:
        raise ValidationError("YTMusic UFID is missing or incorrect")
    expected_youtube_id = video.video_id if video is not None else None
    actual_youtube_ufid = _ufid_value(id3, "https://www.youtube.com/")
    if (str(expected_youtube_id) if expected_youtube_id is not None else None) != actual_youtube_ufid:
        raise ValidationError("YouTube UFID is missing or incorrect")
    expected_spotify_id = spotify.track_id if spotify is not None else None
    actual_spotify_ufid = _ufid_value(id3, "https://open.spotify.com/track/")
    if (str(expected_spotify_id) if expected_spotify_id is not None else None) != actual_spotify_ufid:
        raise ValidationError("Spotify UFID is missing or incorrect")

    urls = _wxxx_urls(id3)
    expected_urls = {
        "YouTube Music source": playlist_entry.get("ytm_url"),
        "Selected YouTube video": video.video_url if video is not None else None,
        "Spotify track": spotify.track_url if spotify else None,
        "Spotify album": spotify.album_url if spotify else None,
        "Original source webpage": metadata.source_webpage_url,
    }
    for desc, expected_url in expected_urls.items():
        if expected_url is None:
            if desc in urls:
                raise ValidationError(f"WXXX:{desc} should be absent")
        elif urls.get(desc) != str(expected_url):
            raise ValidationError(f"WXXX:{desc} missing or incorrect")

    _check_lyrics(id3, lyrics)
    if lyrics_status == "synced":
        lrc_path = Path(str(lyrics_file_path or lyrics_path or ""))
        if not lrc_path.exists():
            raise ValidationError(f"Synced LRC file does not exist: {lrc_path}")
    elif lyrics is not None:
        raise ValidationError("Lyrics result exists but lyrics_status is not synced")

    _check_artwork(id3)

    # Prevent accidental metadata bloat. Every custom tag written by the embedder must be
    # one of the small player-facing fields documented by the project.
    allowed_txxx = {
        "metadata_export_version", "serial_number", "playlist_position", "ytm_playlist_id", "ytm_video_id",
        "yt_video_id", "yt_video_title", "spotify_track_id", "spotify_album_id", "spotify_isrc",
        "lyrics_status", "lyrics_format", "lrclib_id", "lrclib_duration", "lrclib_duration_delta_seconds",
        "lrclib_match_method", "lyrics_sha256", "embedded_artwork_width", "embedded_artwork_height",
        "embedded_artwork_format",
    }
    if set(custom) - allowed_txxx:
        unexpected = sorted(set(custom) - allowed_txxx)
        raise ValidationError(f"Unexpected verbose/custom metadata in MP3: {unexpected}")

    # Reopen after all parsing to ensure the file remains readable.
    try:
        reopened = MP3(path)
        if reopened.info.length <= 0:
            raise ValidationError("Final MP3 failed close/reopen check")
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("Final MP3 failed close/reopen check") from exc
