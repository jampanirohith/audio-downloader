from __future__ import annotations

from dataclasses import dataclass, field
import re
import time
from typing import Any, Mapping

import requests
from requests import RequestException

LRCLIB_API_URL = "https://lrclib.net/api"
TIMESTAMP_RE = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")


class LRCError(RuntimeError):
    pass


@dataclass(frozen=True)
class LyricsResult:
    lyrics_id: int | None
    track_name: str | None
    artist_name: str | None
    album_name: str | None
    duration: int | None
    instrumental: bool | None
    synced_lyrics: str
    query_track: str
    query_artist: str
    query_album: str
    duration_delta_seconds: float | None
    match_method: str
    raw: Mapping[str, Any] = field(repr=False)


class LRCLIBClient:
    """LRCLIB client that intentionally uses only GET /api/get."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": str(
                config.get("user_agent")
                or "Phase1AudioDownloader/2.0 (LRCLIB client)"
            )
        })
        self._timeout = max(5, int(config.get("timeout_seconds", 30)))
        self._max_retries = max(1, int(config.get("max_retries", 3)))
        self._delay = max(0.2, float(config.get("request_delay_seconds", 0.5)))
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)
        self._last_request = time.monotonic()

    def _get(self, *, params: Mapping[str, Any]) -> Any:
        last_error = ""
        for attempt in range(1, self._max_retries + 1):
            self._throttle()
            try:
                response = self._session.get(
                    f"{LRCLIB_API_URL}/get",
                    params=dict(params),
                    timeout=self._timeout,
                )
            except RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self._max_retries:
                    time.sleep(0.75 * attempt)
                    continue
                break

            if response.status_code == 404:
                return None
            if response.status_code == 429:
                retry_after_raw = response.headers.get("Retry-After", "1") or "1"
                try:
                    retry_after = float(retry_after_raw)
                except ValueError:
                    retry_after = 1.0
                if attempt < self._max_retries:
                    time.sleep(max(self._delay, min(retry_after, 60.0)))
                    continue
            if 500 <= response.status_code < 600 and attempt < self._max_retries:
                time.sleep(0.75 * attempt)
                continue
            if not response.ok:
                last_error = f"HTTP {response.status_code}: {response.text[:500]}"
                break
            try:
                return response.json()
            except ValueError as exc:
                raise LRCError("LRCLIB returned invalid JSON from /api/get") from exc
        raise LRCError(f"LRCLIB request failed for /api/get: {last_error or 'unknown error'}")

    @staticmethod
    def _duration_delta(candidate: Any, target: int | None) -> float | None:
        if candidate is None or target is None:
            return None
        try:
            return abs(float(candidate) - float(target))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def is_valid_synced_lyrics(value: Any) -> bool:
        if not isinstance(value, str) or not value.strip():
            return False
        return any(TIMESTAMP_RE.search(line) for line in value.splitlines() if line.strip())

    @staticmethod
    def _result_from_payload(
        payload: Mapping[str, Any],
        *,
        title: str,
        artist: str,
        album: str | None,
        duration_seconds: int | None,
    ) -> LyricsResult:
        candidate_duration = payload.get("duration")
        try:
            duration = int(round(float(candidate_duration))) if candidate_duration is not None else None
        except (TypeError, ValueError):
            duration = None

        lyrics_id_value = payload.get("lyricsId", payload.get("id"))
        lyrics_id: int | None = None
        if isinstance(lyrics_id_value, (int, float, str)) and str(lyrics_id_value).isdigit():
            lyrics_id = int(lyrics_id_value)

        synced = str(payload.get("syncedLyrics") or "").rstrip() + "\n"
        return LyricsResult(
            lyrics_id=lyrics_id,
            track_name=str(payload.get("trackName") or payload.get("name") or "") or None,
            artist_name=str(payload.get("artistName") or "") or None,
            album_name=str(payload.get("albumName") or "") or None,
            duration=duration,
            instrumental=bool(payload.get("instrumental")) if payload.get("instrumental") is not None else None,
            synced_lyrics=synced,
            query_track=title,
            query_artist=artist,
            query_album=album or "",
            duration_delta_seconds=LRCLIBClient._duration_delta(candidate_duration, duration_seconds),
            match_method="lrclib_api_get",
            raw=dict(payload),
        )

    def get_synced(
        self,
        *,
        title: str,
        artist: str,
        album: str | None,
        duration_seconds: int | None,
        alternate_signatures: list[tuple[str, str, str | None, int | None]] | None = None,
    ) -> LyricsResult | None:
        """Use only /api/get. Try the primary signature, then optional metadata-derived alternates.

        This never calls /api/search. LRCLIB's /api/get is a signature lookup that uses
        title, artist, album, and duration to locate the best record; syncedLyrics must exist.
        """
        signatures: list[tuple[str, str, str | None, int | None]] = [
            (title, artist, album, duration_seconds)
        ]
        for signature in alternate_signatures or []:
            if signature not in signatures:
                signatures.append(signature)

        best: LyricsResult | None = None
        for track_name, artist_name, album_name, duration in signatures:
            if not track_name or not artist_name or not album_name or duration is None:
                continue
            params: dict[str, Any] = {
                "track_name": track_name,
                "artist_name": artist_name,
                "album_name": album_name,
                "duration": int(duration),
            }
            payload = self._get(params=params)
            if not isinstance(payload, Mapping):
                continue
            if not self.is_valid_synced_lyrics(payload.get("syncedLyrics")):
                continue
            candidate = self._result_from_payload(
                payload,
                title=track_name,
                artist=artist_name,
                album=album_name,
                duration_seconds=duration,
            )
            # Exact /api/get matches should win. If multiple signatures produce synced
            # records, use the smallest duration delta deterministically.
            if best is None:
                best = candidate
            else:
                current_delta = candidate.duration_delta_seconds
                best_delta = best.duration_delta_seconds
                if current_delta is not None and (best_delta is None or current_delta < best_delta):
                    best = candidate
        return best
