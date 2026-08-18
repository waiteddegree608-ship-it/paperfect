"""Build multi-size Windows ICO + PNG from paperfect_logo.png."""
from pathlib import Path
import shutil
from PIL import Image

BASE = Path(__file__).resolve().parents[1]
src = BASE / "frontend" / "static" / "paperfect_logo.png"
if not src.is_file():
    src = BASE / "frontend" / "static" / "favicon.png"
if not src.is_file():
    raise SystemExit(f"No logo PNG found under frontend/static")

img = Image.open(src).convert("RGBA")
w, h = img.size
side = max(w, h)
canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)

sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
build = BASE / "build"
build.mkdir(exist_ok=True)
ico_path = build / "icon.ico"
canvas.save(ico_path, format="ICO", sizes=sizes)
print(f"wrote {ico_path} ({ico_path.stat().st_size} bytes)")

png256 = canvas.resize((256, 256), Image.Resampling.LANCZOS)
png_path = build / "icon.png"
png256.save(png_path, format="PNG")
print(f"wrote {png_path} ({png_path.stat().st_size} bytes)")

static = BASE / "frontend" / "static"
shutil.copy2(ico_path, static / "app_icon.ico")
png256.save(static / "app_icon.png", format="PNG")
print("synced frontend/static/app_icon.ico + app_icon.png")
print("ico magic:", ico_path.read_bytes()[:4].hex())
print("png magic:", png_path.read_bytes()[:8])
