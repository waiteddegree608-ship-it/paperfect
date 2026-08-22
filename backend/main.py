import os
import sys
import json

# Windows console: avoid 锟斤拷 mojibake when printing Chinese (force UTF-8 streams)
if sys.platform == "win32":
    try:
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure standard streams are redirected to app_debug.log if running as frozen executable
if getattr(sys, 'frozen', False) or sys.stdout is None or sys.stderr is None:
    try:
        # Redirect outputs to app_debug.log in the executable folder
        log_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        log_file = open(os.path.join(log_dir, "app_debug.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file
    except Exception:
        # Fallback to devnull
        try:
            devnull = open(os.devnull, "w")
            sys.stdout = devnull
            sys.stderr = devnull
        except Exception:
            pass

# Ensure the root directory is in sys.path so that 'from backend...' works
# even if the script is executed directly via `python backend/main.py`
# Packaged: paperfect.exe lives next to backend/ + frontend/ (dist_portable root)
if getattr(sys, "frozen", False):
    _root = os.path.dirname(sys.executable)
else:
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.core.config import get_base_dir
from backend.api import paper_router, ppt_router, chat_router, config_router, library_router, tools_router
from backend.services.file_manager import scan_items, get_item_by_name
import fitz
import io
import functools
from fastapi.responses import StreamingResponse
from fastapi import HTTPException

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disable_stale_frontend_cache(request: Request, call_next):
    """Prevent Electron persist: partition from serving old PPT toolbar HTML/JS."""
    response = await call_next(request)
    path = request.url.path or ""
    if (
        path.startswith("/ppt_editor_app")
        or path.startswith("/chat/")
        or path == "/"
        or path.endswith(".html")
        or path.endswith(".js")
        or path.endswith(".css")
    ):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


FRONTEND_DIR = os.path.join(get_base_dir(), "frontend")
templates = Jinja2Templates(directory=os.path.join(FRONTEND_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static")

# Create frontend/ppt_editor if it doesn't exist to prevent startup crash
ppt_editor_dir = os.path.join(FRONTEND_DIR, "ppt_editor")
os.makedirs(ppt_editor_dir, exist_ok=True)
app.mount("/ppt_editor_app", StaticFiles(directory=ppt_editor_dir), name="ppt_editor_app")

# Include Routers
app.include_router(paper_router.router)
app.include_router(ppt_router.router)
app.include_router(chat_router.router)
app.include_router(config_router.router)
app.include_router(library_router.router)
app.include_router(tools_router.router)

# Views and static routes
@app.get("/", response_class=HTMLResponse)
async def library_page(request: Request):
    return templates.TemplateResponse(request, "library.html")




@app.get("/chat/{book_name}", response_class=HTMLResponse)
async def chat_page(request: Request, book_name: str):
    book = get_item_by_name(book_name)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return templates.TemplateResponse(request, "chat.html", {"book_name": book_name, "is_paper": book["type"] == "paper"})

@app.get("/cover/{book_name}")
def get_cover(book_name: str):
    book = get_item_by_name(book_name)
    if not book: raise HTTPException(status_code=404, detail="Book not found")
    
    pdf_path = book["pdf_path"]
    cover_path = pdf_path.replace(".pdf", "_cover.png")
    
    if not os.path.exists(cover_path):
        try:
            doc = fitz.open(pdf_path)
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
            pix.save(cover_path)
            doc.close()
        except Exception:
            raise HTTPException(status_code=404, detail="PDF not found for cover")
    
    return FileResponse(cover_path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})

@app.get("/pdf/{book_name}")
async def get_pdf(book_name: str):
    item = get_item_by_name(book_name)
    if not item or not os.path.exists(item.get("pdf_path", "")): raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(item["pdf_path"], media_type="application/pdf", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})

@app.get("/pdf_translated/{book_name}")
async def get_pdf_translated(book_name: str):
    item = get_item_by_name(book_name)
    if not item or not os.path.exists(item.get("translated_pdf_path", "")) : raise HTTPException(status_code=404, detail="Translated PDF not found")
    return FileResponse(item["translated_pdf_path"], media_type="application/pdf", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})

@app.get("/pdf_annotated/{book_name}")
async def get_pdf_annotated(book_name: str):
    item = get_item_by_name(book_name)
    if not item or not os.path.exists(item.get("annotated_pdf_path", "")) : raise HTTPException(status_code=404, detail="Annotated PDF not found")
    return FileResponse(item["annotated_pdf_path"], media_type="application/pdf", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})

@app.get("/api/annotations/{book_name:path}")
async def get_ai_annotations(book_name: str):
    # :path allows titles with special Unicode (e.g. en-dash –) that plain {param} can mishandle
    from urllib.parse import unquote
    book_name = unquote(book_name or "").strip().strip("/")
    item = get_item_by_name(book_name)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    # Prefer path next to the annotated PDF (authoritative), fall back to reconstructed dir
    json_path = None
    ann_pdf = item.get("annotated_pdf_path") or ""
    if ann_pdf:
        cand = os.path.join(os.path.dirname(ann_pdf), "annotations.json")
        if os.path.exists(cand):
            json_path = cand
    if not json_path:
        base_dir = get_base_dir()
        # Use item["name"] (disk folder name) rather than raw URL param
        folder_name = item.get("name") or book_name
        target_dir = os.path.join(base_dir, "data", "textbooks" if item["type"] == "book" else "papers", folder_name)
        json_path = os.path.join(target_dir, "marked", "annotations.json")
    if not json_path or not os.path.exists(json_path):
        print(f"[annotations] missing json for {book_name!r} path={json_path!r}")
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[annotations] loaded {len(data) if hasattr(data, '__len__') else '?'} items from {json_path}")
        return data
    except Exception as e:
        print("Read annotations.json error:", e, "path=", json_path)
        return []

@app.get("/ppt_editor/{book_name:path}")
async def ppt_editor_page(request: Request, book_name: str):
    from urllib.parse import unquote, quote
    book_name = unquote(book_name or "").strip().strip("/")
    # Static SPA entry (no separate Node/Vite server required in production)
    return RedirectResponse(
        f"/ppt_editor_app/index.html?book={quote(book_name, safe='')}",
        status_code=302,
    )

def auto_heal_empty_abstracts():
    import threading
    import time
    import json
    
    def heal_worker():
        time.sleep(8)
        from backend.models.database import SessionLocal, Document
        from backend.services.paper_analyzer import analyze_paper, apply_analysis_to_document

        pending_ids = []
        db = SessionLocal()
        try:
            pending_ids = [
                d.id for d in db.query(Document).filter(
                    (Document.abstract == "") |
                    (Document.abstract.is_(None)) |
                    (Document.paper_type == "") |
                    (Document.paper_type.is_(None)) |
                    (Document.year.is_(None)) |
                    (Document.year == "") |
                    (Document.venue.ilike("%arxiv%")) |
                    (Document.zh_title.is_(None)) |
                    (Document.zh_title == "") |
                    (Document.zh_title == Document.title)
                ).all()
            ]
        except Exception as e:
            print(f"[Auto Heal] query failed: {e}", flush=True)
            pending_ids = []
        finally:
            db.close()

        if not pending_ids:
            return
        print(f"[Auto Heal] Found {len(pending_ids)} documents lacking metadata.", flush=True)
        for doc_id in pending_ids[:12]:
            local = SessionLocal()
            try:
                doc = local.query(Document).filter(Document.id == doc_id).first()
                if not doc or not doc.file_path or not os.path.exists(doc.file_path):
                    continue
                print(f"[Auto Heal] Healing metadata for: {doc.original_filename}...", flush=True)
                analysis = analyze_paper(doc.file_path)
                apply_analysis_to_document(local, doc, analysis)
                print(f"[Auto Heal] Successfully healed: {doc.original_filename}", flush=True)
            except Exception as e:
                print(f"[Auto Heal] Error on doc {doc_id}: {e}", flush=True)
                local.rollback()
            finally:
                local.close()
            time.sleep(1.5)
            
    threading.Thread(target=heal_worker, daemon=True).start()

@app.get("/api/health")
async def health():
    """Lightweight readiness probe for Electron / installers."""
    return {"ok": True, "service": "paperfect"}


@app.on_event("startup")
async def startup_event():
    # Heal a few pending-metadata papers in the background (per-doc, capped)
    # so a previous tag IntegrityError does not leave the library stuck.
    auto_heal_empty_abstracts()

def _run_packaged_script():
    """
    Frozen mode helper: paperfect.exe --script path/to/file.py [args...]
    Lets Electron-packaged builds re-use this exe as the Python interpreter for
    annotator / translator / book-builder subprocesses without a system Python.
    """
    import runpy
    from backend.core.config import get_base_dir as _gbd

    script_path = os.path.abspath(sys.argv[2])
    if not os.path.isfile(script_path):
        print(f"[paperfect] --script not found: {script_path}", flush=True)
        sys.exit(2)
    # Rewrite argv so scripts see: [script_path, *args]
    sys.argv = [script_path] + sys.argv[3:]
    root = _gbd()
    if root not in sys.path:
        sys.path.insert(0, root)
    runpy.run_path(script_path, run_name="__main__")


if __name__ == "__main__":
    # Packaged subprocess entry (must run before uvicorn / webview)
    if len(sys.argv) >= 3 and sys.argv[1] in ("--script", "script"):
        _run_packaged_script()
        sys.exit(0)

    import uvicorn
    import threading
    import time

    is_headless = "headless" in sys.argv or "--headless" in sys.argv or os.environ.get("PAPERFECT_HEADLESS") == "1"

    if is_headless:
        # Run uvicorn server directly on main thread (Electron spawns us this way)
        uvicorn.run(app, host="127.0.0.1", port=8900)
    else:
        # Standalone paperfect.exe with embedded webview window
        def run_server():
            uvicorn.run(app, host="127.0.0.1", port=8900)

        t = threading.Thread(target=run_server, daemon=True)
        t.start()

        time.sleep(1.2)

        # Give this process its own taskbar identity so Windows shows the
        # Paperfect icon instead of grouping it under python.exe's icon.
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.paperfect.app")
            except Exception:
                pass

        from backend.core.config import get_base_dir
        app_icon = None
        for candidate in (
            os.path.join(get_base_dir(), "frontend", "static", "app_icon.ico"),
            os.path.join(get_base_dir(), "build", "icon.ico"),
        ):
            if os.path.isfile(candidate):
                app_icon = candidate
                break

        import webview
        webview.create_window(
            "Paperfect AI Academic Assistant",
            "http://127.0.0.1:8900/",
            width=1280,
            height=768,
            min_size=(1024, 700),
        )
        webview.start(icon=app_icon)
