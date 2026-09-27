from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
for relative in ("temp", "logs"):
    path = root / relative
    path.mkdir(exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)
for path in (root / "songs" / "original",):
    path.mkdir(parents=True, exist_ok=True)
    for child in path.glob("*.mp3*"):
        child.unlink(missing_ok=True)
print("Runtime working artifacts cleaned.")
