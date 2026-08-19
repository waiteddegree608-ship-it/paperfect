# coding=utf-8
"""Library-local paper lineage: related docs, reference picks, same-author."""
from __future__ import annotations

import json
import os
import re
import difflib
from typing import Any, Dict, List

from backend.core.config import get_base_dir
from backend.models.database import Document, DocumentRelation, Tag
from backend.services.pdf_body import load_body_info, extract_reference_entries, detect_body_range
from backend.services.venue_matcher import match_venue


def _authors_of(doc: Document) -> List[str]:
    raw = doc.authors or ""
    if not raw:
        return []
    try:
        val = json.loads(raw)
        if isinstance(val, list):
            return [str(a).strip() for a in val if str(a).strip()]
    except Exception:
        pass
    return [a.strip() for a in re.split(r"[,;]", raw) if a.strip()]


def _keywords_of(doc: Document) -> List[str]:
    names = [t.name for t in (doc.tags or []) if getattr(t, "category", "") == "Keywords"]
    try:
        extra = json.loads(doc.en_keywords or "[]")
        if isinstance(extra, list):
            names.extend(str(x) for x in extra)
    except Exception:
        pass
    return [n for n in names if n]


def _field_of(doc: Document) -> str:
    v = doc.research_field or ""
    try:
        obj = json.loads(v)
        if isinstance(obj, dict):
            return str(obj.get("zh") or obj.get("en") or "")
    except Exception:
        pass
    return v


def _title_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _upsert_relation(db, src_id: int, dst_id: int, rtype: str, weight: int):
    if src_id == dst_id:
        return
    row = (
        db.query(DocumentRelation)
        .filter(
            DocumentRelation.source_doc_id == src_id,
            DocumentRelation.target_doc_id == dst_id,
            DocumentRelation.relation_type == rtype,
        )
        .first()
    )
    if row:
        row.weight = max(row.weight or 0, weight)
    else:
        db.add(DocumentRelation(source_doc_id=src_id, target_doc_id=dst_id, relation_type=rtype, weight=weight))


def build_lineage(db, doc: Document) -> Dict[str, Any]:
    others = db.query(Document).filter(Document.id != doc.id).all()
    my_authors = set(a.lower() for a in _authors_of(doc))
    my_kws = set(k.lower() for k in _keywords_of(doc))
    my_field = (_field_of(doc) or "").lower()

    related = []
    for o in others:
        reasons = []
        score = 0
        o_authors = _authors_of(o)
        shared_auth = [a for a in o_authors if a.lower() in my_authors]
        if shared_auth:
            reasons.append("same_author")
            score += 5 * len(shared_auth)
            _upsert_relation(db, doc.id, o.id, "same_author", len(shared_auth))
        shared_kw = [k for k in _keywords_of(o) if k.lower() in my_kws]
        if shared_kw:
            reasons.append("shared_keywords")
            score += len(shared_kw)
            _upsert_relation(db, doc.id, o.id, "shared_keywords", len(shared_kw))
        ofield = (_field_of(o) or "").lower()
        if my_field and ofield and (my_field in ofield or ofield in my_field):
            reasons.append("same_field")
            score += 2
        if score > 0:
            related.append({
                "id": o.id,
                "title": o.title,
                "zh_title": o.zh_title,
                "year": o.year,
                "venue": o.venue,
                "ccf_partition": o.ccf_partition,
                "authors": o_authors,
                "reasons": reasons,
                "score": score,
                "original_filename": o.original_filename,
            })
    related.sort(key=lambda x: -x["score"])
    try:
        db.commit()
    except Exception:
        db.rollback()

    book = (doc.original_filename or "").replace(".pdf", "")
    target_dir = os.path.join(get_base_dir(), "data", "papers", book)
    pdf_path = doc.file_path if doc.file_path and os.path.isfile(doc.file_path) else os.path.join(target_dir, "raw", f"{book}.pdf")
    dossier = _build_dossier(doc, target_dir, pdf_path)
    info = load_body_info(target_dir) or {}
    refs = info.get("references") or []
    if not refs and pdf_path and os.path.isfile(pdf_path):
        start = info.get("refs_start_page")
        if not start:
            det = detect_body_range(pdf_path)
            start = det.get("refs_start_page")
        if start:
            refs = extract_reference_entries(pdf_path, start)

    lib_titles = [(o, (o.title or "") + " " + (o.zh_title or "")) for o in others]
    ref_picks = []
    for r in refs[:40]:
        title_g = r.get("title_guess") or r.get("raw") or ""
        in_lib = None
        best = 0.0
        for o, blob in lib_titles:
            sc = _title_score(title_g, o.title or "")
            if sc > best:
                best = sc
                in_lib = o if sc >= 0.72 else None
        ccf, _, acr = match_venue(title_g)
        worth = 0
        if in_lib:
            worth += 5
        if ccf == "A":
            worth += 3
        elif ccf == "B":
            worth += 2
        if re.search(r"\b(survey|review|综述)\b", title_g, re.I):
            worth += 2
        year = r.get("year") or ""
        if year.isdigit() and int(year) >= 2018:
            worth += 1
        ref_picks.append({
            "raw": r.get("raw"),
            "title": title_g,
            "year": year,
            "ccf": ccf,
            "matched_venue": acr,
            "in_library": bool(in_lib),
            "library_doc_id": in_lib.id if in_lib else None,
            "library_title": in_lib.title if in_lib else None,
            "worth_score": worth,
        })
    ref_picks.sort(key=lambda x: -x["worth_score"])

    return {
        "document": {
            "id": doc.id,
            "title": doc.title,
            "zh_title": doc.zh_title,
            "authors": _authors_of(doc),
            "year": doc.year,
            "venue": doc.venue,
            "ccf_partition": doc.ccf_partition,
            "jcr_partition": doc.jcr_partition,
            "doi": doc.doi,
            "abstract": doc.abstract,
            "en_abstract": doc.en_abstract,
            "original_filename": doc.original_filename,
        },
        "related": related[:20],
        "references": ref_picks[:25],
        "dossier": dossier,
    }


_ARCH_RE = re.compile(
    r"architect|framework|overview|pipeline|schematic|backbone|"
    r"structure|network|model of|block diagram|材料结构|架构|框架|总览|模型图|结构图|流程图",
    re.I,
)
_FIG_CAP_RE = re.compile(
    r"(?:Figure|Fig\.?)\s*(\d+)\s*[:.\-–—]?\s*(.+)",
    re.I,
)


def _extract_figure_captions(pdf_path: str, max_pages: int = 14) -> Dict[str, str]:
    caps = {}
    if not pdf_path or not os.path.isfile(pdf_path):
        return caps
    try:
        import fitz
        doc = fitz.open(pdf_path)
        try:
            for i, page in enumerate(doc):
                if i >= max_pages:
                    break
                text = page.get_text("text") or ""
                for m in _FIG_CAP_RE.finditer(text):
                    num, cap = m.group(1), (m.group(2) or "").strip().split("\n")[0][:220]
                    if num not in caps and cap:
                        caps[num] = cap
        finally:
            doc.close()
    except Exception:
        pass
    return caps


def _list_figure_files(img_dir: str) -> List[str]:
    if not os.path.isdir(img_dir):
        return []
    files = []
    for name in os.listdir(img_dir):
        if re.match(r"(?i)figure_\d+\.(png|jpg|jpeg|webp)$", name):
            files.append(name)
    def _num(n):
        m = re.search(r"(\d+)", n)
        return int(m.group(1)) if m else 999
    files.sort(key=_num)
    return files


def _parse_kb_qa(kb_path: str) -> List[Dict[str, str]]:
    if not os.path.isfile(kb_path):
        return []
    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return []
    parts = re.split(r"(?m)^##\s+", raw)
    qa = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        title, _, body = p.partition("\n")
        title = title.strip()
        body = body.strip()
        if not body or title.startswith("提示词汇总"):
            continue
        qa.append({"title": title, "answer": body})
    if qa:
        return qa
    # Single undifferentiated report
    text = raw.strip()
    if len(text) > 80:
        return [{"title": "学术解析", "answer": text}]
    return []


def _attach_prompt_questions(qa: List[Dict[str, str]], prompt_type: str = "提示词汇总") -> List[Dict[str, str]]:
    sections = []
    try:
        from backend.services.prompts import split_prompt_sections, _load_stage1_prompt_file
        for name in (prompt_type, "提示词汇总", "计算机+人工智能"):
            if not name:
                continue
            try:
                raw = _load_stage1_prompt_file(name, "zh")
                sections = split_prompt_sections(raw)
            except Exception:
                sections = []
            if sections:
                break
    except Exception:
        sections = []
    by_title = {s.get("title"): s.get("body") for s in sections}
    out = []
    for item in qa:
        q = by_title.get(item.get("title") or "") or ""
        out.append({
            "title": item.get("title") or "",
            "question": q,
            "answer": item.get("answer") or "",
        })
    return out


def _build_dossier(doc: Document, target_dir: str, pdf_path: str) -> Dict[str, Any]:
    img_dir = os.path.join(target_dir, "images")
    files = _list_figure_files(img_dir)
    caps = _extract_figure_captions(pdf_path)
    book = (doc.original_filename or "").replace(".pdf", "")

    def _fig(name: str, role: str):
        num = ""
        m = re.search(r"(\d+)", name)
        if m:
            num = m.group(1)
        return {
            "filename": name,
            "url": f"/api/library/documents/{doc.id}/figures/{name}",
            "caption": caps.get(num) or "",
            "role": role,
        }

    hero = _fig(files[0], "hero") if files else None
    arch = None
    for name in files:
        num = ""
        m = re.search(r"(\d+)", name)
        if m:
            num = m.group(1)
        blob = f"{name} {caps.get(num) or ''}"
        if _ARCH_RE.search(blob):
            arch = _fig(name, "architecture")
            break
    if arch and hero and arch["filename"] == hero["filename"] and len(files) > 1:
        # keep architecture as the matched one; hero stays Figure 1
        pass
    if not arch:
        # second figure is often the model if captions didn't match
        if len(files) >= 2:
            arch = _fig(files[1], "architecture")

    pipeline = {}
    try:
        with open(os.path.join(target_dir, "pipeline.json"), "r", encoding="utf-8") as f:
            pipeline = json.load(f) or {}
    except Exception:
        pipeline = {}

    kb_path = os.path.join(target_dir, "parsed", f"{book}_KnowledgeBase.md")
    qa = _attach_prompt_questions(
        _parse_kb_qa(kb_path),
        pipeline.get("prompt_type") or "提示词汇总",
    )
    ai_abstract = (doc.abstract or "").strip() or (doc.en_abstract or "").strip()
    if not ai_abstract and qa:
        ai_abstract = (qa[0].get("answer") or "")[:1200]

    return {
        "hero_figure": hero,
        "arch_figure": arch,
        "ai_abstract": ai_abstract,
        "qa": qa,
        "prompt_type": pipeline.get("prompt_type") or "",
    }


def _fetch_author_papers(author_name: str, doi: str) -> List[Dict[str, Any]]:
    return []

