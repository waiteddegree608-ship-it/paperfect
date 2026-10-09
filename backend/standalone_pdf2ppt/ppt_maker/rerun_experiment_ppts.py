# -*- coding: utf-8 -*-
"""Force-refresh PPT analysis + human-style layout for experiment papers.

Usage:
  python rerun_experiment_ppts.py              # English (default, for CHI experiment)
  python rerun_experiment_ppts.py zh           # Chinese
  python rerun_experiment_ppts.py en --layout-only   # relayout only (use cache)
"""
from pathlib import Path
import subprocess
import sys
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[3]  # paperfect/
ENV = dotenv_values(ROOT / ".env")
SCRIPT = Path(__file__).resolve().parent / "generate_full_ppt.js"
CWD = Path(__file__).resolve().parent


def clean_url(u: str) -> str:
    u = (u or "").strip().strip("'\"")
    if u.endswith("/"):
        u = u[:-1]
    for suf in ("/messages", "/chat/completions", "/chat"):
        if u.endswith(suf):
            u = u[: -len(suf)]
    if u.endswith("/"):
        u = u[:-1]
    return u or "https://api.siliconflow.cn/v1"


def pick_key(raw: str) -> str:
    raw = (raw or "").strip().strip("'\"")
    parts = [p.strip().strip("'\"") for p in raw.split(",") if p.strip()]
    return parts[0] if parts else ""


def main():
    lang = "en"
    layout_only = False
    for a in sys.argv[1:]:
        if a in ("en", "zh"):
            lang = a
        if a in ("--layout-only", "-l"):
            layout_only = True

    key = pick_key(ENV.get("PAPER_API_KEY") or ENV.get("CHAT_API_KEY") or ENV.get("PARSE_API_KEY"))
    url = clean_url(ENV.get("PAPER_API_URL") or ENV.get("CHAT_API_URL") or ENV.get("PARSE_API_URL"))
    model = (ENV.get("PAPER_MODEL") or ENV.get("CHAT_MODEL") or "qwen3.7-plus").strip().strip("'\"")
    if not key:
        print("No API key in .env")
        sys.exit(1)
    print("model:", model)
    print("url:", url)
    print("lang:", lang)
    print("force_refresh:", not layout_only)

    papers = ROOT / "data" / "papers"
    jobs = [
        (
            papers / "Attention Is All You Need" / "parsed" / "Attention Is All You Need_KnowledgeBase.md",
            papers / "Attention Is All You Need" / "images",
            papers / "Attention Is All You Need" / "pptx" / "Attention Is All You Need_Full_Presentation.pptx",
        ),
        (
            papers
            / "Feature Pyramid Networks for Object Detection"
            / "parsed"
            / "Feature Pyramid Networks for Object Detection_KnowledgeBase.md",
            papers / "Feature Pyramid Networks for Object Detection" / "images",
            papers
            / "Feature Pyramid Networks for Object Detection"
            / "pptx"
            / "Feature Pyramid Networks for Object Detection_Full_Presentation.pptx",
        ),
    ]

    for md, img, out in jobs:
        if not md.exists():
            print("Missing MD", md)
            sys.exit(1)
        print("\n==== RUNNING", out.name, "====")
        cmd = [
            "node",
            str(SCRIPT),
            str(md),
            str(img),
            str(out),
            "simple",
            key,
            model,
            url,
            lang,
        ]
        if not layout_only:
            cmd.append("--force-refresh")
        r = subprocess.run(cmd, cwd=str(CWD))
        if r.returncode != 0:
            print("FAILED", out.name, "code", r.returncode)
            sys.exit(r.returncode)
        print("OK", out)
    print("\nALL OK")


if __name__ == "__main__":
    main()
