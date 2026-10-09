# coding: utf-8
"""Paper workspace layout — same on-disk contract as the Paperfect desktop app."""
from __future__ import annotations

import json
import os
import shutil
from typing import Any, Optional

_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _AGENT_DIR not in __import__("sys").path:
    __import__("sys").path.insert(0, _AGENT_DIR)

from runtime import paperfect_root, work_root, ok, err


SUBDIRS = ("raw", "parsed", "translated", "marked", "images", "pptx", "cache", "exports")


def file_ok(path: str, min_bytes: int = 64) -> bool:
    try:
        return bool(path) and os.path.isfile(path) and os.path.getsize(path) >= min_bytes
    except OSError:
        return False


def _load_json(path: str) -> Any:
    if not file_ok(path, 2):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def ensure_dirs(paper_dir: str) -> None:
    for sub in SUBDIRS:
        os.makedirs(os.path.join(paper_dir, sub), exist_ok=True)


def paths_for(book_name: str, root: Optional[str] = None) -> dict:
    root = root or work_root()
    paper_dir = os.path.join(root, book_name)
    return {
        "book_name": book_name,
        "work_root": root,
        "paper_dir": paper_dir,
        "raw_dir": os.path.join(paper_dir, "raw"),
        "pdf_path": os.path.join(paper_dir, "raw", f"{book_name}.pdf"),
        "kb_path": os.path.join(paper_dir, "parsed", f"{book_name}_KnowledgeBase.md"),
        "translated_pdf": os.path.join(paper_dir, "translated", f"{book_name}_translated.pdf"),
        "annotated_pdf": os.path.join(paper_dir, "marked", f"{book_name}_annotated.pdf"),
        "annotations_json": os.path.join(paper_dir, "marked", "annotations.json"),
        "images_dir": os.path.join(paper_dir, "images"),
        "pptx_path": os.path.join(paper_dir, "pptx", f"{book_name}_Full_Presentation.pptx"),
        "pptx_dir": os.path.join(paper_dir, "pptx"),
        "sync_map": os.path.join(paper_dir, "pptx", "slide_sync_map.json"),
        "ppt_status": os.path.join(paper_dir, "pptx", "ppt_status.json"),
        "pipeline_json": os.path.join(paper_dir, "pipeline.json"),
        "metadata_json": os.path.join(paper_dir, "metadata.json"),
        "upload_meta": os.path.join(paper_dir, "upload_meta.json"),
        "body_info": os.path.join(paper_dir, "parsed", "body_info.json"),
        "cache_dir": os.path.join(paper_dir, "cache"),
        "exports_dir": os.path.join(paper_dir, "exports"),
        "reading_html": os.path.join(paper_dir, "research", "reading", "index.html"),
        "reading_manifest": os.path.join(paper_dir, "research", "reading", "manifest.json"),
        "notes_json": os.path.join(paper_dir, "research", "notes", "notes.json"),
        "notes_md": os.path.join(paper_dir, "research", "notes", "notes.md"),
    }


def resolve_paper(book_name: str) -> dict:
    name = (book_name or "").strip().strip("/\\")
    if not name:
        raise ValueError("book_name is required")
    p = paths_for(name)
    if not os.path.isdir(p["paper_dir"]):
        # Also look in the desktop-app library if WORK_DIR is custom
        lib = os.path.join(paperfect_root(), "data", "papers", name)
        if os.path.isdir(lib):
            p = paths_for(name, os.path.join(paperfect_root(), "data", "papers"))
    if not os.path.isdir(p["paper_dir"]):
        raise FileNotFoundError(
            f"Paper workspace not found: {name}. Call ingest_pdf first. work_root={p['work_root']}"
        )
    return p


def artifact_status(p: dict) -> dict:
    ppt_complete = False
    st = _load_json(p["ppt_status"])
    if isinstance(st, dict):
        ppt_complete = bool(st.get("complete"))
    has_pptx = file_ok(p["pptx_path"], 8000)
    figures = []
    img_dir = p["images_dir"]
    if os.path.isdir(img_dir):
        figures = sorted(
            f for f in os.listdir(img_dir) if f.lower().endswith((".png", ".jpg", ".jpeg"))
        )
    return {
        "has_raw": file_ok(p["pdf_path"], 64),
        "has_kb": file_ok(p["kb_path"], 200),
        "has_translated": file_ok(p["translated_pdf"], 1024),
        "has_annotated": file_ok(p["annotated_pdf"], 1024),
        "has_annotations_json": file_ok(p["annotations_json"], 8),
        "has_pptx": has_pptx,
        "ppt_complete": ppt_complete if has_pptx else False,
        "figure_count": len(figures),
        "figures": figures[:40],
        "has_metadata": file_ok(p["metadata_json"], 8),
        "has_body_info": file_ok(p["body_info"], 8),
    }


def ingest_pdf(pdf_path: str, book_name: Optional[str] = None) -> dict:
    from backend.services.file_manager import sanitize_book_name

    src = os.path.abspath(pdf_path)
    if not os.path.isfile(src):
        return err(f"PDF not found: {src}")
    if not src.lower().endswith(".pdf"):
        return err("Only .pdf files are accepted")

    display = os.path.splitext(os.path.basename(src))[0]
    name = sanitize_book_name(book_name or display)
    root = work_root()
    existing = os.path.join(root, name)
    if os.path.isdir(existing) and file_ok(os.path.join(existing, "raw", f"{name}.pdf")):
        p = paths_for(name)
        return ok(
            skipped=True,
            reason="workspace already exists",
            **p,
            artifacts=artifact_status(p),
        )
    candidate = name
    n = 2
    while os.path.isdir(os.path.join(root, candidate)):
        candidate = f"{name[:60]}_{n}"
        n += 1
        if n > 99:
            break
    name = candidate

    p = paths_for(name)
    ensure_dirs(p["paper_dir"])
    shutil.copy2(src, p["pdf_path"])
    meta = {
        "display_title": display,
        "original_filename": os.path.basename(src),
        "book_name": name,
        "source_pdf": src,
    }
    with open(p["upload_meta"], "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return ok(skipped=False, display_title=display, **p, artifacts=artifact_status(p))


def list_papers() -> dict:
    root = work_root()
    items = []
    if not os.path.isdir(root):
        return ok(work_root=root, papers=[])
    for name in sorted(os.listdir(root)):
        paper_dir = os.path.join(root, name)
        if not os.path.isdir(paper_dir):
            continue
        p = paths_for(name)
        if not file_ok(p["pdf_path"]) and not os.path.isdir(p["raw_dir"]):
            continue
        meta = _load_json(p["upload_meta"]) or {}
        md = _load_json(p["metadata_json"]) or {}
        items.append(
            {
                "book_name": name,
                "display_title": meta.get("display_title") or md.get("en_title") or name,
                "zh_title": md.get("zh_title") or "",
                "venue": md.get("venue") or "",
                "year": md.get("year") or "",
                "paper_dir": p["paper_dir"],
                "artifacts": artifact_status(p),
            }
        )
    return ok(work_root=root, count=len(items), papers=items)


def get_artifacts(book_name: str) -> dict:
    try:
        p = resolve_paper(book_name)
    except Exception as e:
        return err(str(e))
    flags = _load_json(p["pipeline_json"]) or {}
    meta = _load_json(p["metadata_json"]) or {}
    body = _load_json(p["body_info"]) or {}
    st = artifact_status(p)
    return ok(
        book_name=p["book_name"],
        paper_dir=p["paper_dir"],
        paths={k: p[k] for k in (
            "pdf_path", "kb_path", "translated_pdf", "annotated_pdf",
            "annotations_json", "images_dir", "pptx_path", "sync_map",
            "metadata_json", "pipeline_json", "body_info",
        )},
        artifacts=st,
        pipeline_flags=flags,
        metadata={k: meta.get(k) for k in (
            "en_title", "zh_title", "venue", "year", "ccf_partition",
            "jcr_partition", "paper_type", "doi", "authors",
        ) if meta},
        body_info=body,
    )


def read_text_file(path: str, offset: int = 0, max_chars: int = 8000) -> dict:
    if not os.path.isfile(path):
        return err(f"File not found: {path}")
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    total = len(text)
    offset = max(0, int(offset or 0))
    max_chars = max(200, min(int(max_chars or 8000), 40000))
    chunk = text[offset: offset + max_chars]
    return ok(
        path=path,
        total_chars=total,
        offset=offset,
        returned_chars=len(chunk),
        truncated=offset + len(chunk) < total,
        content=chunk,
    )
