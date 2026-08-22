from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import os
import shutil
import json
import re

from backend.models.database import SessionLocal, Folder, Document, Tag, DocumentRelation
from backend.services.paper_analyzer import analyze_paper
from backend.core.config import get_base_dir
from backend.services.file_manager import active_tasks_progress
from backend.services.task_runner import active_tasks, async_run_builder

router = APIRouter(prefix="/api/library", tags=["library"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/folders")
def get_folders(db: Session = Depends(get_db)):
    folders = db.query(Folder).all()
    return [{"id": f.id, "name": f.name, "parent_id": f.parent_id, "is_system": f.is_system, "doc_count": db.query(Document).filter(Document.folder_id == f.id).count()} for f in folders]

@router.post("/folders")
def create_folder(name: str = Form(...), parent_id: Optional[int] = Form(None), db: Session = Depends(get_db)):
    folder = Folder(name=name, parent_id=parent_id)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id}

class FolderRenameRequest(BaseModel):
    name: str

class MoveDocumentRequest(BaseModel):
    folder_id: Optional[int] = None

@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: int, db: Session = Depends(get_db)):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    db.query(Document).filter(Document.folder_id == folder_id).update({"folder_id": None})
    db.delete(folder)
    db.commit()
    return {"status": "success"}

@router.put("/folders/{folder_id}")
def rename_folder(folder_id: int, req: FolderRenameRequest, db: Session = Depends(get_db)):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    folder.name = req.name
    db.commit()
    db.refresh(folder)
    return {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id}

@router.put("/documents/{doc_id}/move")
def move_document(doc_id: int, req: MoveDocumentRequest, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if req.folder_id is not None:
        folder = db.query(Folder).filter(Folder.id == req.folder_id).first()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
    doc.folder_id = req.folder_id
    db.commit()
    db.refresh(doc)
    return {"status": "success", "id": doc.id, "folder_id": doc.folder_id}


def _cache_entry_is_fallback(entry) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("fallback"):
        return True
    exp = str(entry.get("overall_explanation") or "")
    if "自动标注失败" in exp or "auto labels failed" in exp.lower():
        return True
    anns = entry.get("annotations") or []
    if len(anns) == 1 and isinstance(anns[0], dict):
        lab = str(anns[0].get("label") or "") + str(anns[0].get("description") or "")
        if "兜底" in lab or "fallback" in lab.lower():
            return True
    return False


def _ppt_labels_complete(target_dir, has_pptx: bool) -> bool:
    """True only when the deck exists and figure labels are not fallback stubs."""
    if not has_pptx or not target_dir:
        return False
    st = os.path.join(target_dir, "pptx", "ppt_status.json")
    try:
        if os.path.isfile(st):
            with open(st, "r", encoding="utf-8") as f:
                return bool((json.load(f) or {}).get("complete"))
    except Exception:
        pass
    for name in ("ppt_cache_zh.json", "ppt_cache_en.json"):
        fp = os.path.join(target_dir, "pptx", name)
        if not os.path.isfile(fp):
            continue
        try:
            with open(fp, "r", encoding="utf-8") as f:
                cache = json.load(f) or {}
        except Exception:
            continue
        if any(_cache_entry_is_fallback(v) for v in cache.values()):
            return False
    return True


def _doc_pipeline_status(book_name: str):
    """
    Derive UI status from disk artifacts + in-memory active_tasks.

    Critical UX rule: if annotate/translate/KB already exist, the paper is
    openable even while PPT is still generating. Previously anything in
    active_tasks was hard-locked as processing → users thought parsing "vanished".
    """
    from backend.core.config import get_base_dir

    base = get_base_dir()
    paper_dir = os.path.join(base, "data", "papers", book_name)
    book_dir = os.path.join(base, "data", "textbooks", book_name)
    target_dir = paper_dir if os.path.isdir(paper_dir) else book_dir if os.path.isdir(book_dir) else None
    is_paper = os.path.isdir(paper_dir)

    paper_task_id = f"papers_{book_name}"
    book_task_id = f"books_{book_name}"
    task_id = paper_task_id if is_paper or paper_task_id in active_tasks else book_task_id
    in_flight = (paper_task_id in active_tasks) or (book_task_id in active_tasks)

    pptx_path = os.path.join(target_dir or "", "pptx", f"{book_name}_Full_Presentation.pptx") if target_dir else ""
    annotated = os.path.join(target_dir or "", "marked", f"{book_name}_annotated.pdf") if target_dir else ""
    translated = os.path.join(target_dir or "", "translated", f"{book_name}_translated.pdf") if target_dir else ""
    kb = os.path.join(target_dir or "", "parsed", f"{book_name}_KnowledgeBase.md") if target_dir else ""
    raw_pdf = os.path.join(target_dir or "", "raw", f"{book_name}.pdf") if target_dir else ""

    def _ok(p, min_b=64):
        try:
            return bool(p) and os.path.isfile(p) and os.path.getsize(p) >= min_b
        except OSError:
            return False

    has_pptx = _ok(pptx_path, 8000)  # empty failed PPTX must not count as ready
    has_annotated = _ok(annotated, 1024)
    has_translated = _ok(translated, 1024)
    has_kb = _ok(kb, 200)
    has_raw = _ok(raw_pdf, 64)
    ppt_complete = _ppt_labels_complete(target_dir, has_pptx)
    # Viewable as soon as raw PDF exists (chat page); richer tabs need annotated/etc.
    can_open = has_raw or has_annotated or has_kb

    flags = {}
    try:
        fp = os.path.join(target_dir or "", "pipeline.json")
        if target_dir and os.path.isfile(fp):
            with open(fp, "r", encoding="utf-8") as f:
                flags = json.load(f) or {}
    except Exception:
        flags = {}
    need_ppt = flags.get("do_ppt", True)
    need_ann = flags.get("do_annotate", True)
    need_tr = flags.get("do_translate", True)
    need_parse = flags.get("do_parse", True)
    if not any([need_ppt, need_ann, need_tr, need_parse]):
        requested_done = has_raw
    else:
        requested_done = True
        if need_ppt and not ppt_complete:
            requested_done = False
        if need_ann and not has_annotated:
            requested_done = False
        if need_tr and not has_translated:
            requested_done = False
        if need_parse and not has_kb:
            requested_done = False

    if requested_done and not in_flight:
        return {
            "status": "ready",
            "progress": "",
            "percent": 100,
            "can_open": True,
            "has_annotated": has_annotated,
            "has_translated": has_translated,
            "has_kb": has_kb,
            "has_pptx": has_pptx,
        }

    if in_flight:
        progress_info = active_tasks_progress.get(
            paper_task_id if paper_task_id in active_tasks else book_task_id,
            {"percent": 5, "stage": "准备中..."},
        )
        # If core parse outputs already exist, treat as openable "processing"
        return {
            "status": "processing",
            "progress": progress_info.get("stage", "准备中..."),
            "percent": progress_info.get("percent", 5),
            "can_open": can_open,
            "has_annotated": has_annotated,
            "has_translated": has_translated,
            "has_kb": has_kb,
            "has_pptx": has_pptx,
        }

    # Not in active_tasks: decide ready vs interrupted from disk
    if is_paper:
        if requested_done:
            status, percent, progress = "ready", 100, ""
        elif has_pptx and not ppt_complete:
            status, percent, progress = "interrupted", 80, "PPT 部分完成，可继续"
        elif has_raw:
            missing = []
            if need_ann and not has_annotated:
                missing.append("批注")
            if need_tr and not has_translated:
                missing.append("翻译")
            if need_ppt and not ppt_complete:
                missing.append("PPT")
            status = "interrupted"
            percent = 55 if has_kb else 30
            progress = ("未完成：" + "、".join(missing)) if missing else "解析未完成"
        else:
            status, percent, progress = "interrupted", 0, "文件缺失"
    else:
        if has_kb:
            status, percent, progress = "ready", 100, ""
        elif has_raw:
            status, percent, progress = "interrupted", 40, "抽取未完成"
        else:
            status, percent, progress = "interrupted", 0, "文件缺失"

    return {
        "status": status,
        "progress": progress,
        "percent": percent,
        "can_open": can_open,
        "has_annotated": has_annotated,
        "has_translated": has_translated,
        "has_kb": has_kb,
        "has_pptx": has_pptx,
    }


@router.get("/documents")
def get_documents(folder_id: Optional[int] = None, tag: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Document)
    if folder_id:
        query = query.filter(Document.folder_id == folder_id)
    if tag:
        query = query.join(Document.tags).filter(Tag.name == tag)
        
    docs = query.all()
    result = []
    for d in docs:
        book_name = d.original_filename.replace(".pdf", "") if d.original_filename else ""
        pipe = _doc_pipeline_status(book_name) if book_name else {
            "status": "ready", "progress": "", "percent": 100, "can_open": True,
            "has_annotated": False, "has_translated": False, "has_kb": False, "has_pptx": False,
        }

        result.append({
            "id": d.id,
            "title": d.title,
            "zh_title": d.zh_title,
            "original_filename": d.original_filename,
            "upload_time": d.upload_time,
            "venue": d.venue,
            "paper_type": d.paper_type,
            "jcr_partition": d.jcr_partition,
            "ccf_partition": d.ccf_partition,
            "core_type": d.core_type,
            "research_field": d.research_field,
            "research_direction": d.research_direction,
            "authors": d.authors,
            "year": d.year,
            "doi": d.doi,
            "abstract": d.abstract,
            "en_abstract": d.en_abstract,
            "en_keywords": d.en_keywords,
            "folder_id": d.folder_id,
            "tags": [{"id": t.id, "name": t.name, "category": t.category} for t in d.tags],
            "status": pipe["status"],
            "progress": pipe["progress"],
            "percent": pipe["percent"],
            "can_open": pipe.get("can_open", True),
            "has_annotated": pipe.get("has_annotated", False),
            "has_translated": pipe.get("has_translated", False),
            "has_kb": pipe.get("has_kb", False),
            "has_pptx": pipe.get("has_pptx", False),
        })
    return result

from backend.services.file_manager import handle_upload_file as old_handle_upload_file

@router.post("/documents/{doc_id}/retag")
def retag_document(doc_id: int, db: Session = Depends(get_db)):
    """Re-run metadata/abstract/tag analysis for a library document (no full pipeline)."""
    from backend.services.paper_analyzer import analyze_paper, apply_analysis_to_document

    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    path = doc.file_path
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="PDF file missing on disk")
    analysis = analyze_paper(path)
    apply_analysis_to_document(db, doc, analysis)
    db.refresh(doc)
    return {
        "status": "success",
        "id": doc.id,
        "title": doc.title,
        "zh_title": doc.zh_title,
        "paper_type": doc.paper_type,
        "abstract": doc.abstract,
        "en_abstract": doc.en_abstract,
        "venue": doc.venue,
        "tags": [{"id": t.id, "name": t.name, "category": t.category} for t in doc.tags],
    }

def _form_bool(val, default=True):
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("1", "true", "yes", "on")


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    folder_id: int = Form(None),
    folder_name: str = Form(None),
    item_type: str = Form("paper"),
    prompt_type: str = Form("提示词汇总"),
    ppt_mode: str = Form("creative"),
    ppt_lang: str = Form("zh"),
    do_translate: str = Form("true"),
    do_annotate: str = Form("true"),
    do_ppt: str = Form("true"),
    db: Session = Depends(get_db)
):
    # Determine folder
    if folder_id:
        folder = db.query(Folder).filter(Folder.id == folder_id).first()
    elif folder_name:
        folder = db.query(Folder).filter(Folder.name == folder_name).first()
        if not folder:
            folder = Folder(name=folder_name)
            db.add(folder)
            db.commit()
            db.refresh(folder)
    else:
        folder = db.query(Folder).filter(Folder.name == "默认文件夹").first()

    # Use the old handle_upload_file to save to data/papers or data/textbooks
    # (safe short book_name for paths; display_title keeps the human-readable name)
    try:
        upload_result = await old_handle_upload_file(file, item_type)
    except RuntimeError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    if isinstance(upload_result, (list, tuple)) and len(upload_result) >= 3:
        book_name, pdf_path, display_title = upload_result[0], upload_result[1], upload_result[2]
    else:
        book_name, pdf_path = upload_result[0], upload_result[1]
        display_title = book_name

    # Save to DB — title shows full original name; paths use safe book_name
    doc = Document(
        title=display_title or book_name,
        original_filename=f"{book_name}.pdf",
        file_path=pdf_path,
        folder_id=folder.id if folder else None
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    # Trigger background task for parsing/PPT (The old pipeline)
    task_id = f"{item_type}s_{book_name}"
    if task_id not in active_tasks:
        active_tasks.add(task_id)
        if item_type == "paper":
            background_tasks.add_task(
                async_run_builder,
                pdf_path,
                book_name,
                "paper",
                prompt_type,
                ppt_mode,
                ppt_lang,
                _form_bool(do_translate, True),
                _form_bool(do_annotate, True),
                _form_bool(do_ppt, True),
            )
        else:
            background_tasks.add_task(async_run_builder, pdf_path, book_name, "book")
            
    # Also trigger the auto-tagging for the new DB in the background
    from backend.services.paper_analyzer import analyze_paper
    from backend.models.database import SessionLocal as SLocal
    
    def auto_tag(doc_id, path):
        db_local = SLocal()
        try:
            from backend.services.paper_analyzer import apply_analysis_to_document
            analysis = analyze_paper(path)
            doc_to_update = db_local.query(Document).filter(Document.id == doc_id).first()
            if doc_to_update:
                apply_analysis_to_document(db_local, doc_to_update, analysis)
                print(f"[Auto tag] saved metadata for doc {doc_id}", flush=True)
        except Exception as e:
            import traceback
            print("Auto tag error:", e, flush=True)
            traceback.print_exc()
            db_local.rollback()
        finally:
            db_local.close()
            
    background_tasks.add_task(auto_tag, doc.id, pdf_path)
    
    return {"status": "success", "id": doc.id, "book_name": book_name}

@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # Delete from DB
    db.delete(doc)
    db.commit()
    
    # Try to delete physical folder using old logic
    from backend.services.file_manager import delete_target_item
    name_without_ext = doc.original_filename.replace('.pdf', '')
    delete_target_item(name_without_ext, "paper")
    delete_target_item(name_without_ext, "book")
    
    return {"status": "success"}

@router.get("/graph")
def get_knowledge_graph(db: Session = Depends(get_db)):
    """Paper-to-paper graph from stored relations (legacy URL kept)."""
    nodes = []
    links = []
    docs = db.query(Document).all()
    for d in docs:
        nodes.append({"id": f"doc_{d.id}", "name": d.title, "category": 0, "docId": d.id})
    seen = set()
    rels = db.query(DocumentRelation).all()
    for r in rels:
        key = (min(r.source_doc_id, r.target_doc_id), max(r.source_doc_id, r.target_doc_id), r.relation_type)
        if key in seen:
            continue
        seen.add(key)
        links.append({
            "source": f"doc_{r.source_doc_id}",
            "target": f"doc_{r.target_doc_id}",
            "value": r.weight,
            "type": r.relation_type,
        })
    return {"nodes": nodes, "links": links, "categories": [{"name": "Document"}]}


@router.get("/documents/{doc_id}/figures/{filename}")
def get_document_figure(doc_id: int, filename: str, db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="bad filename")
    # Figure filenames may be prefixed with the (space-containing) paper title,
    # e.g. "My Paper Title_Figure_1.png" — only block path separators/traversal
    # above, and just check the extension here.
    if not re.match(r"(?i)^.+\.(png|jpg|jpeg|webp)$", filename):
        raise HTTPException(status_code=400, detail="bad filename")
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    book = (doc.original_filename or "").replace(".pdf", "")
    from backend.core.config import get_base_dir
    path = os.path.join(get_base_dir(), "data", "papers", book, "images", filename)
    if not os.path.isfile(path):
        path = os.path.join(get_base_dir(), "data", "textbooks", book, "images", filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Figure not found")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/documents/{doc_id}/lineage")
def get_document_lineage(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    from backend.services.paper_lineage import build_lineage
    return build_lineage(db, doc)

from pydantic import BaseModel
from openai import OpenAI
from backend.core.config import load_config
from backend.api.chat_router import simple_rag_search
from backend.services.file_manager import get_item_by_name

import re

class UniversalSearchRequest(BaseModel):
    message: str
    chat_history: list
    lang: str = "zh"

_CJK_RUN_RE = re.compile(r'[\u4e00-\u9fff]+')
# Some gateways/models (e.g. mimo) emulate tool-calling by writing this literal
# tag soup into plain message content instead of populating message.tool_calls.
_TEXT_TOOL_CALL_RE = re.compile(r"<tool_call>\s*<function=([\w_]+)>(.*?)</function>\s*</tool_call>", re.DOTALL | re.IGNORECASE)
_TEXT_TOOL_PARAM_RE = re.compile(r"<parameter=([\w_]+)>(.*?)</parameter>", re.DOTALL)


def _query_tokens(q_low: str) -> list:
    """Tokenize a (lowercased) query for substring scoring against document
    text. Handles space-separated languages normally, and additionally emits
    sliding-window bigrams for CJK runs so un-spaced Chinese phrases (e.g.
    "负泊松比材料") still get partial credit against document text — we don't
    have a real Chinese word segmenter available."""
    tokens = [t for t in re.split(r"[\s,;，。、\-]+", q_low) if len(t) >= 2]
    for run in _CJK_RUN_RE.findall(q_low):
        if len(run) <= 2:
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    stop = {"我想", "找", "关于", "的", "论文", "文献", "please", "find", "papers",
            "about", "the", "ccf", "帮我", "一下", "找一", "一篇", "相关"}
    return [t for t in tokens if t not in stop]


def _strip_text_tool_calls(text: str) -> str:
    return _TEXT_TOOL_CALL_RE.sub("", text or "").strip()


def _parse_text_tool_calls(text: str) -> list:
    calls = []
    for m in _TEXT_TOOL_CALL_RE.finditer(text or ""):
        args = {}
        for pm in _TEXT_TOOL_PARAM_RE.finditer(m.group(2)):
            args[pm.group(1).strip()] = pm.group(2).strip()
        calls.append({"id": f"textcall_{len(calls)}", "name": m.group(1).strip(), "arguments": args})
    return calls


def extract_json(text: str):
    try:
        return json.loads(text)
    except:
        pass
    
    # Try to find JSON block
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except:
            pass
            
    # Try to find anything that looks like a JSON object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0).strip())
        except:
            pass
            
    return None

@router.post("/universal_search")
def universal_search(req: UniversalSearchRequest, db: Session = Depends(get_db)):
    docs = db.query(Document).all()
    q = (req.message or "").strip()
    q_low = q.lower()

    def hay(d):
        tags = " ".join(t.name for t in d.tags)
        return " ".join([
            d.title or "", d.zh_title or "", d.venue or "", d.abstract or "",
            d.en_abstract or "", d.research_field or "", d.research_direction or "",
            d.ccf_partition or "", d.paper_type or "", tags, d.authors or "",
        ]).lower()

    # Local structured prefilter (CCF / type / keywords) — never dump the whole library
    scored = []
    want_ccf = None
    m = re.search(r"\bccf\s*[-:]?\s*([abc])\b", q_low)
    if m:
        want_ccf = m.group(1).upper()
    want_review = bool(re.search(r"综述|survey|review", q_low))
    want_research = bool(re.search(r"研究论文|research paper", q_low)) and not want_review
    tokens = _query_tokens(q_low)
    # CJK bigrams are noisy (lots of coincidental 2-char matches), so weight
    # them lower than "real" tokens (whole words / >=3-char runs).
    strong_tokens = [t for t in tokens if len(t) >= 3 or not _CJK_RUN_RE.fullmatch(t)]
    weak_tokens = [t for t in tokens if t not in strong_tokens]

    for d in docs:
        h = hay(d)
        score = 0
        if want_ccf and (d.ccf_partition or "").upper() == want_ccf:
            score += 8
        if want_review and (d.paper_type or "") == "综述":
            score += 4
        if want_research and (d.paper_type or "") == "研究":
            score += 2
        for t in strong_tokens:
            if t in h:
                score += 3
        for t in weak_tokens:
            if t in h:
                score += 1
        if score > 0:
            scored.append((score, d))
    scored.sort(key=lambda x: -x[0])
    # Small libraries: just hand the whole catalog to the LLM instead of
    # trusting a fragile keyword prefilter (which fails badly on natural-
    # language / un-spaced Chinese queries and can silently drop the only
    # relevant paper). Larger libraries fall back to the scored top-N.
    if len(docs) <= 60:
        candidates = docs
    elif scored:
        candidates = [d for _, d in scored[:30]]
    else:
        candidates = docs[:30]

    catalog_lines = []
    doc_lookup = {d.id: d for d in docs}
    for d in candidates:
        tags = [t.name for t in d.tags if t.category == "Keywords"]
        tags_str = ",".join(tags[:6]) if tags else ""
        abstract_snip = (d.abstract or d.en_abstract or "")[:180].replace("\n", " ")
        line = f"[{d.id}] {d.title}"
        if d.zh_title:
            line += f" ({d.zh_title})"
        if d.venue and d.venue != "Unknown":
            line += f" @{d.venue}"
        if d.ccf_partition:
            line += f" CCF-{d.ccf_partition}"
        if d.year:
            line += f" {d.year}"
        if d.paper_type:
            line += f" #{d.paper_type}"
        if tags_str:
            line += f" #{tags_str}"
        if abstract_snip:
            line += f" | {abstract_snip}"
        catalog_lines.append(line)
    catalog_str = "\n".join(catalog_lines) if catalog_lines else "(empty library)"

    if req.lang == "en":
        sys_prompt = f"""You are an academic literature assistant. Recommend papers from THIS CANDIDATE LIST only.
The user may specify venue rank (CCF A/B/C), paper type (survey vs research), field, fuzzy topic, or author.

[Candidates]
{catalog_str}

Call search_paper_knowledge_base only if you need methods/conclusions beyond the catalog.

Output JSON only:
{{"reply": "recommendation in English, up to 800 words", "document_ids": [1, 2]}}
document_ids must be integers from the candidate list. Empty list if nothing matches."""
    else:
        sys_prompt = f"""你是学术文献推荐助理。只能从下面的【候选文献】里推荐。
用户可能用模糊描述、研究领域、CCF 分级（A/B/C）、综述/研究、作者等条件检索。

【候选文献】
{catalog_str}

只有需要方法/结论细节时才调用 search_paper_knowledge_base。

只输出 JSON：
{{"reply": "中文推荐说明，可写到 800 字", "document_ids": [1, 2]}}
document_ids 必须是候选列表中的整数 ID。找不到就空列表。"""

    messages = [{"role": "system", "content": sys_prompt}]
    recent_history = req.chat_history[-6:] if len(req.chat_history) > 6 else req.chat_history
    for hist in recent_history:
        messages.append({"role": hist["role"], "content": hist["content"]})
    messages.append({"role": "user", "content": req.message})

    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_paper_knowledge_base",
                "description": "深入检索特定文献的详细内容（方法、结论等）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "integer", "description": "文献ID"},
                        "query": {"type": "string", "description": "检索关键词"},
                    },
                    "required": ["document_id", "query"],
                },
            },
        }
    ]

    cfg = load_config()
    client = OpenAI(api_key=cfg["chat_api_key"], base_url=cfg["chat_api_url"], timeout=300.0)
    model = cfg.get("chat_model", "Qwen/Qwen2.5-72B-Instruct")
    from backend.services.model_pick import extra_body_for_model, reasoning_max_tokens, strip_think
    chat_extra = extra_body_for_model(model)
    chat_max_tokens = reasoning_max_tokens(8192, model)
    tool_results_summary = []
    fallback_ids = [d.id for d in candidates[:8]]

    def pack_docs(doc_ids):
        final_docs = []
        if doc_ids and isinstance(doc_ids, list):
            doc_ids = [int(i) for i in doc_ids if str(i).isdigit() or isinstance(i, int)]
            if doc_ids:
                found = db.query(Document).filter(Document.id.in_(doc_ids)).all()
                order = {i: n for n, i in enumerate(doc_ids)}
                found.sort(key=lambda x: order.get(x.id, 99))
                for d in found:
                    final_docs.append({
                        "id": d.id,
                        "title": d.title,
                        "zh_title": d.zh_title,
                        "original_filename": d.original_filename,
                        "venue": d.venue,
                        "paper_type": d.paper_type,
                        "jcr_partition": d.jcr_partition,
                        "ccf_partition": d.ccf_partition,
                        "core_type": d.core_type,
                        "research_field": d.research_field,
                        "research_direction": d.research_direction,
                        "abstract": d.abstract,
                        "tags": [{"id": t.id, "name": t.name, "category": t.category} for t in d.tags],
                    })
        return final_docs

    for iteration in range(3):
        try:
            current_tools = tools if iteration < 2 else None
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=current_tools,
                max_tokens=chat_max_tokens,
                temperature=0.4,
                # Only try the CoT-disable hint on the first round; some gateways
                # reject unknown extra_body fields for certain models.
                **({"extra_body": chat_extra} if (chat_extra and iteration == 0) else {}),
            )
            message = response.choices[0].message
            raw_content = strip_think(message.content or "")
            native_calls = message.tool_calls or []
            # Fallback: some gateways/models (e.g. mimo) never populate
            # message.tool_calls and instead emit <tool_call> tag soup as
            # plain content. Detect and handle that the same way so it never
            # leaks straight into the user-facing reply. Only honor this on
            # rounds where tools were actually offered — on the final,
            # forced-answer round (current_tools is None) a hallucinated tag
            # must be ignored/stripped rather than looped on again, or a
            # stubborn model can burn through every remaining iteration.
            text_calls = [] if (native_calls or current_tools is None) else _parse_text_tool_calls(raw_content)

            if native_calls or text_calls:
                assistant_msg = {"role": "assistant", "content": _strip_text_tool_calls(raw_content)}
                if native_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": t.id,
                            "type": "function",
                            "function": {"name": t.function.name, "arguments": t.function.arguments},
                        }
                        for t in native_calls
                    ]
                messages.append(assistant_msg)

                run_calls = (
                    [{"id": t.id, "name": t.function.name, "arguments": t.function.arguments} for t in native_calls]
                    if native_calls else
                    [{"id": c["id"], "name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)} for c in text_calls]
                )
                for call in run_calls:
                    doc_id = None
                    if call["name"] == "search_paper_knowledge_base":
                        try:
                            raw_args = call["arguments"]
                            args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                            doc_id = args.get("document_id")
                            query = args.get("query", "") or ""
                            doc = db.query(Document).filter(Document.id == doc_id).first() if doc_id is not None else None
                            if doc:
                                name_without_ext = (doc.original_filename or doc.title or "").replace(".pdf", "")
                                item_info = get_item_by_name(name_without_ext) if name_without_ext else None
                                if item_info and item_info.get("kb_path"):
                                    rag_result = simple_rag_search(item_info["kb_path"], query)
                                    tool_result = (rag_result[:1600] + "...") if rag_result and len(rag_result) > 1600 else (rag_result or "未找到相关信息。")
                                else:
                                    tool_result = "该文献暂无深度知识库文件。"
                            else:
                                tool_result = "未找到该文献。"
                        except Exception as e:
                            tool_result = f"工具执行出错: {str(e)}"
                    else:
                        tool_result = "未知工具调用，已忽略。"
                    tool_results_summary.append(f"[文献{doc_id}检索结果]: {tool_result[:600]}")
                    if native_calls:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "name": call["name"],
                            "content": tool_result,
                        })
                    else:
                        # No real tool_call_id pairing exists for the emulated
                        # text-based call — feed the result back as a plain
                        # message instead of a 'tool' role, since some
                        # gateways validate tool role messages strictly.
                        messages.append({"role": "user", "content": f"[工具结果] {tool_result}"})

                total_content_len = sum(len(str(m.get("content", ""))) for m in messages)
                if total_content_len > 24000:
                    summary = "\n".join(tool_results_summary)
                    messages = [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": f"{req.message}\n\n【已检索到的信息摘要】\n{summary}\n\n请根据以上信息直接给出推荐结果JSON。"},
                    ]
                continue

            content = _strip_text_tool_calls(raw_content)
            parsed = extract_json(content)
            if parsed and "name" in parsed and "arguments" in parsed:
                continue
            reply = ""
            doc_ids = []
            if parsed and "reply" in parsed:
                reply = parsed.get("reply") or ""
                doc_ids = parsed.get("document_ids") or []
            else:
                reply = content
                ids_in_text = [int(x) for x in re.findall(r"\[(\d+)\]", content)]
                doc_ids = ids_in_text[:8]
            if not doc_ids:
                doc_ids = fallback_ids
            packed = pack_docs(doc_ids) or pack_docs(fallback_ids)
            if not reply or not reply.strip():
                reply = "已根据你的条件筛选出下列文献。" if req.lang != "en" else "Here are the matching papers."
            return {"reply": reply, "documents": packed}
        except Exception:
            # Log the full traceback server-side for debugging, but never
            # leak a raw Python exception string into the chat UI.
            import traceback
            traceback.print_exc()
            reply = "抱歉，检索时出现了问题，已为你返回本地初筛结果。" if req.lang != "en" else "Sorry, something went wrong during search — showing local pre-filtered results instead."
            try:
                packed = pack_docs(fallback_ids)
            except Exception:
                traceback.print_exc()
                packed = []
            return {"reply": reply, "documents": packed}

    return {"reply": "未能完成检索，已返回本地预筛选结果。", "documents": pack_docs(fallback_ids)}
