# coding=utf-8
"""Atomic stage progress files so the UI can show real done/total, not a timer."""
from __future__ import annotations

import json
import os


def write_progress(path: str | None, done: int, total: int, label: str = "") -> None:
    if not path:
        path = os.environ.get("PAPERFECT_PROGRESS_FILE") or ""
    if not path:
        return
    total = max(1, int(total or 1))
    done = max(0, min(total, int(done or 0)))
    payload = {"done": done, "total": total, "label": label or f"{done}/{total}"}
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except OSError:
            pass


def read_progress(path: str | None) -> dict | None:
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        return data
    except Exception:
        return None
