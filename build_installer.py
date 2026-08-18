"""
Build Paperfect Windows installer (NSIS) for public release.

Guarantees:
  - No developer API keys / private URLs / model names in the package
  - Empty library (no personal papers)
  - Bundled backend (paperfect.exe) + portable Node for PPT — no system Python/Node required
  - Windows 10+ 64-bit only

Outputs under dist_electron/:
  Paperfect-Setup-2.0.0.exe   (NSIS installer — main deliverable)
  Paperfect-2.0.0-portable.exe (optional single-file portable)
  win-unpacked/               (debug / smoke test)

Usage:
  python build_installer.py
  python build_installer.py --skip-backend   # reuse existing paperfect.exe if present
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
DIST = BASE / "dist_portable"
ELECTRON_OUT = BASE / "dist_electron"
TEMPLATE_ENV = BASE / "env.release.template"

CLEAN_ENV = """# Paperfect — user configuration (release)
# Fill in via the in-app Settings page. Installer ships empty on purpose.

PARSE_API_URL=
PARSE_API_KEY=
PARSE_MODEL=

CHAT_API_URL=
CHAT_API_KEY=
CHAT_MODEL=

PAPER_API_URL=
PAPER_API_KEY=
PAPER_MODEL=

ANNOTATOR_API_URL=
ANNOTATOR_API_KEY=
ANNOTATOR_MODEL=

TRANSLATE_API_URL=
TRANSLATE_API_KEY=
TRANSLATE_MODEL=
"""


def banner(msg: str) -> None:
    print(f"\n{'=' * 60}\n  {msg}\n{'=' * 60}", flush=True)


def run(cmd, cwd=None, check=True):
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd or BASE))
    if check and r.returncode != 0:
        raise RuntimeError(f"Command failed ({r.returncode}): {cmd}")
    return r


def write_clean_env(target: Path) -> None:
    text = CLEAN_ENV
    if TEMPLATE_ENV.is_file():
        text = TEMPLATE_ENV.read_text(encoding="utf-8")
    target.write_text(text, encoding="utf-8")
    # Safety: refuse to ship if any non-empty KEY/URL/MODEL slipped in
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip().upper()
        val = val.strip().strip("'").strip('"')
        if val and any(x in key for x in ("KEY", "URL", "MODEL", "TOKEN", "SECRET")):
            raise RuntimeError(f"Release .env must keep secrets empty, found value for {key}")
    print(f"  Wrote clean release .env -> {target}")


def wipe_user_data(dist: Path) -> None:
    data = dist / "data"
    for name in ("papers", "textbooks", "library_raw"):
        p = data / name
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
        p.mkdir(parents=True, exist_ok=True)
    for db in data.glob("*.db*"):
        try:
            db.unlink()
        except OSError:
            pass
    for log in dist.glob("*.log"):
        try:
            log.unlink()
        except OSError:
            pass
    print("  Cleared papers / textbooks / library_raw / logs / dbs")


def sync_frontend() -> None:
    """Push latest templates/static/ppt_editor into dist_portable."""
    src = BASE / "frontend"
    dst = DIST / "frontend"
    if not src.is_dir():
        raise FileNotFoundError(src)
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".git")
    shutil.copytree(src, dst, ignore=ignore)
    print("  Synced frontend -> dist_portable/frontend")


def ensure_runtime(skip_backend: bool) -> None:
    """Ensure paperfect.exe + node + slim ppt runtime exist."""
    from build_portable_exe import (
        compile_backend_exe,
        ensure_portable_node,
        slim_ppt_runtime,
        copy_app_sources,
        clean_dist_keep_wheels,
    )

    need_full = not (DIST / "paperfect.exe").is_file() or not (DIST / "runtime" / "node" / "node.exe").is_file()
    if need_full and not skip_backend:
        banner("Refreshing dist_portable core (backend + node + sources)")
        clean_dist_keep_wheels()
        copy_app_sources()
        slim_ppt_runtime()
        ensure_portable_node()
        compile_backend_exe()
    else:
        banner("Reusing existing paperfect.exe / node (patching release assets)")
        if not (DIST / "paperfect.exe").is_file():
            if skip_backend:
                raise FileNotFoundError("dist_portable/paperfect.exe missing; run without --skip-backend")
            compile_backend_exe()
        if not (DIST / "runtime" / "node" / "node.exe").is_file():
            ensure_portable_node()
        ppt_nm = DIST / "backend" / "standalone_pdf2ppt" / "ppt_maker" / "node_modules"
        if not ppt_nm.is_dir():
            slim_ppt_runtime()
        # Keep backend Python sources in sync for --script workers
        ignore = shutil.ignore_patterns(
            "__pycache__", "*.pyc", "node_modules", "dist", ".vite", "*.map"
        )
        backend_dst = DIST / "backend"
        if backend_dst.exists():
            # Update non-node_modules trees carefully: re-copy services/api/core
            for sub in ("api", "core", "services", "models"):
                s = BASE / "backend" / sub
                d = backend_dst / sub
                if d.exists():
                    shutil.rmtree(d, ignore_errors=True)
                if s.exists():
                    shutil.copytree(s, d, ignore=ignore)
            shutil.copy2(BASE / "backend" / "main.py", backend_dst / "main.py")
            # Keep generate_full_ppt.js current
            ppt_src = BASE / "backend" / "standalone_pdf2ppt" / "ppt_maker" / "generate_full_ppt.js"
            ppt_dst = backend_dst / "standalone_pdf2ppt" / "ppt_maker" / "generate_full_ppt.js"
            if ppt_src.is_file():
                ppt_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ppt_src, ppt_dst)
        else:
            copy_app_sources()
            slim_ppt_runtime()

    # Fresh multi-size ICO for exe / shortcut / taskbar (from paperfect_logo.png)
    try:
        run([sys.executable, str(BASE / "scripts" / "make_icons.py")], cwd=BASE)
    except Exception as e:
        print(f"  [WARN] make_icons.py: {e}")

    sync_frontend()
    # Fail packaging early if templates got mojibake (PowerShell Set-Content etc.)
    tpl_dir = DIST / "frontend" / "templates"
    if tpl_dir.is_dir():
        for html in tpl_dir.glob("*.html"):
            raw = html.read_bytes()
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError as e:
                raise RuntimeError(
                    f"Template not valid UTF-8 (would white-screen at runtime): {html} — {e}"
                ) from e
        print(f"  Templates UTF-8 OK ({len(list(tpl_dir.glob('*.html')))} files)")
    write_clean_env(DIST / ".env")
    wipe_user_data(DIST)

    # Drop accidental secrets elsewhere
    for bad in (DIST / ".env.local", DIST / "config.json"):
        if bad.exists():
            bad.unlink()

    # README for installed tree (shown only next to backend resources)
    (DIST / "README_RELEASE.txt").write_text(
        "Paperfect runtime (bundled with installer)\n"
        "==========================================\n"
        "- paperfect.exe  : FastAPI backend (no system Python needed)\n"
        "- runtime/node   : Node.js for PPT generation (no system Node needed)\n"
        "- frontend/      : UI assets\n"
        "- .env           : empty template; configure in-app Settings\n"
        "\n"
        "Requirements: Windows 10/11 64-bit\n",
        encoding="utf-8",
    )


def package_nsis() -> Path:
    banner("electron-builder NSIS installer (+ portable)")
    if ELECTRON_OUT.exists():
        shutil.rmtree(ELECTRON_OUT, ignore_errors=True)

    # nsis + portable + dir for verification
    # IMPORTANT: do NOT set win.signAndEditExecutable=false — that skips rcedit
    # and leaves the default Electron icon on Paperfect.exe / shortcuts / taskbar.
    run(
        [
            "npx.cmd",
            "electron-builder",
            "--win",
            "nsis",
            "portable",
            "dir",
            "--x64",
        ],
        cwd=BASE,
    )

    setup = None
    for p in ELECTRON_OUT.glob("*.exe"):
        if "Setup" in p.name or "setup" in p.name.lower():
            setup = p
            break
    if not setup:
        # artifactName Paperfect-Setup-${version}.exe
        cands = list(ELECTRON_OUT.glob("Paperfect-Setup*.exe"))
        setup = cands[0] if cands else None
    if not setup:
        raise FileNotFoundError("NSIS Setup exe not found in dist_electron/")

    # Also copy to project root for convenience
    root_copy = BASE / "Paperfect_Setup.exe"
    shutil.copy2(setup, root_copy)
    print(f"  Installer: {setup} ({setup.stat().st_size / 1e6:.1f} MB)")
    print(f"  Copy:      {root_copy}")
    return setup


def verify_no_secrets(setup_related_dir: Path) -> None:
    banner("Verify no secrets in packaged resources")
    env_path = setup_related_dir / "resources" / "dist_portable" / ".env"
    if not env_path.is_file():
        raise FileNotFoundError(f"Missing packaged .env: {env_path}")
    text = env_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip().upper()
        val = val.strip().strip("'").strip('"')
        if val and any(x in key for x in ("KEY", "URL", "MODEL", "TOKEN", "SECRET")):
            raise RuntimeError(f"SECRET LEAK in packaged .env: {key}={val[:8]}...")
    parser = (
        setup_related_dir
        / "resources"
        / "dist_portable"
        / "backend"
        / "standalone_pdf2ppt"
        / "ppt_maker"
        / "node_modules"
        / "openai"
        / "_vendor"
        / "partial-json-parser"
        / "parser.mjs"
    )
    if not parser.is_file():
        raise FileNotFoundError(f"PPT runtime broken (openai/_vendor missing): {parser}")
    if not (setup_related_dir / "resources" / "dist_portable" / "paperfect.exe").is_file():
        raise FileNotFoundError("paperfect.exe missing in package")
    if not (setup_related_dir / "resources" / "dist_portable" / "runtime" / "node" / "node.exe").is_file():
        raise FileNotFoundError("bundled node.exe missing in package")
    print("  OK: clean .env, backend exe, node, openai/_vendor present")


def write_user_readme(setup: Path) -> None:
    readme = BASE / "INSTALLER_README.md"
    readme.write_text(
        f"""# Paperfect 安装包说明（面向用户）

## 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | **Windows 10 或 Windows 11**（不支持 Windows 7/8） |
| 架构 | **64 位 (x64)** 仅支持 |
| 内存 | 建议 **8 GB+**（解析大论文时更稳） |
| 磁盘 | 安装约 **400–600 MB**，另需工作空间存放 PDF/PPT |
| 网络 | 需要可访问你配置的大模型 API（解析/翻译/PPT 均走 API） |
| 其它 | **无需**自备 Python / Node.js；安装包已内置运行时 |

不支持：32 位系统、ARM 版 Windows（未测试）、Windows Server 精简环境（未保证）。

## 安装文件

- 主安装包：`{setup.name}`  
  路径：`{setup}`  
  也可使用项目根目录副本：`Paperfect_Setup.exe`

## 安装步骤

1. 双击 **Paperfect-Setup-*.exe**
2. 选择安装目录（默认可改）
3. 完成安装后可从桌面快捷方式或开始菜单启动 **Paperfect**
4. 首次启动打开 **系统配置 / Settings**，填写：
   - API Base URL
   - API Key（可多个，逗号或界面多行）
   - 模型名称  
   保存后即可上传 PDF 使用

## 安装包内已包含（用户无需再装）

- Electron 桌面壳
- Python 后端（`paperfect.exe`，PyInstaller）
- Node.js 运行时（仅用于 PPT 生成）
- 前端页面与 PPT 编辑器静态资源

## 卸载

通过「设置 → 应用 → 已安装的应用」卸载 Paperfect。  
用户文库数据默认保留在安装目录下的 `resources/dist_portable/data`（卸载是否删除取决于系统/卸载选项）。

## 开发者重新打包

```bat
cd /d E:\\workspace\\paperfect
python build_installer.py
```

密钥不会打进安装包：使用 `env.release.template` 的空配置。
""",
        encoding="utf-8",
    )
    print(f"  Wrote {readme}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--skip-backend",
        action="store_true",
        help="Reuse existing dist_portable/paperfect.exe (faster if already built)",
    )
    args = ap.parse_args()

    print("Paperfect public installer builder")
    print(f"  BASE = {BASE}")

    ensure_runtime(skip_backend=args.skip_backend)
    setup = package_nsis()
    verify_no_secrets(ELECTRON_OUT / "win-unpacked")
    write_user_readme(setup)

    banner("DONE — public installer ready")
    print(
        f"""
Deliver to users:
  {setup}

Also:
  {BASE / 'Paperfect_Setup.exe'}
  {ELECTRON_OUT / 'Paperfect-2.0.0-portable.exe'}  (optional portable)

Remember: first launch → Settings → fill API URL / Key / Model.
Windows 10/11 x64 only. No system Python/Node required.
"""
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[BUILD FAILED] {e}", file=sys.stderr)
        sys.exit(1)
