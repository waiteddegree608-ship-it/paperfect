# coding: utf-8
"""Locate the Paperfect install and put `backend/` on sys.path.

Other projects must point PAPERFECT_ROOT at a Paperfect checkout (or packaged
root). This file is imported first by server.py so MCP tools can `from backend...`.
"""
from __future__ import annotations

import os
import sys
from typing import Any


AGENT_DIR = os.path.dirname(os.path.abspath(__file__))


def paperfect_root() -> str:
    env = (os.environ.get("PAPERFECT_ROOT") or "").strip().strip('"')
    if env and os.path.isdir(env):
        return os.path.abspath(env)
    parent = os.path.dirname(AGENT_DIR)
    if os.path.isdir(os.path.join(parent, "backend")):
        return parent
    raise RuntimeError(
        "Cannot find Paperfect. Set env PAPERFECT_ROOT to the Paperfect repo "
        "(the folder that contains backend/ and frontend/)."
    )


def work_root() -> str:
    """Where paper workspaces are stored.

    PAPERFECT_WORK_DIR  →  explicit output root (recommended for other projects)
    else                →  {PAPERFECT_ROOT}/data/papers  (same as the desktop app)
    """
    env = (os.environ.get("PAPERFECT_WORK_DIR") or "").strip().strip('"')
    if env:
        path = os.path.abspath(env)
        os.makedirs(path, exist_ok=True)
        return path
    path = os.path.join(paperfect_root(), "data", "papers")
    os.makedirs(path, exist_ok=True)
    return path


def bootstrap() -> str:
    root = paperfect_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if sys.platform == "win32":
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    return root


def call_blocking(fn, *args, **kwargs):
    """Run a sync function even if the MCP server is already inside an event loop.

    `paper_translator.translate_pdf` uses asyncio.run(); calling it on the MCP
    event loop would raise. Always hop to a worker thread.
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(fn, *args, **kwargs).result()


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def ok(**payload: Any) -> dict:
    return {"ok": True, **payload}


def err(message: str, **payload: Any) -> dict:
    return {"ok": False, "error": message, **payload}
