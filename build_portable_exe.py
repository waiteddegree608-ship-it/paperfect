"""
Build a self-contained Paperfect portable EXE (no run.bat / no system server).

Output:
  dist_electron/Paperfect <version>.exe     — single portable Electron launcher
  dist_electron/win-unpacked/Paperfect.exe  — unpacked folder (easier to debug)

Does NOT build the NSIS installer (that is a later step after you verify the exe).

What gets bundled:
  - Electron shell (main.js)
  - dist_portable/paperfect.exe  (PyInstaller FastAPI backend, headless)
  - frontend + backend sources (for static files + --script workers)
  - slim ppt_maker runtime (generate_full_ppt.js + prod node_modules)
  - portable Node.js under runtime/node (for PPT generation)
  - empty data/ skeleton + .env template
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
DIST = BASE / "dist_portable"
ELECTRON_OUT = BASE / "dist_electron"
NODE_VERSION = "22.14.0"
NODE_ZIP_URL = (
    f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-x64.zip"
)


def banner(msg: str) -> None:
    print(f"\n{'=' * 60}\n  {msg}\n{'=' * 60}", flush=True)


def run(cmd, cwd=None, check=True, env=None):
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    r = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd or BASE),
        env=env,
        text=True,
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"Command failed ({r.returncode}): {cmd}")
    return r


def dir_size_mb(path: Path) -> float:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total / (1024 * 1024)


def clean_dist_keep_wheels() -> None:
    banner("Step 0: Prepare dist_portable (keep _wheels cache if present)")
    keep_wheels = DIST / "_wheels"
    wheels_backup = BASE / "_wheels_build_cache"
    if keep_wheels.is_dir():
        if wheels_backup.exists():
            shutil.rmtree(wheels_backup, ignore_errors=True)
        shutil.move(str(keep_wheels), str(wheels_backup))
        print("  Parked _wheels for reuse")

    if DIST.exists():
        shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir(parents=True, exist_ok=True)

    if wheels_backup.is_dir():
        shutil.move(str(wheels_backup), str(keep_wheels))
        print(f"  Restored _wheels ({dir_size_mb(keep_wheels):.0f} MB)")


def copy_app_sources() -> None:
    banner("Step 1: Copy backend + frontend (exclude bloat)")
    ignore = shutil.ignore_patterns(
        "__pycache__",
        "*.pyc",
        ".git",
        "node_modules",
        "dist",
        ".vite",
        "*.map",
        "paperfect_library.db",
        "paperfect_library.db-*",
        "database.db",
        "debug_output.json",
        "search_debug.log",
    )
    shutil.copytree(BASE / "backend", DIST / "backend", ignore=ignore)
    shutil.copytree(BASE / "frontend", DIST / "frontend", ignore=ignore)

    # Data skeleton only (no user papers)
    data = DIST / "data"
    data.mkdir(exist_ok=True)
    for name in ("keyword_dict.json", "venue_dict.json"):
        src = BASE / "data" / name
        if src.exists():
            shutil.copy2(src, data / name)
    for d in ("papers", "textbooks", "library_raw"):
        (data / d).mkdir(exist_ok=True)

    # .env: prefer project .env so your machine can verify; strip nothing critical
    env_src = BASE / ".env"
    env_dst = DIST / ".env"
    if env_src.exists():
        shutil.copy2(env_src, env_dst)
        print("  Copied project .env into package (for your verification)")
    else:
        env_dst.write_text(
            "PARSE_API_URL=https://api.siliconflow.cn/v1\n"
            "PARSE_API_KEY=\n"
            "PARSE_MODEL=Qwen/Qwen2.5-72B-Instruct\n"
            "CHAT_API_URL=https://api.siliconflow.cn/v1\n"
            "CHAT_API_KEY=\n"
            "CHAT_MODEL=Qwen/Qwen2.5-72B-Instruct\n",
            encoding="utf-8",
        )
        print("  Wrote empty .env template")

    # Lightweight readme next to backend
    (DIST / "README_PORTABLE.txt").write_text(
        "Paperfect portable runtime bundle\n"
        "Launched by Electron — do not run install.bat for the packaged EXE.\n"
        "Edit .env next to paperfect.exe to set API keys if needed.\n",
        encoding="utf-8",
    )
    print("  Sources copied.")


def slim_ppt_runtime() -> None:
    banner("Step 2: Slim PPT Node runtime (prod deps only)")
    ppt_src = BASE / "backend" / "standalone_pdf2ppt" / "ppt_maker"
    ppt_dst = DIST / "backend" / "standalone_pdf2ppt" / "ppt_maker"
    ppt_dst.mkdir(parents=True, exist_ok=True)

    # Only files needed to generate PPTX at runtime
    for name in ("generate_full_ppt.js", "generate_ppt.js"):
        src = ppt_src / name
        if src.exists():
            shutil.copy2(src, ppt_dst / name)

    pkg = {
        "name": "paperfect-ppt-runtime",
        "private": True,
        "type": "module",
        "dependencies": {
            "image-size": "^2.0.2",
            "openai": "^6.34.0",
            "pptxgenjs": "^4.0.1",
        },
    }
    (ppt_dst / "package.json").write_text(json.dumps(pkg, indent=2), encoding="utf-8")

    print("  npm install --omit=dev in ppt_maker runtime...")
    run(["npm.cmd", "install", "--omit=dev", "--no-audit", "--no-fund"], cwd=ppt_dst)
    print(f"  ppt_maker runtime size: {dir_size_mb(ppt_dst):.1f} MB")


def ensure_portable_node() -> None:
    banner("Step 3: Bundle portable Node.js")
    node_dir = DIST / "runtime" / "node"
    node_exe = node_dir / "node.exe"
    if node_exe.is_file():
        print(f"  Already present: {node_exe}")
        return

    cache = BASE / "_node_cache"
    cache.mkdir(exist_ok=True)
    zip_path = cache / f"node-v{NODE_VERSION}-win-x64.zip"
    if not zip_path.is_file():
        print(f"  Downloading {NODE_ZIP_URL} ...")
        urllib.request.urlretrieve(NODE_ZIP_URL, zip_path)
        print(f"  Saved {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB)")
    else:
        print(f"  Using cached zip: {zip_path.name}")

    extract_tmp = cache / f"node-v{NODE_VERSION}-win-x64"
    if extract_tmp.exists():
        shutil.rmtree(extract_tmp, ignore_errors=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(cache)

    # zip root is node-vXX-win-x64/
    extracted = cache / f"node-v{NODE_VERSION}-win-x64"
    if not extracted.is_dir():
        # fallback: first dir
        dirs = [p for p in cache.iterdir() if p.is_dir() and p.name.startswith("node-")]
        extracted = dirs[0]

    node_dir.parent.mkdir(parents=True, exist_ok=True)
    if node_dir.exists():
        shutil.rmtree(node_dir, ignore_errors=True)
    # Keep only node.exe + LICENSE (enough for generate_full_ppt.js)
    node_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(extracted / "node.exe", node_dir / "node.exe")
    for extra in ("LICENSE", "README.md"):
        if (extracted / extra).exists():
            shutil.copy2(extracted / extra, node_dir / extra)
    print(f"  Bundled node.exe -> {node_exe} ({node_exe.stat().st_size / 1e6:.1f} MB)")


def compile_backend_exe() -> None:
    banner("Step 4: PyInstaller paperfect.exe (backend)")
    # Keep build/icon.* — put pyinstaller work under build/pyi
    work = BASE / "build" / "pyi"
    spec_dist = BASE / "build" / "pyi_dist"
    for p in (work, spec_dist):
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
        p.mkdir(parents=True, exist_ok=True)

    icon = BASE / "build" / "icon.ico"
    # Exclude heavy ML stacks that may be installed site-wide but are NOT used by Paperfect.
    excludes = [
        "torch",
        "torchvision",
        "torchaudio",
        "tensorflow",
        "keras",
        "tensorboard",
        "sklearn",
        "scikit-learn",
        "scipy",
        "pandas",
        "matplotlib",
        "numpy.tests",
        "cv2",
        "PIL.ImageQt",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
        "jedi",
        "parso",
        "pygame",
        "tkinter",
        "webview",
        "pyarrow",
        "fsspec",
        "zmq",
        "transformers",
        "onnx",
        "onnxruntime",
    ]
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--noconsole",
        "--name",
        "paperfect",
        "--distpath",
        str(spec_dist),
        "--workpath",
        str(work),
        "--specpath",
        str(work),
        "--paths",
        str(BASE),
        # Prefer lean collection: only what Paperfect actually imports
        "--collect-submodules",
        "uvicorn",
        "--collect-data",
        "jinja2",
        "--collect-data",
        "certifi",
        "--collect-binaries",
        "pymupdf",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols",
        "--hidden-import",
        "uvicorn.protocols.http",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "uvicorn.lifespan",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--hidden-import",
        "backend",
        "--hidden-import",
        "backend.api.paper_router",
        "--hidden-import",
        "backend.api.ppt_router",
        "--hidden-import",
        "backend.api.chat_router",
        "--hidden-import",
        "backend.api.config_router",
        "--hidden-import",
        "backend.api.library_router",
        "--hidden-import",
        "backend.services.file_manager",
        "--hidden-import",
        "backend.services.task_runner",
        "--hidden-import",
        "backend.services.llm_client",
        "--hidden-import",
        "backend.services.project_manager",
        "--hidden-import",
        "backend.services.pdf_annotator",
        "--hidden-import",
        "backend.services.paper_translator",
        "--hidden-import",
        "backend.services.paper_analyzer",
        "--hidden-import",
        "backend.models.database",
        "--hidden-import",
        "fitz",
        "--hidden-import",
        "openai",
        "--hidden-import",
        "sqlalchemy",
        "--hidden-import",
        "dotenv",
        "--hidden-import",
        "multipart",
        "--hidden-import",
        "pydantic",
        "--hidden-import",
        "pptx",
        "--hidden-import",
        "aiofiles",
        "--hidden-import",
        "httpx",
        "--hidden-import",
        "anyio",
        "--hidden-import",
        "sniffio",
        "--hidden-import",
        "h11",
        "--hidden-import",
        "starlette",
        "--hidden-import",
        "email.mime.text",
        "--hidden-import",
        "email.mime.multipart",
    ]
    for ex in excludes:
        cmd.extend(["--exclude-module", ex])
    if icon.is_file():
        cmd.extend(["--icon", str(icon)])
    cmd.append(str(BASE / "backend" / "main.py"))

    # Clean previous analysis so excludes take effect
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)

    run(cmd, cwd=BASE)

    built = spec_dist / "paperfect.exe"
    if not built.is_file():
        raise FileNotFoundError(f"PyInstaller did not produce {built}")
    dest = DIST / "paperfect.exe"
    if dest.exists():
        dest.unlink()
    shutil.copy2(built, dest)
    print(f"  [OK] {dest} ({dest.stat().st_size / 1e6:.1f} MB)")


def smoke_test_backend() -> None:
    banner("Step 5: Smoke-test paperfect.exe --headless")
    import time
    import urllib.error
    import urllib.request as ureq

    # free port
    if sys.platform == "win32":
        subprocess.run(
            'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :8900 ^| findstr LISTENING\') do taskkill /F /PID %a',
            shell=True,
            capture_output=True,
        )

    exe = DIST / "paperfect.exe"
    proc = subprocess.Popen(
        [str(exe), "--headless"],
        cwd=str(DIST),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    ok = False
    try:
        for i in range(90):
            time.sleep(1)
            try:
                with ureq.urlopen("http://127.0.0.1:8900/api/health", timeout=2) as r:
                    body = r.read().decode("utf-8", errors="replace")
                    if r.status == 200 and "ok" in body.lower():
                        print(f"  Health OK after {i + 1}s: {body[:120]}")
                        ok = True
                        break
            except Exception:
                pass
            if proc.poll() is not None:
                print(f"  Backend exited early code={proc.returncode}")
                break
        if not ok:
            # fallback root
            try:
                with ureq.urlopen("http://127.0.0.1:8900/", timeout=3) as r:
                    if r.status == 200:
                        print("  Root OK (no /api/health)")
                        ok = True
            except Exception as e:
                print(f"  Smoke test failed: {e}")
    finally:
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                )
            else:
                proc.kill()
        except Exception:
            pass
    if not ok:
        raise RuntimeError("Backend smoke test failed — fix before Electron package")


def package_electron_portable() -> None:
    banner("Step 6: electron-builder (portable + dir only)")
    # Ensure icon exists
    icon = BASE / "build" / "icon.ico"
    if not icon.is_file():
        png = BASE / "frontend" / "static" / "app_icon.ico"
        if png.is_file():
            shutil.copy2(png, icon)
            print(f"  Copied icon from {png}")

    # Clear previous electron output
    if ELECTRON_OUT.exists():
        shutil.rmtree(ELECTRON_OUT, ignore_errors=True)

    env = os.environ.copy()
    # portable only — no NSIS installer yet
    # Keep signAndEditExecutable enabled (default) so rcedit embeds build/icon.ico
    # into Paperfect.exe — otherwise Windows shows the default Electron logo.
    run(
        [
            "npx.cmd",
            "electron-builder",
            "--win",
            "portable",
            "dir",
            "--x64",
        ],
        cwd=BASE,
        env=env,
    )

    # List outputs
    print("\n  Outputs:")
    if ELECTRON_OUT.exists():
        for p in sorted(ELECTRON_OUT.rglob("*.exe")):
            if p.is_file():
                print(f"    {p.relative_to(BASE)}  ({p.stat().st_size / 1e6:.1f} MB)")
    unpacked = ELECTRON_OUT / "win-unpacked" / "Paperfect.exe"
    if unpacked.is_file():
        print(f"\n  RECOMMENDED TEST: {unpacked}")
        print("  (unpacked folder keeps logs next to resources easier to inspect)")


def main() -> None:
    print("Paperfect portable EXE builder")
    print(f"  BASE = {BASE}")
    clean_dist_keep_wheels()
    copy_app_sources()
    slim_ppt_runtime()
    ensure_portable_node()
    compile_backend_exe()
    smoke_test_backend()
    package_electron_portable()
    banner("DONE")
    print(
        """
Next (for you):
  1. Close any running Paperfect / run.bat
  2. Launch:
       E:\\workspace\\paperfect\\dist_electron\\win-unpacked\\Paperfect.exe
     or the portable:
       E:\\workspace\\paperfect\\dist_electron\\Paperfect *.exe
  3. Verify library, theme, PPT toolbar, open a paper
  4. After you confirm OK, we build the installer (NSIS)

Note: first backend start can take 20–60s (PyInstaller one-file unpack).
"""
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[BUILD FAILED] {e}", file=sys.stderr)
        sys.exit(1)
