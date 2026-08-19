from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import shutil

from urllib.parse import quote

from backend.core.config import get_base_dir
from backend.services.paper_tools import (
    resolve_pdf,
    export_pages_as_images,
    export_figures,
    export_docx,
    export_markdown_or_latex,
    ocr_pdf,
    add_text_markup,
    rotate_pdf,
    split_pdf,
    merge_pdfs,
    compress_pdf,
    watermark_pdf,
    protect_pdf,
    unlock_pdf,
)


class MergeRequest(BaseModel):
    book_names: List[str]
    sources: Optional[List[str]] = None  # per-book source: raw | translated | annotated
    out_name: Optional[str] = None

router = APIRouter(prefix="/api/tools", tags=["tools"])


class MarkupRequest(BaseModel):
    book_name: str
    page: int
    kind: str = "highlight"
    color: Optional[List[float]] = None
    note: str = ""
    rects: List[dict]
    source: str = "raw"  # raw | translated | annotated


def _exports_dir(book_name: str) -> str:
    d = os.path.join(get_base_dir(), "data", "papers", book_name, "exports")
    os.makedirs(d, exist_ok=True)
    return d


def _download_url(book_name: str, filename: str) -> str:
    return f"/api/tools/download?book_name={quote(book_name)}&file={quote(os.path.basename(filename))}"


@router.post("/export/images")
def api_export_images(book_name: str = Query(...), dpi: int = 300, source: str = "raw"):
    try:
        pdf = resolve_pdf(book_name, source)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    out_dir = os.path.join(_exports_dir(book_name), f"pages_{dpi}dpi")
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir, ignore_errors=True)
    files = export_pages_as_images(pdf, out_dir, dpi=dpi)
    zip_name = f"{book_name}_pages_{dpi}dpi.zip"
    zip_path = os.path.join(_exports_dir(book_name), zip_name)
    import zipfile
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, os.path.basename(p))
    return {"status": "success", "count": len(files), "download": _download_url(book_name, zip_name)}


@router.post("/export/figures")
def api_export_figures(book_name: str = Query(...), dpi: int = 300, source: str = "raw"):
    try:
        pdf = resolve_pdf(book_name, source)
        zip_path = export_figures(pdf, book_name, dpi=dpi)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"status": "success", "download": _download_url(book_name, zip_path)}


@router.post("/export/docx")
def api_export_docx(book_name: str = Query(...), source: str = "raw"):
    try:
        pdf = resolve_pdf(book_name, source)
        out = os.path.join(_exports_dir(book_name), f"{book_name}.docx")
        export_docx(pdf, out)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(501, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"status": "success", "download": _download_url(book_name, out)}


@router.post("/export/text")
def api_export_text(book_name: str = Query(...), fmt: str = "md", source: str = "raw"):
    try:
        pdf = resolve_pdf(book_name, source)
        ext = "tex" if fmt in ("tex", "latex") else "md"
        out = os.path.join(_exports_dir(book_name), f"{book_name}.{ext}")
        export_markdown_or_latex(pdf, out, fmt=fmt)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"status": "success", "download": _download_url(book_name, out)}


@router.post("/ocr")
def api_ocr(book_name: str = Query(...), lang: str = "eng", source: str = "raw"):
    try:
        pdf = resolve_pdf(book_name, source)
        out = os.path.join(_exports_dir(book_name), f"{book_name}_ocr.pdf")
        ocr_pdf(pdf, out, lang=lang)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(501, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"status": "success", "download": _download_url(book_name, out)}


@router.post("/rotate")
def api_rotate(book_name: str = Query(...), angle: int = 90, source: str = "raw"):
    try:
        pdf = resolve_pdf(book_name, source)
        out = os.path.join(_exports_dir(book_name), f"{book_name}_rotated.pdf")
        rotate_pdf(pdf, out, angle=angle)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"status": "success", "download": _download_url(book_name, out)}


@router.post("/split")
def api_split(book_name: str = Query(...), start: int = 1, end: Optional[int] = None, source: str = "raw"):
    try:
        pdf = resolve_pdf(book_name, source)
        out = os.path.join(_exports_dir(book_name), f"{book_name}_p{start}-{end or 'end'}.pdf")
        split_pdf(pdf, out, start=start, end=end)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"status": "success", "download": _download_url(book_name, out)}


@router.post("/compress")
def api_compress(book_name: str = Query(...), source: str = "raw"):
    try:
        pdf = resolve_pdf(book_name, source)
        out = os.path.join(_exports_dir(book_name), f"{book_name}_compressed.pdf")
        compress_pdf(pdf, out)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"status": "success", "download": _download_url(book_name, out)}


@router.post("/watermark")
def api_watermark(book_name: str = Query(...), text: str = Query(...), opacity: float = 0.15, source: str = "raw"):
    try:
        pdf = resolve_pdf(book_name, source)
        out = os.path.join(_exports_dir(book_name), f"{book_name}_watermarked.pdf")
        watermark_pdf(pdf, out, text=text, opacity=opacity)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"status": "success", "download": _download_url(book_name, out)}


@router.post("/protect")
def api_protect(book_name: str = Query(...), password: str = Query(...), source: str = "raw"):
    try:
        pdf = resolve_pdf(book_name, source)
        out = os.path.join(_exports_dir(book_name), f"{book_name}_protected.pdf")
        protect_pdf(pdf, out, password=password)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"status": "success", "download": _download_url(book_name, out)}


@router.post("/unlock")
def api_unlock(book_name: str = Query(...), password: str = "", source: str = "raw"):
    try:
        pdf = resolve_pdf(book_name, source)
        out = os.path.join(_exports_dir(book_name), f"{book_name}_unlocked.pdf")
        unlock_pdf(pdf, out, password=password)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"status": "success", "download": _download_url(book_name, out)}


@router.post("/merge")
def api_merge(req: MergeRequest):
    if len(req.book_names) < 2:
        raise HTTPException(400, "合并至少需要两篇文献")
    sources = req.sources or ["raw"] * len(req.book_names)
    try:
        paths = [
            resolve_pdf(name, sources[i] if i < len(sources) else "raw")
            for i, name in enumerate(req.book_names)
        ]
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    out_name = os.path.basename(req.out_name or ("merged_" + "_".join(req.book_names)))[:80] or "merged"
    out_dir = os.path.join(get_base_dir(), "data", "exports")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{out_name}.pdf")
    try:
        merge_pdfs(paths, out)
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"status": "success", "download": f"/api/tools/download_global?file={quote(os.path.basename(out))}"}


@router.get("/download_global")
def api_download_global(file: str = Query(...)):
    safe_file = os.path.basename(file)
    base = os.path.normpath(os.path.join(get_base_dir(), "data", "exports"))
    full = os.path.normpath(os.path.join(base, safe_file))
    try:
        common = os.path.commonpath([base, full])
    except ValueError:
        raise HTTPException(403, "invalid path")
    if common != base or not os.path.isfile(full):
        raise HTTPException(403, "invalid path")
    return FileResponse(full, filename=safe_file)


@router.post("/markup")
def api_markup(req: MarkupRequest):
    try:
        pdf = resolve_pdf(req.book_name, req.source)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    # Write back onto the same file so the viewer refresh picks it up
    color = tuple(req.color) if req.color and len(req.color) == 3 else (1.0, 0.92, 0.23)
    tmp = pdf + ".tmp.pdf"
    try:
        add_text_markup(pdf, tmp, req.page, req.rects, kind=req.kind, color=color, note=req.note)
        os.replace(tmp, pdf)
    except Exception as e:
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise HTTPException(400, str(e))
    return {"status": "success"}


@router.get("/download")
def api_download(book_name: str = Query(...), file: str = Query(...)):
    safe_book = os.path.basename(book_name)
    safe_file = os.path.basename(file)
    base = os.path.normpath(_exports_dir(safe_book))
    full = os.path.normpath(os.path.join(base, safe_file))
    try:
        common = os.path.commonpath([base, full])
    except ValueError:
        raise HTTPException(403, "invalid path")
    if common != base or not os.path.isfile(full):
        raise HTTPException(403, "invalid path")
    return FileResponse(full, filename=safe_file)
