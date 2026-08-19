# coding=utf-8
"""CCF venue matching. JCR is proprietary — only applied from an optional local map."""
from __future__ import annotations

import json
import os
import re
import difflib
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

from backend.core.config import get_base_dir

_NOISE = re.compile(
    r"\b(proceedings|proc\.?|of the|ieee|acm|usenix|the|international|conference|"
    r"workshop|symposium|journal|transactions|trans\.|vol\.?|volume|pp\.?|"
    r"pages?|doi|isbn)\b",
    re.I,
)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_PUNCT = re.compile(r"[^\w\s\u4e00-\u9fff]+", re.U)


def normalize_venue(name: str) -> str:
    s = (name or "").strip()
    s = _YEAR.sub(" ", s)
    s = _NOISE.sub(" ", s)
    s = _PUNCT.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


@lru_cache(maxsize=1)
def load_ccf_catalog() -> Dict[str, Any]:
    path = os.path.join(get_base_dir(), "backend", "resources", "ccf_venues.json")
    if not os.path.isfile(path):
        return {"by_acronym": {}, "by_norm": {}}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    by_acronym = {}
    by_norm = {}
    for key, meta in raw.items():
        if not isinstance(meta, dict):
            continue
        entry = {
            "ccf": (meta.get("ccf") or "").upper(),
            "full": meta.get("full") or key,
            "type": meta.get("type") or "",
            "acronym": key,
        }
        by_acronym[key.upper()] = entry
        by_norm[normalize_venue(key)] = entry
        by_norm[normalize_venue(entry["full"])] = entry
        for alias in meta.get("aliases") or []:
            by_norm[normalize_venue(alias)] = entry
            if len(alias) <= 12 and alias.isupper():
                by_acronym[alias.upper()] = entry
    return {"by_acronym": by_acronym, "by_norm": by_norm}


@lru_cache(maxsize=1)
def load_jcr_map() -> Dict[str, str]:
    """Optional local JCR mapping {normalized_or_acronym: 一区/二区/...}."""
    for rel in (
        os.path.join("backend", "resources", "jcr_venues.json"),
        os.path.join("data", "jcr_venues.json"),
        os.path.join("data", "venue_dict.json"),
    ):
        path = os.path.join(get_base_dir(), rel)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        out = {}
        if isinstance(data, dict):
            for k, v in data.items():
                jcr = ""
                if isinstance(v, dict):
                    jcr = str(v.get("jcr") or v.get("jcr_partition") or "").strip()
                elif isinstance(v, str):
                    jcr = v.strip()
                if jcr and jcr not in ("无", "未知", "Unknown", "-"):
                    out[k.upper()] = jcr
                    nk = normalize_venue(k)
                    if nk:
                        out[nk] = jcr
        if out:
            return out
    return {}


def match_venue(venue: str) -> Tuple[str, str, str]:
    """Return (ccf, jcr, matched_acronym). Empty strings if unknown."""
    venue = (venue or "").strip()
    if not venue or venue.lower() in ("unknown", "arxiv", "preprint"):
        return "", "", ""

    cat = load_ccf_catalog()
    words = re.findall(r"\b[A-Za-z]{2,}\b", venue)
    # 1) acronym exact (CVPR, NeurIPS, ICML...)
    for w in words:
        hit = cat["by_acronym"].get(w.upper())
        if hit and len(w) >= 2:
            jcr = _lookup_jcr(w.upper(), venue)
            return hit["ccf"], jcr, hit["acronym"]

    norm = normalize_venue(venue)
    if not norm:
        return "", "", ""
    hit = cat["by_norm"].get(norm)
    if hit:
        return hit["ccf"], _lookup_jcr(hit["acronym"], venue), hit["acronym"]

    # 2) high-threshold fuzzy, require shared token
    best = None
    best_score = 0.0
    tokens = set(norm.split())
    for k, entry in cat["by_norm"].items():
        if not k:
            continue
        score = difflib.SequenceMatcher(None, norm, k).ratio()
        if k in norm or norm in k:
            score = max(score, min(len(k), len(norm)) / max(len(k), len(norm), 1))
        k_tokens = set(k.split())
        if score > best_score and (tokens & k_tokens):
            best_score = score
            best = entry
    if best and best_score >= 0.82:
        return best["ccf"], _lookup_jcr(best["acronym"], venue), best["acronym"]
    return "", _lookup_jcr("", venue), ""


def scan_ccf_in_text(text: str) -> Tuple[str, str, str]:
    """Pick the strongest CCF venue mentioned in free text (comments, headers, titles)."""
    blob = text or ""
    if not blob.strip():
        return "", "", ""
    cat = load_ccf_catalog()
    hits = []
    for acr, hit in cat["by_acronym"].items():
        if len(acr) < 3 and acr.upper() not in {"CHI", "WWW", "KDD", "SP"}:
            continue
        if re.search(r"(?<![A-Za-z])" + re.escape(acr) + r"(?![A-Za-z])", blob, re.I):
            rank = {"A": 3, "B": 2, "C": 1}.get((hit.get("ccf") or "").upper(), 0)
            hits.append((rank, len(acr), hit))
    if not hits:
        return match_venue(blob)
    hits.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best = hits[0][2]
    return best["ccf"], _lookup_jcr(best["acronym"], best.get("full") or ""), best["acronym"]


def _lookup_jcr(acronym: str, venue: str) -> str:
    jmap = load_jcr_map()
    if not jmap:
        return ""
    if acronym and acronym.upper() in jmap:
        return jmap[acronym.upper()]
    nk = normalize_venue(venue)
    return jmap.get(nk, "")
