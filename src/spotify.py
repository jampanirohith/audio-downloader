from __future__ import annotations

from dataclasses import dataclass, field, replace
import base64
import time
from typing import Any, Mapping

import requests
from requests import RequestException

SPOTIFY_ACCOUNTS_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_URL = "https://api.spotify.com/v1"


class SpotifyError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpotifyImage:
    url: str
    width: int | None
    height: int | None


@dataclass(frozen=True)
class SpotifyResult:
    track_id: str
    track_name: str
    track_url: str | None
    uri: str | None
    artists: list[str]
    artist_ids: list[str]
    artist_urls: list[str]
    album_name: str | None
    album_id: str | None
    album_url: str | None
    album_type: str | None
    album_release_date: str | None
    album_release_precision: str | None
    album_total_tracks: int | None
    album_artwork_url: str | None
    album_artwork_width: int | None
    album_artwork_height: int | None
    album_images: list[SpotifyImage]
    album_label: str | None
    album_copyrights: list[str]
    duration_ms: int
    duration_seconds: int
    duration_delta_ms: int
    explicit: bool | None
    popularity: int | None
    isrc: str | None
    track_number: int | None
    disc_number: int | None
    search_query: str
    search_result_index: int
    raw: Mapping[str, Any] = field(repr=False)
    album_raw: Mapping[str, Any] = field(repr=False)

    @property
    def artist_string(self) -> str:
        return ", ".join(self.artists)

    @property
    def album_artist_string(self) -> str | None:
        return self.artist_string or None


class SpotifyClient:
    """Spotify Web API client using Client Credentials."""

    def __init__(self, config: Mapping[str, Any], project_root: str | None = None) -> None:
        self.config = config
        self._session = requests.Session()
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._album_cache: dict[str, dict[str, Any]] = {}
        self._max_retries = max(1, int(config.get("max_retries", 3)))
        self._timeout = max(5, int(config.get("timeout_seconds", 30)))
        self._client_id = str(config.get("client_id") or "").strip()
        self._client_secret = str(config.get("client_secret") or "").strip()
        if bool(config.get("use_env", True)):
            import os
            self._client_id = os.getenv("SPOTIFY_CLIENT_ID", self._client_id).strip()
            self._client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", self._client_secret).strip()
        self.market = str(config.get("market") or "IN").strip().upper() or None

    @property
    def configured(self) -> bool:
        return bool(self._client_id and self._client_secret)

    def _get_token(self) -> str:
        if not self.configured:
            raise SpotifyError("Spotify is enabled but client_id/client_secret are not configured")
        now = time.time()
        if self._token and now < self._token_expires_at - 60:
            return self._token
        credentials = f"{self._client_id}:{self._client_secret}".encode("utf-8")
        auth = base64.b64encode(credentials).decode("ascii")
        response = self._session.post(
            SPOTIFY_ACCOUNTS_URL,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise SpotifyError(
                f"Spotify token request failed: HTTP {response.status_code}: {response.text[:500]}"
            )
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise SpotifyError("Spotify token response contained no access_token")
        self._token = str(token)
        self._token_expires_at = now + float(payload.get("expires_in") or 3600)
        return self._token

    def _request(self, method: str, path: str, *, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        last_error = ""
        for attempt in range(1, self._max_retries + 1):
            token = self._get_token()
            try:
                response = self._session.request(
                    method,
                    f"{SPOTIFY_API_URL}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                    params=dict(params or {}),
                    timeout=self._timeout,
                )
            except RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self._max_retries:
                    time.sleep(0.75 * attempt)
                    continue
                break
            if response.status_code == 401 and attempt < self._max_retries:
                self._token = None
                self._token_expires_at = 0
                continue
            if response.status_code == 429:
                retry_after_raw = response.headers.get("Retry-After", "1") or "1"
                try:
                    retry_after = float(retry_after_raw)
                except ValueError:
                    retry_after = 1.0
                if attempt < self._max_retries:
                    time.sleep(max(0.2, min(retry_after, 60.0)))
                    continue
            if 500 <= response.status_code < 600 and attempt < self._max_retries:
                time.sleep(0.75 * attempt)
                continue
            if not response.ok:
                last_error = f"HTTP {response.status_code}: {response.text[:500]}"
                break
            try:
                payload = response.json()
            except ValueError as exc:
                raise SpotifyError(f"Spotify API returned invalid JSON for {path}") from exc
            if not isinstance(payload, dict):
                raise SpotifyError(f"Spotify API returned unexpected JSON for {path}")
            return payload
        raise SpotifyError(f"Spotify API request failed for {path}: {last_error or 'unknown error'}")

    @staticmethod
    def _artist_values(track: Mapping[str, Any]) -> tuple[list[str], list[str], list[str]]:
        names: list[str] = []
        ids: list[str] = []
        urls: list[str] = []
        for artist in track.get("artists") or []:
            if not isinstance(artist, Mapping):
                continue
            name = str(artist.get("name") or "").strip()
            if name:
                names.append(name)
            if artist.get("id"):
                ids.append(str(artist["id"]))
            href = (
                (artist.get("external_urls") or {}).get("spotify")
                if isinstance(artist.get("external_urls"), Mapping)
                else None
            )
            if href:
                urls.append(str(href))
        return names, ids, urls

    @staticmethod
    def _images(album: Mapping[str, Any]) -> list[SpotifyImage]:
        images: list[SpotifyImage] = []
        raw = album.get("images")
        if not isinstance(raw, list):
            return images
        for item in raw:
            if not isinstance(item, Mapping) or not item.get("url"):
                continue
            width = item.get("width")
            height = item.get("height")
            try:
                width_i = int(width) if width is not None else None
            except (TypeError, ValueError):
                width_i = None
            try:
                height_i = int(height) if height is not None else None
            except (TypeError, ValueError):
                height_i = None
            images.append(SpotifyImage(str(item["url"]), width_i, height_i))
        return images

    def _get_album(self, album_id: str) -> dict[str, Any]:
        if album_id not in self._album_cache:
            params: dict[str, Any] = {}
            if self.market:
                params["market"] = self.market
            self._album_cache[album_id] = self._request("GET", f"/albums/{album_id}", params=params)
        return self._album_cache[album_id]

    def search_track(self, *, title: str, album: str | None, duration_seconds: int | None) -> SpotifyResult | None:
        if not self.configured:
            raise SpotifyError("Spotify credentials are not configured")
        query = f"{title} {album}".strip() if album else str(title).strip()
        params: dict[str, Any] = {
            "q": query,
            "type": "track",
            "limit": max(1, min(50, int(self.config.get("search_limit", 10)))),
            "offset": 0,
        }
        if self.market:
            params["market"] = self.market
        payload = self._request("GET", "/search", params=params)
        tracks = (((payload.get("tracks") or {}).get("items")) if isinstance(payload.get("tracks"), Mapping) else None) or []
        if duration_seconds is None:
            return None
        tolerance_ms = max(0, int(self.config.get("duration_tolerance_seconds", 2))) * 1000
        for index, track in enumerate(tracks, start=1):
            if not isinstance(track, Mapping):
                continue
            try:
                duration_ms = int(track.get("duration_ms"))
            except (TypeError, ValueError):
                continue
            delta = abs(duration_ms - int(duration_seconds) * 1000)
            if delta > tolerance_ms:
                continue
            track_id = str(track.get("id") or "").strip()
            if not track_id:
                continue
            artists, artist_ids, artist_urls = self._artist_values(track)
            album_obj = track.get("album") if isinstance(track.get("album"), Mapping) else {}
            album_id = str(album_obj.get("id") or "").strip() or None
            album_url = None
            if isinstance(album_obj.get("external_urls"), Mapping):
                album_url = str(album_obj["external_urls"].get("spotify") or "") or None
            album_raw: dict[str, Any] = dict(album_obj)
            if album_id:
                try:
                    album_raw = self._get_album(album_id)
                except SpotifyError:
                    album_raw = dict(album_obj)
            images = self._images(album_raw)
            if not images:
                images = self._images(album_obj)
            largest = max(
                images,
                key=lambda image: (
                    (image.width or 0) * (image.height or 0),
                    image.width or 0,
                    image.height or 0,
                ),
                default=None,
            )
            copyrights: list[str] = []
            for item in album_raw.get("copyrights") or [] if isinstance(album_raw, Mapping) else []:
                if isinstance(item, Mapping) and item.get("text"):
                    copyrights.append(str(item["text"]))
            external_urls = track.get("external_urls") if isinstance(track.get("external_urls"), Mapping) else {}
            external_ids = track.get("external_ids") if isinstance(track.get("external_ids"), Mapping) else {}
            return SpotifyResult(
                track_id=track_id,
                track_name=str(track.get("name") or title),
                track_url=str(external_urls.get("spotify") or "") or None,
                uri=str(track.get("uri") or "") or None,
                artists=artists,
                artist_ids=artist_ids,
                artist_urls=artist_urls,
                album_name=str(album_raw.get("name") or album_obj.get("name") or album or "") or None,
                album_id=album_id,
                album_url=album_url,
                album_type=str(album_raw.get("album_type") or album_obj.get("album_type") or "") or None,
                album_release_date=str(album_raw.get("release_date") or album_obj.get("release_date") or "") or None,
                album_release_precision=str(album_raw.get("release_date_precision") or album_obj.get("release_date_precision") or "") or None,
                album_total_tracks=int(album_raw.get("total_tracks") or album_obj.get("total_tracks")) if (album_raw.get("total_tracks") or album_obj.get("total_tracks")) is not None else None,
                album_artwork_url=largest.url if largest else None,
                album_artwork_width=largest.width if largest else None,
                album_artwork_height=largest.height if largest else None,
                album_images=images,
                album_label=str(album_raw.get("label") or "") or None,
                album_copyrights=copyrights,
                duration_ms=duration_ms,
                duration_seconds=int(round(duration_ms / 1000)),
                duration_delta_ms=delta,
                explicit=bool(track.get("explicit")) if track.get("explicit") is not None else None,
                popularity=int(track["popularity"]) if isinstance(track.get("popularity"), (int, float)) else None,
                isrc=(str(external_ids.get("isrc") or "").strip() or None),
                track_number=int(track["track_number"]) if isinstance(track.get("track_number"), (int, float)) else None,
                disc_number=int(track["disc_number"]) if isinstance(track.get("disc_number"), (int, float)) else None,
                search_query=query,
                search_result_index=index,
                raw=dict(track),
                album_raw=album_raw,
            )
        return None


def apply_spotify_metadata(metadata: Any, result: SpotifyResult) -> Any:
    """Overlay catalog metadata without changing the actual downloaded audio duration."""
    from .metadata import _normalize_date

    changes: dict[str, Any] = {}
    if result.track_name:
        changes["title"] = result.track_name
    if result.artists:
        changes["artists"] = list(result.artists)
        changes["artist"] = result.artist_string
        changes["primary_artist"] = result.artists[0]
    if result.album_name:
        changes["album"] = result.album_name
    if result.album_artist_string:
        changes["album_artist"] = result.album_artist_string
    if result.album_release_date:
        changes["release_date"] = _normalize_date(result.album_release_date)
        changes["release_date_source"] = "spotify.album.release_date"
    if result.track_number is not None:
        changes["track_number"] = str(result.track_number)
        if result.album_total_tracks:
            changes["track_number"] = f"{result.track_number}/{result.album_total_tracks}"
    if result.disc_number is not None:
        changes["disc_number"] = str(result.disc_number)
    if result.album_copyrights and not metadata.copyright:
        changes["copyright"] = " | ".join(result.album_copyrights)
    if result.album_label and not metadata.publisher:
        changes["publisher"] = result.album_label
    return replace(metadata, **changes) if changes else metadata
