import os
import sys

# Ensure the root directory is in sys.path so that 'from backend...' works
# even if the script is executed directly via `python backend/main.py`
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.core.config import get_base_dir
from backend.api import paper_router, ppt_router, chat_router, config_router
from backend.services.file_manager import scan_items, get_item_by_name
import fitz
import io
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

FRONTEND_DIR = os.path.join(get_base_dir(), "frontend")
templates = Jinja2Templates(directory=os.path.join(FRONTEND_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static")

# Include Routers
app.include_router(paper_router.router)
app.include_router(ppt_router.router)
app.include_router(chat_router.router)
app.include_router(config_router.router)

# Views and static routes
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    books = scan_items("book")
    papers = scan_items("paper")
    return templates.TemplateResponse("index.html", {"request": request, "books": books, "papers": papers})

@app.get("/chat/{book_name}", response_class=HTMLResponse)
async def chat_page(request: Request, book_name: str):
    book = get_item_by_name(book_name)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return templates.TemplateResponse("chat.html", {"request": request, "book_name": book_name, "is_paper": book["type"] == "paper"})

@app.get("/cover/{book_name}")
async def get_cover(book_name: str):
    book = get_item_by_name(book_name)
    if not book: raise HTTPException(status_code=404, detail="Book not found")
    
    try:
        doc = fitz.open(book["pdf_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="PDF not found for cover")
    try:
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
        img_data = pix.tobytes("png")
    finally:
        doc.close()
    
    return StreamingResponse(io.BytesIO(img_data), media_type="image/png")

@app.get("/pdf/{book_name}")
async def get_pdf(book_name: str):
    item = get_item_by_name(book_name)
    if not item or not os.path.exists(item.get("pdf_path", "")): raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(item["pdf_path"], media_type="application/pdf")

@app.get("/pdf_translated/{book_name}")
async def get_pdf_translated(book_name: str):
    item = get_item_by_name(book_name)
    if not item or not os.path.exists(item.get("translated_pdf_path", "")) : raise HTTPException(status_code=404, detail="Translated PDF not found")
    return FileResponse(item["translated_pdf_path"], media_type="application/pdf")

@app.get("/pdf_annotated/{book_name}")
async def get_pdf_annotated(book_name: str):
    item = get_item_by_name(book_name)
    if not item or not os.path.exists(item.get("annotated_pdf_path", "")) : raise HTTPException(status_code=404, detail="Annotated PDF not found")
    return FileResponse(item["annotated_pdf_path"], media_type="application/pdf")

@app.get("/ppt_editor/{book_name}")
async def ppt_editor_page(request: Request, book_name: str):
    return RedirectResponse(f"http://localhost:8081/?book={book_name}")

if __name__ == "__main__":
    import uvicorn
    import webbrowser
    import threading
    import time
    
    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:8900/")
        
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8900, reload=False)
