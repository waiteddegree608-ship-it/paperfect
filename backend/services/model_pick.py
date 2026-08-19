# coding=utf-8
"""Model selection: OpenCode quality models stay as configured; only downshift siliconflow giants."""
from __future__ import annotations

import os
import re

_SLOW = re.compile(
    r"thinking|reasoner|qwq|r1\b|235b|397b|72b|a22b",
    re.I,
)
_VL = re.compile(r"\bvl\b|vision|gpt-4o$|gemini-.+-pro", re.I)
_HEAVY_VL = re.compile(r"235b|72b|32b|30b", re.I)

# MiMo (Xiaomi) is a hybrid-reasoning model: unlike qwen3.7-plus it emits a
# <think>...</think> trace before answering unless told otherwise, and that
# trace eats into the same max_tokens budget. Detect it alongside the other
# CoT-heavy models so callers can (a) ask it to skip thinking and (b) give it
# enough headroom when the provider doesn't honor that request.
_REASONING = re.compile(r"thinking|reasoner|qwq|\br1\b|mimo", re.I)

OPENCODE_DEFAULT = "qwen3.7-plus"
OPENCODE_URL = "https://opencode.ai/zen/go/v1"
FAST_TEXT_DEFAULT = "Qwen/Qwen3-8B"
FAST_VISION_DEFAULT = "Qwen/Qwen3-VL-8B-Instruct"


def is_slow_or_thinking(name: str) -> bool:
    return bool(_SLOW.search(name or ""))


def is_vision_model(name: str) -> bool:
    n = name or ""
    return bool(_VL.search(n)) or "vl-" in n.lower() or "vl_" in n.lower()


def is_opencode(cfg: dict | None = None, url: str = "") -> bool:
    blob = " ".join(
        [
            url or "",
            (cfg or {}).get("parse_api_url") or "",
            (cfg or {}).get("chat_api_url") or "",
            (cfg or {}).get("translate_api_url") or "",
            (cfg or {}).get("paper_api_url") or "",
        ]
    ).lower()
    return "opencode" in blob


def _first_model(*vals, fallback: str = "") -> str:
    for v in vals:
        s = (v or "").strip()
        if s:
            return s
    return fallback


def default_fast_text_for_url(cfg: dict) -> str:
    url = (
        cfg.get("translate_api_url")
        or cfg.get("chat_api_url")
        or cfg.get("parse_api_url")
        or ""
    ).lower()
    if "opencode" in url:
        return OPENCODE_DEFAULT
    if "generativelanguage" in url or "googleapis" in url:
        return "gemini-2.5-flash"
    if "openai.com" in url:
        return "gpt-4o-mini"
    return FAST_TEXT_DEFAULT


def is_reasoning_model(name: str) -> bool:
    """True for hybrid-reasoning models (MiMo, R1, QwQ, ...) that spend part of
    their output budget on a <think> trace unless explicitly disabled."""
    return bool(_REASONING.search(name or ""))


def extra_body_for_model(name: str) -> dict:
    """Only disable CoT on explicit thinking/reasoner models — not qwen3.7-plus."""
    if is_reasoning_model(name):
        return {"enable_thinking": False}
    return {}


def reasoning_max_tokens(base: int, name: str, cap: int = 8000) -> int:
    """Give reasoning models (MiMo, R1, QwQ, ...) extra output headroom.

    Some gateways don't honor `enable_thinking: false`, so the model may still
    spend a large chunk of `max_tokens` on its <think> trace before it ever
    reaches the JSON/answer we actually want — leaving nothing for it and
    causing empty/garbled parses (e.g. PPT figure labeling or tagging silently
    falling back). Non-reasoning models are returned unchanged.
    """
    if not is_reasoning_model(name):
        return base
    boosted = max(base * 2, base + 3000)
    return min(cap, boosted)


_THINK_CLOSED = re.compile(r"<think>[\s\S]*?</think>", re.I)
_THINK_OPEN = re.compile(r"<think>[\s\S]*", re.I)


def strip_think(text: str) -> str:
    """Remove a model's <think>...</think> trace, including an unclosed one
    left dangling when max_tokens cut generation off mid-thought."""
    if not text:
        return text or ""
    cleaned = _THINK_CLOSED.sub("", text)
    cleaned = _THINK_OPEN.sub("", cleaned)
    return cleaned.strip()


def pick_fast_text_model(cfg: dict, fallback: str | None = None) -> str:
    """Translate / annotate / tag / chat: use the configured quality model on OpenCode."""
    if is_opencode(cfg):
        return _first_model(
            cfg.get("translate_model"),
            cfg.get("chat_model"),
            cfg.get("annotator_model"),
            cfg.get("parse_model"),
            fallback=fallback or OPENCODE_DEFAULT,
        )
    fb = fallback or default_fast_text_for_url(cfg)
    for key in ("translate_model", "chat_model", "annotator_model"):
        val = (cfg.get(key) or "").strip()
        if not val:
            continue
        if is_slow_or_thinking(val) or is_vision_model(val):
            continue
        return val
    return fb


def pick_parse_model(cfg: dict, fallback: str | None = None) -> str:
    """Knowledge-base parse: honor parse_model. OpenCode plus is multimodal and high quality."""
    if is_opencode(cfg):
        return _first_model(
            cfg.get("parse_model"),
            cfg.get("paper_model"),
            cfg.get("chat_model"),
            fallback=fallback or OPENCODE_DEFAULT,
        )
    vis = (cfg.get("parse_model") or cfg.get("paper_model") or "").strip()
    if vis and not is_slow_or_thinking(vis) and not is_vision_model(vis):
        return vis
    return pick_fast_text_model(cfg, fallback or default_fast_text_for_url(cfg))


def pick_vision_model(cfg: dict, fallback: str | None = None) -> str:
    """PPT figure labeling. OpenCode qwen3.7-plus can see images even without 'vl' in the name."""
    override = (os.environ.get("PAPERFECT_PPT_MODEL") or "").strip()
    if override:
        return override
    if is_opencode(cfg):
        return _first_model(
            cfg.get("parse_model"),
            cfg.get("paper_model"),
            cfg.get("chat_model"),
            fallback=fallback or OPENCODE_DEFAULT,
        )
    fb = fallback or FAST_VISION_DEFAULT
    for key in ("parse_model", "paper_model", "chat_model"):
        val = (cfg.get(key) or "").strip()
        if not val:
            continue
        if is_slow_or_thinking(val):
            continue
        if is_vision_model(val) or "gemini" in val.lower() or "gpt-4o" in val.lower():
            if _HEAVY_VL.search(val):
                return fb
            return val
    return fb
