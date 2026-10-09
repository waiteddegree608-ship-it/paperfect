import os
import re
import hashlib
import shutil
from backend.core.config import get_base_dir

active_tasks = set()
active_tasks_progress = {}

# Windows path budget: data/papers/{name}/pptx/{name}_Full_Presentation.pptx must fit
# under ~260 chars (classic MAX_PATH) even when installed under a deep path.
_MAX_BOOK_NAME_LEN = 72
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_book_name(raw: str, max_len: int = _MAX_BOOK_NAME_LEN) -> str:
    """
    Make a filesystem-safe folder / file stem from a PDF title.
    Long arXiv-style names otherwise blow MAX_PATH and make import fail on Windows.
    """
    name = (raw or "untitled").strip()
    # Drop directory components / nulls
    name = os.path.basename(name.replace("\\", "/")).replace("\x00", "")
    # Normalize fancy punctuation that breaks paths or looks like separators
    for a, b in (
        ("\u2013", "-"),
        ("\u2014", "-"),
        ("\u2212", "-"),
        ("\u00a0", " "),
        ("\u2026", "..."),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
    ):
        name = name.replace(a, b)
    # Illegal on Windows
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = "untitled"
    if name.upper() in _WIN_RESERVED:
        name = f"paper_{name}"
    if len(name) > max_len:
        # Stable short form: head + hash of full original (uniqueness)
        digest = hashlib.md5(name.encode("utf-8", errors="ignore")).hexdigest()[:8]
        keep = max(16, max_len - 9)
        name = name[:keep].rstrip(" .-_") + "_" + digest
    return name


def ensure_unique_book_name(book_name: str, item_type: str) -> str:
    """Avoid clobbering an existing paper folder with the same short name."""
    base = get_base_dir()
    root = os.path.join(base, "data", "textbooks" if item_type == "book" else "papers")
    candidate = book_name
    n = 2
    while os.path.isdir(os.path.join(root, candidate)):
        # Only collide when folder already exists
        suffix = f"_{n}"
        stem = book_name[: max(8, _MAX_BOOK_NAME_LEN - len(suffix))].rstrip(" .-_")
        candidate = f"{stem}{suffix}"
        n += 1
        if n > 99:
            candidate = f"{book_name[:40]}_{hashlib.md5(os.urandom(8)).hexdigest()[:6]}"
            break
    return candidate

def scan_items(item_type="book"):
    items = []
    base_dir = get_base_dir()
    target_dir = os.path.join(base_dir, "data", "textbooks" if item_type == "book" else "papers")
    
    if os.path.exists(target_dir):
        for b_name in os.listdir(target_dir):
            book_dir = os.path.join(target_dir, b_name)
            if os.path.isdir(book_dir):
                pdf_file = os.path.join(book_dir, "raw", f"{b_name}.pdf")
                translated_pdf = os.path.join(book_dir, "translated", f"{b_name}_translated.pdf")
                annotated_pdf = os.path.join(book_dir, "marked", f"{b_name}_annotated.pdf")
                kb_file = os.path.join(book_dir, "parsed", f"{b_name}_KnowledgeBase.md")
                pptx_path = os.path.join(book_dir, "pptx", f"{b_name}_Full_Presentation.pptx")
                
                if item_type == "book":
                    if os.path.exists(kb_file):
                        status = "ready"
                        progress = "100%"
                        percent = 100
                    else:
                        status = "processing" if f"books_{b_name}" in active_tasks else "interrupted"
                        progress_info = active_tasks_progress.get(f"books_{b_name}", {"percent": 0, "stage": "准备中..."})
                        progress = progress_info.get("stage", "抽取中")
                        percent = progress_info.get("percent", 50)
                else:
                    pptx_ok = os.path.exists(pptx_path) and os.path.getsize(pptx_path) >= 8000
                    if pptx_ok:
                        status = "ready"
                        progress = "100%"
                        percent = 100
                    else:
                        status = "processing" if f"papers_{b_name}" in active_tasks else "interrupted"
                        progress_info = active_tasks_progress.get(f"papers_{b_name}", {"percent": 0, "stage": "准备中..."})
                        progress = progress_info.get("stage", "生成中")
                        percent = progress_info.get("percent", 50)
                    
                items.append({
                    "name": b_name,
                    "pdf_path": pdf_file if os.path.exists(pdf_file) else "",
                    "translated_pdf_path": translated_pdf if os.path.exists(translated_pdf) else "",
                    "annotated_pdf_path": annotated_pdf if os.path.exists(annotated_pdf) else "",
                    "kb_path": kb_file if os.path.exists(kb_file) else "",
                    "status": status,
                    "progress": progress,
                    "percent": percent,
                    "type": item_type
                })
    return items

def get_item_by_name(name):
    base_dir = get_base_dir()
    for item_type in ["book", "paper"]:
        target_dir = os.path.join(base_dir, "data", "textbooks" if item_type == "book" else "papers", name)
        if os.path.isdir(target_dir):
            pdf_file = os.path.join(target_dir, "raw", f"{name}.pdf")
            translated_pdf = os.path.join(target_dir, "translated", f"{name}_translated.pdf")
            annotated_pdf = os.path.join(target_dir, "marked", f"{name}_annotated.pdf")
            kb_file = os.path.join(target_dir, "parsed", f"{name}_KnowledgeBase.md")
            pptx_path = os.path.join(target_dir, "pptx", f"{name}_Full_Presentation.pptx")
            
            if item_type == "book":
                if os.path.exists(kb_file):
                    status = "ready"
                    progress = "100%"
                    percent = 100
                else:
                    status = "processing" if f"books_{name}" in active_tasks else "interrupted"
                    progress_info = active_tasks_progress.get(f"books_{name}", {"percent": 0, "stage": "准备中..."})
                    progress = progress_info.get("stage", "抽取中")
                    percent = progress_info.get("percent", 50)
            else:
                pptx_ok = os.path.exists(pptx_path) and os.path.getsize(pptx_path) >= 8000
                if pptx_ok:
                    status = "ready"
                    progress = "100%"
                    percent = 100
                else:
                    status = "processing" if f"papers_{name}" in active_tasks else "interrupted"
                    progress_info = active_tasks_progress.get(f"papers_{name}", {"percent": 0, "stage": "准备中..."})
                    progress = progress_info.get("stage", "生成中")
                    percent = progress_info.get("percent", 50)
                
            return {
                "name": name,
                "pdf_path": pdf_file if os.path.exists(pdf_file) else "",
                "translated_pdf_path": translated_pdf if os.path.exists(translated_pdf) else "",
                "annotated_pdf_path": annotated_pdf if os.path.exists(annotated_pdf) else "",
                "kb_path": kb_file if os.path.exists(kb_file) else "",
                "status": status,
                "progress": progress,
                "percent": percent,
                "type": item_type
            }
    return None

def delete_target_item(name: str, type: str):
    target_dir = os.path.join(get_base_dir(), "data", "textbooks" if type == "book" else "papers", name)
    
    # Remove from active tasks if present
    task_id = f"{type}s_{name}"
    active_tasks.discard(task_id)
    
    if os.path.exists(target_dir):
        try:
            shutil.rmtree(target_dir, ignore_errors=False)
        except Exception:
            # Fallback to ignore errors to delete whatever is not locked
            shutil.rmtree(target_dir, ignore_errors=True)
            
        # Check if the raw pdf or directory still exists
        if os.path.exists(target_dir):
            return {"status": "error", "message": "文件正被后台驻留进程占用，无法彻底物理删除。请关闭终端（run.bat）并重新打开后端，即可释放占用并彻底删除。"}
    return {"status": "success"}

async def handle_upload_file(file, item_type):
    """
    Save upload under data/{papers|textbooks}/{safe_name}/raw/{safe_name}.pdf
    Returns (book_name, pdf_path, display_title) where display_title keeps the
    human-readable original stem (may be long); book_name is path-safe.
    """
    raw_filename = os.path.basename(file.filename) if file.filename else "unknown.pdf"
    name_part, ext_part = os.path.splitext(raw_filename)
    display_title = name_part.strip() or "untitled"
    if display_title.lower().endswith(".pdf"):
        display_title = display_title[:-4]

    book_name = sanitize_book_name(display_title)
    book_name = ensure_unique_book_name(book_name, item_type)
    # Always use .pdf stem matching folder name (downstream assumes this)
    filename = f"{book_name}.pdf"

    target_dir = os.path.join(
        get_base_dir(),
        "data",
        "textbooks" if item_type == "book" else "papers",
        book_name,
        "raw",
    )
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError as e:
        raise RuntimeError(
            f"无法创建论文目录（文件名可能过长或含非法字符）。已尝试: {book_name!r}. 原始错误: {e}"
        ) from e

    pdf_path = os.path.join(target_dir, filename)
    # Guard: refuse if still over conservative path budget
    if len(os.path.abspath(pdf_path)) > 240:
        # Emergency shorter name
        short = sanitize_book_name(display_title, max_len=40)
        short = ensure_unique_book_name(short, item_type)
        book_name = short
        filename = f"{book_name}.pdf"
        target_dir = os.path.join(
            get_base_dir(),
            "data",
            "textbooks" if item_type == "book" else "papers",
            book_name,
            "raw",
        )
        os.makedirs(target_dir, exist_ok=True)
        pdf_path = os.path.join(target_dir, filename)

    content = await file.read()
    try:
        with open(pdf_path, "wb") as buffer:
            buffer.write(content)
    except OSError as e:
        raise RuntimeError(
            f"无法写入 PDF（路径过长或磁盘权限问题）: {pdf_path} — {e}"
        ) from e

    # Persist original title for UI (optional sidecar)
    try:
        meta_path = os.path.join(os.path.dirname(target_dir), "upload_meta.json")
        import json
        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(
                {"display_title": display_title, "original_filename": raw_filename, "book_name": book_name},
                mf,
                ensure_ascii=False,
                indent=2,
            )
    except Exception:
        pass

    return book_name, pdf_path, display_title
