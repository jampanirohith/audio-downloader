from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from src.db_playlist import PlaylistDB
from src.db_songs import SongsDB

( root / "db").mkdir(exist_ok=True)
PlaylistDB(root / "db" / "playlist.db")
SongsDB(root / "db" / "songs.db")
print("Initialized db/playlist.db and db/songs.db")
