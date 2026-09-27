from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .downloader import YTDlpInvoker

LYRICS_WORD_RE = re.compile(r"\blyrics\b", re.IGNORECASE)


@dataclass(frozen=True)
class VideoResult:
    video_id: str
    video_url: str
    title: str | None
    fulltitle: str | None
    alt_title: str | None
    channel: str | None
    channel_id: str | None
    uploader: str | None
    uploader_id: str | None
    upload_date: str | None
    timestamp: int | None
    release_date: str | None
    release_timestamp: int | None
    duration: int | None
    views: int | None
    likes: int | None
    comments: int | None
    thumbnail: str | None
    description: str | None
    categories: list[str]
    tags: list[str]
    extractor: str | None
    extractor_key: str | None
    raw: Mapping[str, Any] = field(repr=False)
    search_query: str
    search_result_index: int
    search_results_fetched: int
    match_method: str = "youtube_search"


def build_search_query(title: str, album: str | None) -> str:
    return f"{title} {album} official video song" if album else f"{title} official video song"


def _parse_single_json(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        raise YouTubeSearchError("yt-dlp returned no JSON output")
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    raise YouTubeSearchError("Could not parse yt-dlp JSON output")


def _published_fields(info: Mapping[str, Any]) -> tuple[str | None, int | None, str | None, int | None]:
    timestamp = int(info["timestamp"]) if isinstance(info.get("timestamp"), (int, float)) else None
    release_timestamp = int(info["release_timestamp"]) if isinstance(info.get("release_timestamp"), (int, float)) else None
    upload_date = str(info["upload_date"]) if info.get("upload_date") else None
    release_date = str(info["release_date"]) if info.get("release_date") else None
    if timestamp is not None and not upload_date:
        upload_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
    if release_timestamp is not None and not release_date:
        release_date = datetime.fromtimestamp(release_timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
    return upload_date, timestamp, release_date, release_timestamp


class YouTubeSearchError(RuntimeError):
    pass


class YouTubeFinder:
    def __init__(self, config: Mapping[str, Any], project_root: str | Path) -> None:
        self.config = config
        self.project_root = Path(project_root)
        self.invoker = YTDlpInvoker(config, project_root)

    def find(self, *, title: str, album: str | None) -> tuple[str, VideoResult | None]:
        search_cfg = self.config["youtube_video_search"]
        count = int(search_cfg["results_to_fetch"])
        query = build_search_query(title, album)
        search_term = f"ytsearch{count}:{query}"
        result = self.invoker.run(
            ["--quiet", "--no-warnings", "--skip-download", "--flat-playlist", "--dump-single-json", search_term],
            cwd=self.project_root,
            timeout=int(self.config.get("youtube_search_timeout_seconds", 120)),
        )
        if result.returncode != 0:
            raise YouTubeSearchError(f"YouTube search failed with exit code {result.returncode}")
        search_json = _parse_single_json(result.stdout)
        entries = search_json.get("entries") or []
        selected: tuple[int, str, str | None, str] | None = None
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                continue
            candidate_title = str(entry.get("title") or "")
            if LYRICS_WORD_RE.search(candidate_title):
                continue
            candidate_id = entry.get("id")
            if not candidate_id:
                continue
            candidate_id = str(candidate_id)
            candidate_url = str(entry.get("webpage_url") or f"https://www.youtube.com/watch?v={candidate_id}")
            selected = (index, candidate_id, candidate_title or None, candidate_url)
            break

        if selected is None:
            return query, None

        index, selected_id, selected_title, selected_url = selected
        detail = self.invoker.run(
            ["--quiet", "--no-warnings", "--skip-download", "--dump-single-json", selected_url],
            cwd=self.project_root,
            timeout=int(self.config.get("youtube_metadata_timeout_seconds", 120)),
        )
        if detail.returncode != 0:
            raise YouTubeSearchError(
                f"Selected YouTube video metadata lookup failed for {selected_id} with exit code {detail.returncode}"
            )
        info = _parse_single_json(detail.stdout)
        upload_date, timestamp, release_date, release_timestamp = _published_fields(info)
        video = VideoResult(
            video_id=str(info.get("id") or selected_id),
            video_url=str(info.get("webpage_url") or selected_url),
            title=str(info.get("title") or selected_title) if info.get("title") or selected_title else None,
            fulltitle=str(info.get("fulltitle")) if info.get("fulltitle") else None,
            alt_title=str(info.get("alt_title")) if info.get("alt_title") else None,
            channel=str(info.get("channel") or info.get("uploader")) if info.get("channel") or info.get("uploader") else None,
            channel_id=str(info.get("channel_id")) if info.get("channel_id") else None,
            uploader=str(info.get("uploader")) if info.get("uploader") else None,
            uploader_id=str(info.get("uploader_id")) if info.get("uploader_id") else None,
            upload_date=upload_date,
            timestamp=timestamp,
            release_date=release_date,
            release_timestamp=release_timestamp,
            duration=int(round(float(info["duration"]))) if info.get("duration") is not None else None,
            views=int(info["view_count"]) if isinstance(info.get("view_count"), (int, float)) else None,
            likes=int(info["like_count"]) if isinstance(info.get("like_count"), (int, float)) else None,
            comments=int(info["comment_count"]) if isinstance(info.get("comment_count"), (int, float)) else None,
            thumbnail=str(info.get("thumbnail")) if info.get("thumbnail") else None,
            description=str(info.get("description")) if info.get("description") else None,
            categories=[str(x) for x in (info.get("categories") or []) if x is not None],
            tags=[str(x) for x in (info.get("tags") or []) if x is not None],
            extractor=str(info.get("extractor")) if info.get("extractor") else None,
            extractor_key=str(info.get("extractor_key")) if info.get("extractor_key") else None,
            raw=info,
            search_query=query,
            search_result_index=index,
            search_results_fetched=len(entries),
        )
        return query, video
