"""Export an allowlisted source tree for review without local research or secrets.

This does not push to GitHub or rewrite the repository's history.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ("backend", "frontend", "docs", "paperfect_agent", "scripts", "tests", ".github")
FILES = ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "CONTRIBUTING.md", ".gitignore", ".env.example", "env.release.template", "requirements.txt", "package.json", "package-lock.json", "main.js", "loading.html", "run.bat", "start_paperfect.cmd", "build_portable_exe.py", "build_installer.py", "build_package.py", "installer.py", "batch_label.py")
EXCLUDED_DIRS = {"node_modules", "__pycache__", "dist", "build", "cache", ".git", ".venv", "venv", "dev", "history"}
EXCLUDED_NAMES = {"config.json", "ai_payload.json", ".env"}
EXCLUDED_SUFFIXES = {".pyc", ".log", ".bak", ".db", ".pdf", ".pptx", ".mp4", ".zip", ".exe"}
TOKEN = re.compile(r"(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,})")


def source_files():
    for name in FILES:
        path = ROOT / name
        if path.is_file():
            yield path
    for directory in DIRECTORIES:
        for path in sorted((ROOT / directory).rglob("*")):
            rel = path.relative_to(ROOT)
            if path.is_symlink() or not path.is_file() or EXCLUDED_DIRS.intersection(rel.parts) or path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES or path.name.startswith(".env."):
                continue
            yield path


def export(output):
    target = Path(output).resolve()
    if target.exists():
        raise ValueError("Output must be a new directory; existing files are never replaced")
    if target.is_relative_to(ROOT):
        raise ValueError("Choose an output directory outside the working repository")
    files = list(source_files())
    # Preflight before any copy. Report locations only, never token values.
    findings = []
    for path in files:
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeError:
            continue
        if TOKEN.search(content):
            findings.append(str(path.relative_to(ROOT)))
    if findings:
        raise ValueError("Credential-shaped tokens require review: " + ", ".join(findings))
    manifest = []
    for source in files:
        relative = source.relative_to(ROOT)
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        manifest.append({"path": relative.as_posix(), "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()})
    (target / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(manifest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(f"Exported {export(args.output)} files to {Path(args.output).resolve()}")
