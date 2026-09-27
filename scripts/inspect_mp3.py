from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

from PIL import Image
from mutagen.id3 import ID3
from mutagen.mp3 import MP3


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect concise metadata embedded in a Phase 1 MP3 and its sidecar JSON")
    parser.add_argument("path")
    args = parser.parse_args()
    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"File does not exist: {path}")

    audio = MP3(path)
    tags = ID3(path)
    print(f"FILE: {path}")
    print(f"SIZE: {path.stat().st_size}")
    print(f"DURATION: {audio.info.length:.3f}s")

    print("\nSTANDARD ID3 FRAMES")
    for frame_id in ("TIT2", "TPE1", "TPE2", "TALB", "TDRC", "TRCK", "TPOS", "TCON", "TCOM", "TPUB", "TCOP", "TLAN", "TBPM", "TCMP", "TENC", "TLEN", "TSRC"):
        for frame in tags.getall(frame_id):
            print(f"{frame_id}: {getattr(frame, 'text', '')}")

    print("\nTXXX")
    for frame in tags.getall("TXXX"):
        print(f"TXXX:{frame.desc}: {frame.text}")

    print("\nUFID")
    for frame in tags.getall("UFID"):
        try:
            value = frame.data.decode("utf-8")
        except Exception:
            value = repr(frame.data)
        print(f"UFID:{frame.owner}: {value}")

    print("\nWXXX")
    for frame in tags.getall("WXXX"):
        print(f"WXXX:{frame.desc}: {frame.url}")

    print("\nLYRICS")
    print(f"SYLT frames: {len(tags.getall('SYLT'))}")
    print(f"USLT frames: {len(tags.getall('USLT'))}")
    print(f"GEOB frames: {len(tags.getall('GEOB'))}")
    print(f"COMM frames: {len(tags.getall('COMM'))}")

    print("\nARTWORK")
    for apic in tags.getall("APIC"):
        try:
            with Image.open(io.BytesIO(apic.data)) as image:
                print(f"APIC:type={apic.type} desc={apic.desc} mime={apic.mime} size={len(apic.data)} image={image.width}x{image.height} format={image.format}")
        except Exception as exc:
            print(f"APIC decode ERROR: {exc}")

    sidecar = path.with_suffix(".json")
    print("\nSIDECAR JSON")
    print(f"exists: {sidecar.exists()}")
    if sidecar.exists():
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            print(f"schema_version: {payload.get('schema_version')}")
            print(f"top-level keys: {', '.join(sorted(payload.keys()))}")
            print(f"lyrics status: {(payload.get('lyrics') or {}).get('status')}")
            print(f"artwork provider: {(payload.get('artwork') or {}).get('provider')}")
        except Exception as exc:
            print(f"sidecar JSON ERROR: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
