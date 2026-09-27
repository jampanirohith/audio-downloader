from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import BinaryIO


def hash_file(path: str | Path, chunk_size: int = 1024 * 1024) -> tuple[int, str]:
    path = Path(path)
    digest = sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()
