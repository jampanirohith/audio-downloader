from __future__ import annotations

import io
import json
from pathlib import Path
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image
from mutagen.id3 import ID3, SYLT, USLT, GEOB, APIC
from mutagen.mp3 import MP3

from src.artwork import (
    ArtworkCandidate,
    choose_best_artwork,
    download_spotify_artwork,
    normalize_artwork,
)
from src.db_playlist import PlaylistDB
from src.db_songs import SONG_COLUMNS, SongsDB
from src.downloader import Downloader, AcquisitionResult
from src.embedder import embed_final_mp3, _parse_lrc
from src.metadata import normalize_metadata
from src.pipeline import Pipeline, safe_filename_component
from src.playlist_ingest import PlaylistIngestor
from src.spotify import SpotifyClient, SpotifyImage, SpotifyResult, apply_spotify_metadata
from src.lrclib import LRCLIBClient, LyricsResult
from src.validator import ValidationError, validate_final_mp3
from src.youtube_finder import VideoResult, build_search_query


def make_mp3(path: Path, seconds: int = 1) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
            f"sine=frequency=1000:duration={seconds}", "-codec:a", "libmp3lame", "-q:a", "7",
            str(path), "-y",
        ],
        check=True,
    )


def playlist_item(video_id: str = "YTM123") -> dict:
    return {
        "videoId": video_id,
        "setVideoId": "SET123",
        "title": "Song A",
        "artists": [{"name": "Artist A", "id": "ART1"}],
        "album": {"name": "Album A", "id": "ALB1"},
        "duration": "1:00",
        "duration_seconds": 60,
        "isAvailable": True,
        "videoType": "MUSIC_VIDEO_TYPE_ATV",
        "thumbnails": [{"url": "https://yt3.googleusercontent.com/abc=w120-h120", "width": 120, "height": 120}],
    }


def source_info() -> dict:
    return {
        "id": "YTM123", "title": "Song A", "artist": "Artist A",
        "artists": [{"name": "Artist A"}, {"name": "Artist B"}],
        "album": "Album A", "album_artist": "Artist A", "track_number": "2/10", "disc_number": "1/1",
        "release_date": "2024-02-03", "upload_date": "20240204", "timestamp": 1707004800,
        "description": "Full source description", "genre": "Pop", "composer": "Composer A", "publisher": "Publisher A",
        "copyright": "Copyright A", "license": "Standard YouTube License", "language": "en", "bpm": 120,
        "compilation": False, "encoder": "Lavf", "duration": 60, "ext": "mp3", "container": "mp3", "acodec": "mp3",
        "format_id": "251", "format_note": "low", "abr": 128, "asr": 44100, "channels": 2,
        "filesize": 12345, "filesize_approx": 12300,
        "webpage_url": "https://music.youtube.com/watch?v=YTM123",
        "original_url": "https://music.youtube.com/watch?v=YTM123", "display_id": "YTM123",
        "extractor": "youtube", "extractor_key": "Youtube", "webpage_url_basename": "watch", "webpage_url_domain": "music.youtube.com",
        "channel": "Artist A", "channel_id": "UC_SOURCE", "channel_url": "https://www.youtube.com/channel/UC_SOURCE",
        "channel_follower_count": 12345, "channel_is_verified": True, "uploader": "Artist A", "uploader_id": "UC_SOURCE",
        "uploader_url": "https://www.youtube.com/@artist", "view_count": 1234, "availability": "public", "age_limit": 0,
        "live_status": "not_live", "media_type": "video", "location": "Hyderabad",
        "thumbnail": "https://i.ytimg.com/x", "categories": ["Music"], "tags": ["song", "official"],
        "thumbnails": [
            {"id": "0", "url": "https://i.ytimg.com/x", "width": 480, "height": 360},
            {"id": "1", "url": "https://lh3.googleusercontent.com/album=w544-h544", "width": 544, "height": 544},
        ],
        "playlist": "Test Playlist", "playlist_id": "PL_SOURCE", "playlist_count": 2, "playlist_index": 1,
        "playlist_uploader": "Playlist Owner", "playlist_uploader_id": "owner", "playlist_channel": "Playlist Channel",
        "playlist_channel_id": "UC_PLAYLIST", "playlist_webpage_url": "https://www.youtube.com/playlist?list=PL_SOURCE",
        "formats": [{"format_id": "251", "ext": "webm", "acodec": "opus"}],
        "custom_source_field": "preserve-me",
    }


def video_result() -> VideoResult:
    raw = {
        "id": "YT999", "webpage_url": "https://www.youtube.com/watch?v=YT999", "title": "Song A - Official Video",
        "fulltitle": "Song A - Official Video", "channel": "Official Channel", "channel_id": "UC1", "uploader": "Official Channel",
        "uploader_id": "UC1", "upload_date": "20240205", "timestamp": 1707091200, "duration": 60,
        "view_count": 123456, "like_count": 1111, "comment_count": 222,
        "thumbnail": "https://i.ytimg.com/vi/YT999/maxresdefault.jpg", "description": "Video description",
        "categories": ["Music"], "tags": ["song", "official"], "channel_url": "https://www.youtube.com/channel/UC1",
        "channel_follower_count": 900000, "channel_is_verified": True, "uploader_url": "https://www.youtube.com/@official",
        "availability": "public", "age_limit": 0, "live_status": "not_live", "media_type": "video", "license": "YouTube",
        "webpage_url_basename": "watch", "webpage_url_domain": "youtube.com", "extractor": "youtube", "extractor_key": "Youtube",
    }
    return VideoResult(
        video_id="YT999", video_url=raw["webpage_url"], title=raw["title"], fulltitle=raw["fulltitle"], alt_title=None,
        channel=raw["channel"], channel_id=raw["channel_id"], uploader=raw["uploader"], uploader_id=raw["uploader_id"],
        upload_date="2024-02-05", timestamp=raw["timestamp"], release_date=None, release_timestamp=None, duration=60,
        views=123456, likes=1111, comments=222, thumbnail=raw["thumbnail"], description=raw["description"],
        categories=["Music"], tags=["song", "official"], extractor="youtube", extractor_key="Youtube", raw=raw,
        search_query="Song A Album A official video song", search_result_index=2, search_results_fetched=10,
    )


def spotify_result() -> SpotifyResult:
    raw = {
        "id": "SPOT1", "name": "Song A", "duration_ms": 60000, "track_number": 2, "disc_number": 1,
        "explicit": False, "popularity": 50, "external_ids": {"isrc": "US-SPOT-123"},
        "external_urls": {"spotify": "https://open.spotify.com/track/SPOT1"}, "uri": "spotify:track:SPOT1",
        "artists": [{"name": "Artist A", "id": "ART1", "external_urls": {"spotify": "https://open.spotify.com/artist/ART1"}}],
        "album": {"name": "Album A", "id": "ALB1", "album_type": "album", "release_date": "2024-02-03",
                  "release_date_precision": "day", "total_tracks": 10,
                  "external_urls": {"spotify": "https://open.spotify.com/album/ALB1"},
                  "images": [
                      {"url": "https://i.scdn.co/image/abc300", "width": 300, "height": 300},
                      {"url": "https://i.scdn.co/image/abc640", "width": 640, "height": 640},
                  ]},
    }
    album_raw = {
        "id": "ALB1", "name": "Album A", "album_type": "album", "release_date": "2024-02-03",
        "release_date_precision": "day", "total_tracks": 10, "label": "Publisher A",
        "copyrights": [{"text": "(P) 2024 Publisher A", "type": "P"}],
        "external_urls": {"spotify": "https://open.spotify.com/album/ALB1"},
        "images": [
            {"url": "https://i.scdn.co/image/abc300", "width": 300, "height": 300},
            {"url": "https://i.scdn.co/image/abc640", "width": 640, "height": 640},
        ],
    }
    return SpotifyResult(
        track_id="SPOT1", track_name="Song A", track_url=raw["external_urls"]["spotify"], uri=raw["uri"],
        artists=["Artist A"], artist_ids=["ART1"], artist_urls=["https://open.spotify.com/artist/ART1"],
        album_name="Album A", album_id="ALB1", album_url="https://open.spotify.com/album/ALB1", album_type="album",
        album_release_date="2024-02-03", album_release_precision="day", album_total_tracks=10,
        album_artwork_url="https://i.scdn.co/image/abc640", album_artwork_width=640, album_artwork_height=640,
        album_images=[SpotifyImage("https://i.scdn.co/image/abc300", 300, 300), SpotifyImage("https://i.scdn.co/image/abc640", 640, 640)],
        album_label="Publisher A", album_copyrights=["(P) 2024 Publisher A"],
        duration_ms=60000, duration_seconds=60, duration_delta_ms=0, explicit=False, popularity=50,
        isrc="US-SPOT-123", track_number=2, disc_number=1, search_query="Song A Album A", search_result_index=1,
        raw=raw, album_raw=album_raw,
    )


def lyrics_result() -> LyricsResult:
    lrc = "[ar:Artist A]\n[00:00.00]hello\n[00:00.50]world\n[00:30.250]last line\n"
    return LyricsResult(
        lyrics_id=99, track_name="Song A", artist_name="Artist A", album_name="Album A", duration=60,
        instrumental=False, synced_lyrics=lrc, query_track="Song A", query_artist="Artist A", query_album="Album A",
        duration_delta_seconds=0, match_method="lrclib_api_get", raw={"id": 99, "syncedLyrics": lrc},
    )


def make_entry() -> dict:
    return {
        "serial_number": 1, "playlist_position": 1, "ytm_playlist_id": "PL1", "ytm_video_id": "YTM123",
        "ytm_url": "https://music.youtube.com/watch?v=YTM123", "ytm_playlist_item_json": json.dumps(playlist_item(), sort_keys=True),
    }


def test_playlist_unavailable_entry_is_preserved(tmp_path: Path):
    db = PlaylistDB(tmp_path / "playlist.db")

    class FakeYTMusic:
        def get_playlist(self, *args, **kwargs):
            item = {"videoId": None, "title": "Unavailable", "artists": [{"name": "Artist"}], "album": {"name": "Album"}, "duration_seconds": 205, "isAvailable": False}
            return {"title": "Test", "tracks": [item, playlist_item()]}

    summary = PlaylistIngestor(db, ytmusic_factory=lambda *a: FakeYTMusic()).ingest("PL1")
    rows = db.get_all()
    assert summary["total_entries"] == 2
    assert rows[0]["serial_number"] == 1 and rows[0]["status"] == "error" and rows[0]["ytm_video_id"] is None
    assert rows[1]["serial_number"] == 2 and rows[1]["status"] == "pending"


def test_unavailable_entry_recovers_same_serial(tmp_path: Path):
    db = PlaylistDB(tmp_path / "playlist.db")
    available = {"tracks": [playlist_item()]}
    unavailable = {"tracks": [{**playlist_item(), "videoId": None, "isAvailable": False}]}

    class FakeYTMusic:
        def __init__(self): self.calls = 0
        def get_playlist(self, *args, **kwargs):
            self.calls += 1
            return unavailable if self.calls == 1 else available

    client = FakeYTMusic()
    ingestor = PlaylistIngestor(db, ytmusic_factory=lambda *a: client)
    ingestor.ingest("PL1")
    assert db.get_by_serial(1)["status"] == "error"
    ingestor.ingest("PL1")
    row = db.get_by_serial(1)
    assert row["serial_number"] == 1 and row["status"] == "pending" and row["ytm_video_id"] == "YTM123"


def test_metadata_normalization_preserves_source_details():
    meta = normalize_metadata(source_info(), playlist_item=playlist_item(), actual_duration=61)
    assert meta.title == "Song A"
    assert meta.artist == "Artist A, Artist B"
    assert meta.album == "Album A"
    assert meta.track_number == "2/10"
    assert meta.genre == "Pop"
    assert meta.source_channel_id == "UC_SOURCE"
    assert meta.raw["custom_source_field"] == "preserve-me"


def test_spotify_search_selects_first_duration_match(monkeypatch):
    client = SpotifyClient({"client_id": "id", "client_secret": "secret", "market": "IN", "search_limit": 10, "duration_tolerance_seconds": 2})
    monkeypatch.setattr(client, "_get_token", lambda: "token")
    payload = {"tracks": {"items": [
        {"id": "wrong", "name": "Wrong", "duration_ms": 55000, "external_urls": {}, "artists": [], "album": {}},
        spotify_result().raw,
        {**spotify_result().raw, "id": "third"},
    ]}}
    monkeypatch.setattr(client, "_request", lambda *a, **k: payload if a[1] == "/search" else spotify_result().album_raw)
    result = client.search_track(title="Song A", album="Album A", duration_seconds=60)
    assert result is not None
    assert result.track_id == "SPOT1"
    assert result.album_artwork_width == 640
    assert result.album_artwork_height == 640


def test_spotify_overlay_changes_player_metadata():
    meta = normalize_metadata(source_info(), playlist_item=playlist_item(), actual_duration=60)
    result = spotify_result()
    enriched = apply_spotify_metadata(meta, result)
    assert enriched.album == "Album A"
    assert enriched.track_number == "2/10"
    assert enriched.publisher == "Publisher A"


def test_spotify_artwork_download_selects_largest(monkeypatch, tmp_path: Path):
    small = io.BytesIO(); Image.new("RGB", (300, 300), "red").save(small, format="JPEG")
    large = io.BytesIO(); Image.new("RGB", (640, 640), "blue").save(large, format="JPEG")

    class Resp:
        def __init__(self, data: bytes): self.content = data; self.headers = {"Content-Type": "image/jpeg"}
        def raise_for_status(self): pass

    def fake_get(url, **kwargs):
        return Resp(large.getvalue() if "640" in url else small.getvalue())

    from src import artwork
    monkeypatch.setattr(artwork.requests, "get", fake_get)
    out, url, width, height, mime = download_spotify_artwork(
        spotify_result().album_images, tmp_path / "cover.jpg"
    )
    assert out.exists() and "640" in url and (width, height) == (640, 640) and mime == "image/jpeg"


def test_choose_best_artwork_prefers_largest_square():
    candidates = [
        ArtworkCandidate(Path("a.jpg"), 480, 360, "https://i.ytimg.com/a"),
        ArtworkCandidate(Path("b.jpg"), 544, 544, "https://lh3.googleusercontent.com/b"),
        ArtworkCandidate(Path("c.jpg"), 720, 720, "https://i.ytimg.com/c"),
    ]
    assert choose_best_artwork(candidates).path.name == "c.jpg"


def test_parse_lrc_creates_millisecond_events():
    events, plain = _parse_lrc("[offset:+100]\n[00:00.05]one\n[00:01]two\n")
    assert events == [("one", 150), ("two", 1100)]
    assert plain == "one\ntwo"


def test_embedder_writes_concise_metadata_and_synced_lyrics(tmp_path: Path):
    source = tmp_path / "master.mp3"; make_mp3(source, 1)
    art = tmp_path / "art.jpg"; Image.new("RGB", (640, 640), "blue").save(art, quality=100)
    meta = normalize_metadata(source_info(), playlist_item=playlist_item(), actual_duration=1)
    video = video_result(); spot = spotify_result(); lrc = lyrics_result()
    out = tmp_path / "final.mp3"
    embed_final_mp3(
        source_mp3=source, output_mp3=out, playlist_entry=make_entry(), metadata=meta, video=video,
        artwork_path=art, artwork_source_url=spot.album_artwork_url, artwork_width=640, artwork_height=640,
        youtube_search_query=video.search_query, spotify=spot, lyrics=lrc,
        lyrics_path="songs/synced_lyrics/final.lrc", lyrics_status="synced",
        metadata_json_path="songs/synced_lyrics/final.json", artwork_provider="spotify",
    )
    tags = ID3(out)
    assert tags.getall("TIT2") and tags.getall("TPE1") and tags.getall("TALB")
    assert tags.getall("TSRC")[0].text[0] == "US-SPOT-123"
    assert tags.getall("SYLT") and tags.getall("USLT")
    assert len(tags.getall("APIC")) == 1
    assert not tags.getall("COMM") and not tags.getall("GEOB")
    custom = {f.desc: f.text[0] for f in tags.getall("TXXX")}
    for key in ("ytm_video_id", "yt_video_id", "spotify_track_id", "spotify_album_id", "spotify_isrc", "lyrics_status"):
        assert key in custom


def test_validator_rejects_verbose_geob_metadata(tmp_path: Path):
    source = tmp_path / "master.mp3"; make_mp3(source)
    art = tmp_path / "art.jpg"; Image.new("RGB", (640, 640), "blue").save(art)
    meta = normalize_metadata(source_info(), playlist_item=playlist_item(), actual_duration=1)
    out = tmp_path / "final.mp3"
    embed_final_mp3(source_mp3=source, output_mp3=out, playlist_entry=make_entry(), metadata=meta, video=video_result(), artwork_path=art)
    tags = ID3(out)
    tags.add(GEOB(encoding=3, mime="application/json", filename="bad.json", desc="bad", data=b"{}"))
    tags.save(out, v2_version=4)
    with pytest.raises(ValidationError, match="GEOB metadata"):
        validate_final_mp3(path=out, playlist_entry=make_entry(), metadata=meta, video=video_result(), artwork_source_url=None, artwork_width=640, artwork_height=640)


def test_validator_accepts_synced_lyrics(tmp_path: Path):
    source = tmp_path / "master.mp3"; make_mp3(source)
    art = tmp_path / "art.jpg"; Image.new("RGB", (640, 640), "blue").save(art)
    meta = normalize_metadata(source_info(), playlist_item=playlist_item(), actual_duration=1)
    out = tmp_path / "final.mp3"; lrc_path = tmp_path / "final.lrc"; lrc = lyrics_result(); lrc_path.write_text(lrc.synced_lyrics, encoding="utf-8")
    embed_final_mp3(source_mp3=source, output_mp3=out, playlist_entry=make_entry(), metadata=meta, video=video_result(), artwork_path=art, artwork_source_url="x", artwork_width=640, artwork_height=640, lyrics=lrc, lyrics_path="final.lrc", lyrics_status="synced")
    validate_final_mp3(path=out, playlist_entry=make_entry(), metadata=meta, video=video_result(), artwork_source_url="x", artwork_width=640, artwork_height=640, lyrics=lrc, lyrics_path="final.lrc", lyrics_file_path=lrc_path, lyrics_status="synced")


def test_lrclib_uses_only_get(monkeypatch):
    client = LRCLIBClient({"user_agent": "test", "request_delay_seconds": 0.2})
    monkeypatch.setattr(client, "_throttle", lambda: None)
    calls = []
    def fake_get(*, params):
        calls.append(dict(params))
        return {"id": 42, "trackName": "Song A", "artistName": "Artist A", "albumName": "Album A", "duration": 60, "instrumental": False, "syncedLyrics": "[00:00.00] exact\n"}
    monkeypatch.setattr(client, "_get", fake_get)
    result = client.get_synced(title="Song A", artist="Artist A", album="Album A", duration_seconds=60)
    assert result is not None and result.lyrics_id == 42 and calls[0]["duration"] == 60


def test_lrclib_returns_none_for_plain_only(monkeypatch):
    client = LRCLIBClient({"user_agent": "test", "request_delay_seconds": 0.2})
    monkeypatch.setattr(client, "_throttle", lambda: None)
    monkeypatch.setattr(client, "_get", lambda **kwargs: {"id": 1, "plainLyrics": "plain", "syncedLyrics": None, "duration": 60})
    assert client.get_synced(title="Song A", artist="Artist A", album="Album A", duration_seconds=60) is None


def test_downloader_command_contract(tmp_path: Path):
    config = {
        "download": {"audio_format": "mp3", "audio_quality": "0", "write_info_json": True, "write_thumbnail": True, "convert_thumbnail": "jpg", "write_all_thumbnails": True},
        "yt_dlp_binary": "yt-dlp", "js_runtime": "none", "socket_timeout_seconds": 30,
    }
    command = Downloader(config, tmp_path).build_acquisition_command(temp_dir=tmp_path / "1", ytm_url="https://music.youtube.com/watch?v=YTM123")
    assert "--write-info-json" in command and "--write-all-thumbnails" in command
    assert "--add-metadata" not in command


def test_pipeline_creates_mp3_json_and_lrc_in_synced_folder(tmp_path: Path):
    playlist_db = PlaylistDB(tmp_path / "db" / "playlist.db")
    songs_db = SongsDB(tmp_path / "db" / "songs.db")
    item = playlist_item()
    playlist_db.insert_entry(
        serial_number=1, playlist_position=1, ytm_playlist_id="PL1", ytm_video_id="YTM123",
        ytm_url="https://music.youtube.com/watch?v=YTM123", title="Song A", artist="Artist A", album="Album A", duration=1,
        ytm_playlist_item_json=json.dumps(item), status="pending",
    )

    def acquire(**kwargs):
        temp = Path(kwargs["temp_dir"]); temp.mkdir(parents=True, exist_ok=True)
        master = temp / "master.mp3"; make_mp3(master)
        info = temp / "master.info.json"; info.write_text(json.dumps(source_info()), encoding="utf-8")
        art = temp / "master.jpg"; Image.new("RGB", (640, 640), "blue").save(art)
        return AcquisitionResult(temp, master, info, art, 1, "https://yt.example/art", 640, 640)

    lrc = lyrics_result()
    fake_spotify = SimpleNamespace(search_track=lambda **kwargs: spotify_result())
    fake_lrclib = SimpleNamespace(get_synced=lambda **kwargs: lrc)
    fake_downloader = SimpleNamespace(acquire=acquire)
    fake_finder = SimpleNamespace(find=lambda **kwargs: ("Song A Album A official video song", video_result()))
    config = {
        "paths": {"songs": "songs", "songs_with_synced_lyrics": "songs/synced_lyrics", "songs_without_synced_lyrics": "songs/no_synced_lyrics", "temp": "temp", "database": "db"},
        "retry": {"max_attempts": 1, "backoff_seconds": 0},
        "spotify": {"enabled": True, "artwork": {"enabled": False}},
        "lyrics": {"enabled": True},
        "filesystem": {"max_filename_length": 180},
    }
    pipeline = Pipeline(project_root=tmp_path, config=config, playlist_db=playlist_db, songs_db=songs_db, downloader=fake_downloader, youtube_finder=fake_finder, spotify_client=fake_spotify, lrclib_client=fake_lrclib)
    outcome = pipeline.process_one()
    assert outcome is not None and outcome.status == "completed"
    rows = songs_db.get_all(); assert len(rows) == 1
    row = rows[0]
    mp3 = tmp_path / row["mp3_path"]; lrc_path = tmp_path / row["lyrics_path"]; json_path = mp3.with_suffix(".json")
    assert mp3.exists() and lrc_path.exists() and json_path.exists()
    assert "songs/synced_lyrics/" in row["mp3_path"]
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["spotify"]["matched"] is True
    assert payload["youtube_video"]["selected"] is True
    assert payload["lyrics"]["embedded_in_mp3"] is True
    tags = ID3(mp3)
    assert tags.getall("SYLT") and tags.getall("USLT")
    assert not tags.getall("GEOB") and not tags.getall("COMM")


def test_pipeline_routes_no_synced_to_unsynced_folder(tmp_path: Path):
    playlist_db = PlaylistDB(tmp_path / "db" / "playlist.db")
    songs_db = SongsDB(tmp_path / "db" / "songs.db")
    playlist_db.insert_entry(serial_number=1, playlist_position=1, ytm_playlist_id="PL1", ytm_video_id="YTM123", ytm_url="https://music.youtube.com/watch?v=YTM123", title="Song A", artist="Artist A", album="Album A", duration=1, ytm_playlist_item_json=json.dumps(playlist_item()), status="pending")
    def acquire(**kwargs):
        temp = Path(kwargs["temp_dir"]); temp.mkdir(parents=True, exist_ok=True)
        master = temp / "master.mp3"; make_mp3(master)
        info = temp / "master.info.json"; info.write_text(json.dumps(source_info()), encoding="utf-8")
        art = temp / "master.jpg"; Image.new("RGB", (640, 640), "blue").save(art)
        return AcquisitionResult(temp, master, info, art, 1, "https://yt.example/art", 640, 640)
    fake_lrclib = SimpleNamespace(get_synced=lambda **kwargs: None)
    fake_finder = SimpleNamespace(find=lambda **kwargs: ("Song A Album A official video song", None))
    config = {"paths": {"songs": "songs", "songs_with_synced_lyrics": "songs/synced_lyrics", "songs_without_synced_lyrics": "songs/no_synced_lyrics", "temp": "temp", "database": "db"}, "retry": {"max_attempts": 1, "backoff_seconds": 0}, "spotify": {"enabled": False}, "lyrics": {"enabled": True}, "filesystem": {"max_filename_length": 180}}
    pipeline = Pipeline(project_root=tmp_path, config=config, playlist_db=playlist_db, songs_db=songs_db, downloader=SimpleNamespace(acquire=acquire), youtube_finder=fake_finder, lrclib_client=fake_lrclib)
    assert pipeline.process_one().status == "completed"
    row = songs_db.get_by_serial(1)
    assert "songs/no_synced_lyrics/" in row["mp3_path"]
    assert row["lyrics_path"] is None
    assert (tmp_path / row["mp3_path"]).with_suffix(".json").exists()


def test_songs_schema_has_new_output_columns(tmp_path: Path):
    db = SongsDB(tmp_path / "songs.db")
    with db.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(songs)")}
    assert set(SONG_COLUMNS).issubset(columns)
    assert {"metadata_json_path", "artwork_provider", "spotify_album_artwork_width", "spotify_album_artwork_height", "lyrics_embedded"}.issubset(columns)


def test_safe_filename_component_windows_rules():
    assert "/" not in safe_filename_component("a/b", "fallback")
    assert safe_filename_component("CON", "fallback").startswith("_")


def test_build_search_query_contract():
    assert build_search_query("Song A", "Album A") == "Song A Album A official video song"
    assert build_search_query("Song A", None) == "Song A official video song"


def test_no_api_search_literal_in_lrclib_source():
    source = Path("src/lrclib.py").read_text(encoding="utf-8")
    assert "requests.get(\n                    f\"{LRCLIB_API_URL}/search\"" not in source
    assert "LRCLIB_API_URL}/search" not in source



def test_spotify_artwork_preserves_original_bytes(monkeypatch, tmp_path: Path):
    from PIL import Image
    import io

    original = io.BytesIO()
    Image.new("RGB", (2048, 2048), "red").save(original, format="JPEG", quality=100, subsampling=0)
    payload = original.getvalue()

    class Response:
        content = payload
        headers = {"Content-Type": "image/jpeg"}
        def raise_for_status(self):
            return None

    monkeypatch.setattr("src.artwork.requests.get", lambda *args, **kwargs: Response())
    out, url, width, height, mime = download_spotify_artwork(
        [SpotifyImage("https://i.scdn.co/image/large", 2048, 2048), SpotifyImage("https://i.scdn.co/image/small", 640, 640)],
        tmp_path / "cover.jpg",
    )
    assert out.read_bytes() == payload
    assert (url, width, height, mime) == ("https://i.scdn.co/image/large", 2048, 2048, "image/jpeg")


def test_mp3_sidecar_can_hold_raw_verbose_metadata_without_embedding_it(tmp_path: Path):
    source = tmp_path / "master.mp3"; make_mp3(source)
    art = tmp_path / "art.jpg"; Image.new("RGB", (640, 640), "blue").save(art)
    meta = normalize_metadata(source_info(), playlist_item=playlist_item(), actual_duration=1)
    out = tmp_path / "final.mp3"
    embed_final_mp3(source_mp3=source, output_mp3=out, playlist_entry=make_entry(), metadata=meta, video=video_result(), artwork_path=art,
                    artwork_source_url="https://example/art", artwork_width=640, artwork_height=640, artwork_mime_type="image/jpeg",
                    youtube_search_query="Song A Album A official video song", metadata_json_path="final.json", artwork_provider="spotify")
    tags = ID3(out)
    assert not tags.getall("GEOB") and not tags.getall("COMM")
    custom = {f.desc: f.text[0] for f in tags.getall("TXXX")}
    assert "artwork_provider" not in custom
    assert "artwork_mime_type" not in custom


def test_pipeline_sidecar_holds_raw_source_details_not_mp3(tmp_path: Path):
    playlist_db = PlaylistDB(tmp_path / "db" / "playlist.db")
    songs_db = SongsDB(tmp_path / "db" / "songs.db")
    playlist_db.insert_entry(serial_number=1, playlist_position=1, ytm_playlist_id="PL1", ytm_video_id="YTM123", ytm_url="https://music.youtube.com/watch?v=YTM123", title="Song A", artist="Artist A", album="Album A", duration=1, ytm_playlist_item_json=json.dumps(playlist_item()), status="pending")
    def acquire(**kwargs):
        temp = Path(kwargs["temp_dir"]); temp.mkdir(parents=True, exist_ok=True)
        master = temp / "master.mp3"; make_mp3(master)
        info = temp / "master.info.json"; info.write_text(json.dumps(source_info()), encoding="utf-8")
        art = temp / "master.jpg"; Image.new("RGB", (640, 640), "blue").save(art)
        return AcquisitionResult(temp, master, info, art, 1, "https://yt.example/art", 640, 640)
    config={"paths":{"songs":"songs","songs_with_synced_lyrics":"songs/synced_lyrics","songs_without_synced_lyrics":"songs/no_synced_lyrics","temp":"temp","database":"db"},"retry":{"max_attempts":1,"backoff_seconds":0},"spotify":{"enabled":False},"lyrics":{"enabled":False},"filesystem":{"max_filename_length":180}}
    finder=SimpleNamespace(find=lambda **kwargs:("Song A Album A official video song", video_result()))
    pipe=Pipeline(project_root=tmp_path,config=config,playlist_db=playlist_db,songs_db=songs_db,downloader=SimpleNamespace(acquire=acquire),youtube_finder=finder)
    assert pipe.process_one().status == "completed"
    row=songs_db.get_by_serial(1)
    mp3=tmp_path/row["mp3_path"]; sidecar=mp3.with_suffix(".json")
    tags=ID3(mp3); custom={f.desc:f.text[0] for f in tags.getall("TXXX")}
    assert not tags.getall("COMM") and not tags.getall("GEOB")
    assert "yt_video_channel" not in custom and "source_description" not in custom and "source_age_limit" not in custom
    payload=json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["sources"]["yt_dlp_info_json"]["description"] == source_info()["description"]


def test_spotify_artwork_rejects_non_square_without_transform(monkeypatch, tmp_path: Path):
    class Response:
        content = b"not-an-image"
        headers = {"Content-Type": "image/jpeg"}
        def raise_for_status(self): return None
    # A real non-square JPEG payload.
    buf = io.BytesIO(); Image.new("RGB", (800, 600), "red").save(buf, format="JPEG")
    Response.content = buf.getvalue()
    monkeypatch.setattr("src.artwork.requests.get", lambda *args, **kwargs: Response())
    with pytest.raises(Exception, match="not square"):
        download_spotify_artwork([SpotifyImage("https://i.scdn.co/image/ns", 800, 600)], tmp_path / "cover.jpg")
    assert not (tmp_path / "cover.jpg").exists()


def test_pipeline_uses_largest_spotify_artwork_without_reencoding(monkeypatch, tmp_path: Path):
    import io
    # Make a deterministic JPEG payload that represents the Spotify response.
    buf = io.BytesIO()
    Image.new("RGB", (1200, 1200), "green").save(buf, format="JPEG", quality=100, subsampling=0)
    spotify_bytes = buf.getvalue()

    class Response:
        content = spotify_bytes
        headers = {"Content-Type": "image/jpeg"}
        def raise_for_status(self): return None

    monkeypatch.setattr("src.artwork.requests.get", lambda *args, **kwargs: Response())

    playlist_db = PlaylistDB(tmp_path / "db" / "playlist.db")
    songs_db = SongsDB(tmp_path / "db" / "songs.db")
    playlist_db.insert_entry(serial_number=1, playlist_position=1, ytm_playlist_id="PL1", ytm_video_id="YTM123", ytm_url="https://music.youtube.com/watch?v=YTM123", title="Song A", artist="Artist A", album="Album A", duration=1, ytm_playlist_item_json=json.dumps(playlist_item()), status="pending")
    def acquire(**kwargs):
        temp=Path(kwargs["temp_dir"]); temp.mkdir(parents=True, exist_ok=True)
        master=temp/"master.mp3"; make_mp3(master)
        info=temp/"master.info.json"; info.write_text(json.dumps(source_info()), encoding="utf-8")
        art=temp/"master.jpg"; Image.new("RGB", (640, 640), "blue").save(art)
        return AcquisitionResult(temp, master, info, art, 1, "https://yt.example/art", 640, 640)

    spot=spotify_result()
    fake_spotify=SimpleNamespace(search_track=lambda **kwargs: spot)
    finder=SimpleNamespace(find=lambda **kwargs:("Song A Album A official video song", video_result()))
    cfg={"paths":{"songs":"songs","songs_with_synced_lyrics":"songs/synced_lyrics","songs_without_synced_lyrics":"songs/no_synced_lyrics","temp":"temp","database":"db"},"retry":{"max_attempts":1,"backoff_seconds":0},"spotify":{"enabled":True,"artwork":{"enabled":True}},"lyrics":{"enabled":False},"filesystem":{"max_filename_length":180}}
    pipe=Pipeline(project_root=tmp_path,config=cfg,playlist_db=playlist_db,songs_db=songs_db,downloader=SimpleNamespace(acquire=acquire),youtube_finder=finder,spotify_client=fake_spotify)
    assert pipe.process_one().status == "completed"
    row=songs_db.get_by_serial(1); mp3=tmp_path/row["mp3_path"]; sidecar=mp3.with_suffix(".json")
    tags=ID3(mp3); apic=tags.getall("APIC"); assert len(apic)==1
    assert bytes(apic[0].data) == spotify_bytes
    payload=json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["artwork"]["provider"] == "spotify"
    assert payload["artwork"]["sha256"]
