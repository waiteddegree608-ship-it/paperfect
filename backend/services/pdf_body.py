# coding=utf-8
"""Detect paper body vs references / appendix so pipelines can skip back-matter."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import fitz

HEADING_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)*\.?\s+)?"
    r"(references|bibliography|参考文献|参考资料|reference)\s*$",
    re.I,
)
APPENDIX_RE = re.compile(
    r"^\s*(appendix|appendices|supplementary|acknowledgment|acknowledgement|"
    r"附录|补充材料|数据集|data\s+availability)\b",
    re.I,
)
# Typical bibliography lines: [12] Author. Title...
BIB_ITEM_RE = re.compile(
    r"^\s*(?:\[(\d+)\]|(\d+)\.)\s+(.{12,400})$",
)


def _is_heading_line(line: str) -> bool:
    s = (line or "").strip()
    if not s or len(s) > 48:
        return False
    return bool(HEADING_RE.match(s))


def detect_body_range(pdf_path: str) -> Dict[str, Any]:
    """
    Return 1-based page numbers:
      body_end_page: last page treated as paper body (inclusive)
      refs_start_page: first references page, or None
      page_count
    On failure, body_end_page == page_count (process everything).
    """
    result = {
        "page_count": 0,
        "body_end_page": 0,
        "refs_start_page": None,
        "appendix_start_page": None,
        "confidence": "none",
    }
    if not pdf_path or not os.path.isfile(pdf_path):
        return result

    doc = fitz.open(pdf_path)
    try:
        n = len(doc)
        result["page_count"] = n
        result["body_end_page"] = n
        if n <= 2:
            return result

        refs_page = None
        appendix_page = None
        # Ignore "references" mentions in related-work (early pages)
        min_page = max(2, int(n * 0.45))

        for i in range(n):
            page = doc[i]
            text = page.get_text("text") or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if not lines:
                continue
            scan = lines[:18] + [ln for ln in lines[18:36] if len(ln) < 40]
            for ln in scan:
                if refs_page is None and _is_heading_line(ln) and (i + 1) >= min_page:
                    bib_hits = sum(1 for x in lines if BIB_ITEM_RE.match(x))
                    # Related-work can mention "References"; require bib lines unless late in the paper
                    if bib_hits >= 2 or (i + 1) >= int(n * 0.6):
                        refs_page = i + 1
                        break
                if (
                    appendix_page is None
                    and refs_page is not None
                    and APPENDIX_RE.match(ln)
                    and len(ln) < 60
                    and (i + 1) > refs_page
                ):
                    appendix_page = i + 1
                    break
            if refs_page and appendix_page:
                break

        if refs_page and refs_page < n:
            if refs_page <= max(3, int(n * 0.35)):
                result["confidence"] = "rejected_too_early"
            else:
                result["refs_start_page"] = refs_page
                result["body_end_page"] = max(1, refs_page - 1)
                result["appendix_start_page"] = appendix_page
                result["confidence"] = "heading"
        else:
            result["confidence"] = "full_fallback"
        return result
    except Exception as e:
        result["error"] = str(e)
        return result
    finally:
        doc.close()


def extract_reference_entries(pdf_path: str, refs_start_page: Optional[int] = None, max_items: int = 80) -> List[Dict[str, Any]]:
    """Parse bibliography lines from the references section (best-effort)."""
    info = detect_body_range(pdf_path) if refs_start_page is None else None
    start = refs_start_page or (info or {}).get("refs_start_page")
    if not start:
        return []
    doc = fitz.open(pdf_path)
    items: List[Dict[str, Any]] = []
    try:
        n = len(doc)
        for i in range(start - 1, n):
            text = doc[i].get_text("text") or ""
            for raw in text.splitlines():
                m = BIB_ITEM_RE.match(raw.strip())
                if not m:
                    continue
                num = m.group(1) or m.group(2)
                rest = (m.group(3) or "").strip()
                year_m = re.search(r"\b((?:19|20)\d{2})\b", rest)
                items.append({
                    "index": int(num) if str(num).isdigit() else len(items) + 1,
                    "raw": rest,
                    "year": year_m.group(1) if year_m else "",
                    "title_guess": _guess_title(rest),
                })
                if len(items) >= max_items:
                    return items
        return items
    except Exception:
        return items
    finally:
        doc.close()


def _guess_title(raw: str) -> str:
    # "Author. Title. Venue, year." — take the segment after first period that looks like a title
    parts = [p.strip() for p in re.split(r"\.\s+", raw) if p.strip()]
    if len(parts) >= 2:
        cand = parts[1]
        if 8 <= len(cand) <= 180:
            return cand
    return raw[:160]


def save_body_info(pdf_path: str, target_dir: str) -> Dict[str, Any]:
    info = detect_body_range(pdf_path)
    if info.get("refs_start_page"):
        info["references"] = extract_reference_entries(pdf_path, info["refs_start_page"])
    else:
        info["references"] = []
    os.makedirs(os.path.join(target_dir, "parsed"), exist_ok=True)
    out = os.path.join(target_dir, "parsed", "body_info.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    info["path"] = out
    return info


def load_body_info(target_dir: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(target_dir, "parsed", "body_info.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def is_body_page(page_1based: int, body_end_page: Optional[int], page_count: int) -> bool:
    end = body_end_page or page_count
    return 1 <= page_1based <= end
