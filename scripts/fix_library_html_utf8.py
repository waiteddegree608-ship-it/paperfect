"""Ensure library.html is valid UTF-8 and bump main.js cache-bust."""
from pathlib import Path
import re
import shutil

BASE = Path(__file__).resolve().parents[1]
src = BASE / "frontend" / "templates" / "library.html"
text = src.read_text(encoding="utf-8")
text2, n = re.subn(
    r"library/main\.js(\?v=[^\"']*)?",
    "library/main.js?v=20260806fix",
    text,
    count=1,
)
src.write_text(text2, encoding="utf-8", newline="\n")
src.read_bytes().decode("utf-8")
print(f"OK {src} (cache-bust replacements={n})")

# Sync into dist trees
for dest_root in (
    BASE / "dist_portable" / "frontend" / "templates",
    BASE / "dist_electron" / "win-unpacked" / "resources" / "dist_portable" / "frontend" / "templates",
):
    if dest_root.is_dir():
        shutil.copy2(src, dest_root / "library.html")
        print(f"synced -> {dest_root / 'library.html'}")
