# coding=utf-8
"""Per-paper LLM usage / timing log for cost diagnosis."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional


def usage_path(target_dir: str) -> str:
    return os.path.join(target_dir, "usage.json")


def load_usage(target_dir: str) -> Dict[str, Any]:
    path = usage_path(target_dir)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"stages": {}, "updated_at": None}


def record_stage(
    target_dir: str,
    stage: str,
    *,
    calls: int = 0,
    prompt_chars: int = 0,
    completion_chars: int = 0,
    elapsed_sec: float = 0.0,
    extra: Optional[Dict[str, Any]] = None,
):
    data = load_usage(target_dir)
    stages = data.setdefault("stages", {})
    prev = stages.get(stage, {})
    merged = {
        "calls": int(prev.get("calls", 0)) + int(calls),
        "prompt_chars": int(prev.get("prompt_chars", 0)) + int(prompt_chars),
        "completion_chars": int(prev.get("completion_chars", 0)) + int(completion_chars),
        "elapsed_sec": round(float(prev.get("elapsed_sec", 0)) + float(elapsed_sec), 2),
        # rough: ~4 chars / token
        "est_prompt_tokens": 0,
        "est_completion_tokens": 0,
    }
    merged["est_prompt_tokens"] = merged["prompt_chars"] // 4
    merged["est_completion_tokens"] = merged["completion_chars"] // 4
    if extra:
        merged.update(extra)
    stages[stage] = merged
    data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(target_dir, exist_ok=True)
    with open(usage_path(target_dir), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data
