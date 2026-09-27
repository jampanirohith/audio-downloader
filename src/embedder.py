from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
import re
import shutil
from typing import Any, Mapping

from PIL import Image
from mutagen.id3 import (
    APIC,
    ID3,
    TBPM,
    TCMP,
    TCOM,
    TCOP,
    TALB,
    TCON,
    TDRC,
    TENC,
    TIT2,
    TLAN,
    TLEN,
    TPE1,
    TPE2,
    TPUB,
    TPOS,
    TRCK,
    TSRC,
    TXXX,
    UFID,
    USLT,
    WXXX,
    SYLT,
)
from mutagen.mp3 import MP3

from .lrclib import LyricsResult, TIMESTAMP_RE
from .spotify import SpotifyResult


METADATA_EXPORT_VERSION = "6"
LRC_OFFSET_RE = re.compile(r"^\[offset:([+-]?\d+)\]$", re.IGNORECASE)
LRC_METADATA_RE = re.compile(r"^\[[A-Za-z]{2,8}:[^\]]*\]$")


class EmbedError(RuntimeError):
    pass


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _add_txxx(tags: ID3, desc: str, value: Any) -> None:
    text = _text(value)
    if text is None:
        return
    tags.add(TXXX(encoding=3, desc=desc, text=[text]))


def _add_wxxx(tags: ID3, desc: str, url: str | None) -> None:
    if url:
        tags.add(WXXX(encoding=3, desc=desc, url=str(url)))


def _add_ufid(tags: ID3, owner: str, identifier: str | None) -> None:
    if identifier:
        tags.add(UFID(owner=owner, data=str(identifier).encode("utf-8")))


def _parse_lrc(synced_lrc: str) -> tuple[list[tuple[str, int]], str]:
    """Parse LRC into ID3 SYLT events and plain lyric fallback text."""
    if not isinstance(synced_lrc, str) or not synced_lrc.strip():
        raise EmbedError("Synced lyrics are empty")

    events: list[tuple[str, int]] = []
    plain_lines: list[str] = []
    offset_ms = 0

    for raw_line in synced_lrc.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        offset_match = LRC_OFFSET_RE.match(line)
        if offset_match:
            try:
                offset_ms = int(offset_match.group(1))
            except ValueError:
                pass
            continue

        stamps: list[int] = []
        remainder = line
        while True:
            match = TIMESTAMP_RE.match(remainder)
            if not match:
                break
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            fraction = match.group(3) or "0"
            # Normalize .1/.12/.123 into milliseconds.
            millis = int(fraction.ljust(3, "0")[:3])
            stamps.append(max(0, minutes * 60_000 + seconds * 1_000 + millis + offset_ms))
            remainder = remainder[match.end():]

        text = remainder.strip()
        if not stamps:
            # Preserve metadata tags nowhere in the MP3 lyric body.
            if LRC_METADATA_RE.match(line):
                continue
            continue
        if not text:
            continue
        plain_lines.append(text)
        for timestamp in stamps:
            events.append((text, timestamp))

    events.sort(key=lambda item: (item[1], item[0]))
    if not events:
        raise EmbedError("LRCLIB returned synchronized lyrics but no timestamped lyric lines could be parsed")
    # Remove exact duplicate timestamp/text pairs without disturbing order.
    deduped: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for event in events:
        if event not in seen:
            deduped.append(event)
            seen.add(event)
    return deduped, "\n".join(plain_lines)


def _add_lyrics(tags: ID3, lyrics: LyricsResult) -> int:
    events, plain_text = _parse_lrc(lyrics.synced_lyrics)
    tags.add(
        SYLT(
            encoding=3,
            lang="xxx",
            format=2,  # milliseconds
            type=1,    # lyrics
            desc="Lyrics",
            text=events,
        )
    )
    # USLT is a compatibility fallback for players that do not surface SYLT.
    tags.add(USLT(encoding=3, lang="xxx", desc="Lyrics", text=plain_text))
    _add_txxx(tags, "lyrics_status", "synced")
    _add_txxx(tags, "lyrics_format", "LRC / ID3 SYLT")
    _add_txxx(tags, "lrclib_id", lyrics.lyrics_id)
    _add_txxx(tags, "lrclib_duration", lyrics.duration)
    _add_txxx(tags, "lrclib_duration_delta_seconds", lyrics.duration_delta_seconds)
    _add_txxx(tags, "lrclib_match_method", lyrics.match_method)
    _add_txxx(tags, "lyrics_sha256", hashlib.sha256(lyrics.synced_lyrics.encode("utf-8")).hexdigest())
    return len(events)


def _add_core_metadata(tags: ID3, metadata: Any, spotify: SpotifyResult | None) -> None:
    effective_isrc = getattr(metadata, "isrc", None) or (spotify.isrc if spotify is not None else None)
    tags.add(TIT2(encoding=3, text=[metadata.title]))
    tags.add(TPE1(encoding=3, text=[metadata.artist]))
    album_artist = metadata.album_artist or (spotify.artist_string if spotify is not None else None)
    if album_artist:
        tags.add(TPE2(encoding=3, text=[album_artist]))
    if metadata.album:
        tags.add(TALB(encoding=3, text=[metadata.album]))
    if metadata.release_date:
        tags.add(TDRC(encoding=3, text=[metadata.release_date]))
    if metadata.track_number:
        tags.add(TRCK(encoding=3, text=[metadata.track_number]))
    if metadata.disc_number:
        tags.add(TPOS(encoding=3, text=[metadata.disc_number]))
    if metadata.genre:
        tags.add(TCON(encoding=3, text=[metadata.genre]))
    if metadata.composer:
        tags.add(TCOM(encoding=3, text=[metadata.composer]))
    if metadata.publisher:
        tags.add(TPUB(encoding=3, text=[metadata.publisher]))
    if metadata.copyright:
        tags.add(TCOP(encoding=3, text=[metadata.copyright]))
    if metadata.language:
        tags.add(TLAN(encoding=3, text=[metadata.language]))
    if metadata.bpm is not None:
        tags.add(TBPM(encoding=3, text=[str(metadata.bpm)]))
    if metadata.compilation is not None:
        tags.add(TCMP(encoding=3, text=["1" if metadata.compilation else "0"]))
    if metadata.encoder:
        tags.add(TENC(encoding=3, text=[metadata.encoder]))
    if metadata.duration is not None:
        tags.add(TLEN(encoding=3, text=[str(int(metadata.duration) * 1000)]))
    if effective_isrc:
        tags.add(TSRC(encoding=3, text=[effective_isrc]))


def embed_final_mp3(
    *,
    source_mp3: str | Path,
    output_mp3: str | Path,
    playlist_entry: Mapping[str, Any],
    metadata: Any,
    video: Any,
    artwork_path: str | Path,
    artwork_source_url: str | None = None,
    artwork_width: int | None = None,
    artwork_height: int | None = None,
    artwork_mime_type: str | None = None,
    max_description_chars: int = 0,
    youtube_search_query: str | None = None,
    spotify: SpotifyResult | None = None,
    lyrics: LyricsResult | None = None,
    lyrics_path: str | Path | None = None,
    lyrics_status: str = "none",
    metadata_json_path: str | Path | None = None,
    artwork_provider: str | None = None,
) -> dict[str, Any]:
    """Create the final MP3 with concise interoperable metadata only.

    Detailed/source metadata belongs in the sidecar JSON, not in source descriptions or
    giant GEOB/TXXX dumps. The song keeps the important music fields, source IDs, URLs,
    Spotify ISRC, artwork and synchronized lyrics.
    """
    del max_description_chars  # Source descriptions deliberately do not enter ID3.
    source_mp3 = Path(source_mp3)
    output_mp3 = Path(output_mp3)
    artwork_path = Path(artwork_path)
    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_mp3, output_mp3)
    if not artwork_path.exists():
        output_mp3.unlink(missing_ok=True)
        raise EmbedError(f"Artwork file is required for final MP3: {artwork_path}")

    try:
        audio = MP3(output_mp3)
        tags = audio.tags
        if tags is None:
            audio.add_tags()
            tags = audio.tags
        if tags is None:
            raise EmbedError("Mutagen could not initialize ID3 tags")
        tags.clear()

        _add_core_metadata(tags, metadata, spotify)

        # Small, durable application/source identities.
        _add_txxx(tags, "metadata_export_version", METADATA_EXPORT_VERSION)
        _add_txxx(tags, "serial_number", playlist_entry.get("serial_number"))
        _add_txxx(tags, "playlist_position", playlist_entry.get("playlist_position"))
        _add_txxx(tags, "ytm_playlist_id", playlist_entry.get("ytm_playlist_id"))
        _add_txxx(tags, "ytm_video_id", playlist_entry.get("ytm_video_id"))
        _add_txxx(tags, "yt_video_id", getattr(video, "video_id", None) if video is not None else None)
        _add_txxx(tags, "yt_video_title", getattr(video, "title", None) if video is not None else None)
        _add_txxx(tags, "spotify_track_id", spotify.track_id if spotify else None)
        _add_txxx(tags, "spotify_album_id", spotify.album_id if spotify else None)
        _add_txxx(tags, "isrc", getattr(metadata, "isrc", None) or (spotify.isrc if spotify else None))
        _add_txxx(tags, "spotify_isrc", spotify.isrc if spotify else None)
        _add_txxx(tags, "lyrics_status", "synced" if lyrics else lyrics_status)

        # Machine-readable IDs.
        _add_ufid(tags, "https://music.youtube.com/", playlist_entry.get("ytm_video_id"))
        if video is not None:
            _add_ufid(tags, "https://www.youtube.com/", getattr(video, "video_id", None))
        if spotify is not None:
            _add_ufid(tags, "https://open.spotify.com/track/", spotify.track_id)

        # Human/automation-friendly URLs.
        _add_wxxx(tags, "YouTube Music source", playlist_entry.get("ytm_url"))
        if video is not None:
            _add_wxxx(tags, "Selected YouTube video", getattr(video, "video_url", None))
        if spotify is not None:
            _add_wxxx(tags, "Spotify track", spotify.track_url)
            _add_wxxx(tags, "Spotify album", spotify.album_url)
        if metadata.source_webpage_url:
            _add_wxxx(tags, "Original source webpage", metadata.source_webpage_url)

        lyrics_event_count = 0
        if lyrics is not None:
            lyrics_event_count = _add_lyrics(tags, lyrics)
        else:
            _add_txxx(tags, "lyrics_status", lyrics_status)

        with Image.open(artwork_path) as image:
            embedded_width, embedded_height = image.size
            image_format = (image.format or "JPEG").upper()
        mime = artwork_mime_type or mimetypes.guess_type(artwork_path.name)[0] or "image/jpeg"
        tags.add(
            APIC(
                encoding=3,
                mime=mime,
                type=3,
                desc="Cover",
                data=artwork_path.read_bytes(),
            )
        )
        _add_txxx(tags, "embedded_artwork_width", embedded_width)
        _add_txxx(tags, "embedded_artwork_height", embedded_height)
        _add_txxx(tags, "embedded_artwork_format", image_format)

        audio.save(v2_version=4)
        return {
            "embedded_lyrics": lyrics is not None,
            "lyrics_event_count": lyrics_event_count,
            "embedded_artwork_width": embedded_width,
            "embedded_artwork_height": embedded_height,
        }
    except Exception:
        output_mp3.unlink(missing_ok=True)
        raise
