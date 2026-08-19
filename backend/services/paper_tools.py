# coding=utf-8
"""Paper utility exports — wrap mature open-source tools, no custom converters."""
from __future__ import annotations

import json
import os
import shutil
import zipfile
from typing import List, Optional, Tuple

import fitz

from backend.core.config import get_base_dir
from backend.services.project_manager import ProjectManager


def _paper_dir(book_name: str) -> str:
    return os.path.join(get_base_dir(), "data", "papers", book_name)


def resolve_pdf(book_name: str, which: str = "raw") -> str:
    d = _paper_dir(book_name)
    mapping = {
        "raw": os.path.join(d, "raw", f"{book_name}.pdf"),
        "translated": os.path.join(d, "translated", f"{book_name}_translated.pdf"),
        "annotated": os.path.join(d, "marked", f"{book_name}_annotated.pdf"),
    }
    path = mapping.get(which) or mapping["raw"]
    if os.path.isfile(path):
        return path
    raw = mapping["raw"]
    if os.path.isfile(raw):
        return raw
    raise FileNotFoundError(f"PDF not found for {book_name}")


def export_pages_as_images(pdf_path: str, out_dir: str, dpi: int = 300, pages: Optional[List[int]] = None) -> List[str]:
    """Rasterize PDF pages with PyMuPDF at a user-chosen DPI (not a blurry 72dpi dump)."""
    dpi = max(72, min(int(dpi or 300), 600))
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    written = []
    try:
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        indices = pages if pages else list(range(len(doc)))
        for i in indices:
            if i < 0 or i >= len(doc):
                continue
            pix = doc[i].get_pixmap(matrix=mat, alpha=False)
            name = f"page_{i + 1:03d}_{dpi}dpi.png"
            dest = os.path.join(out_dir, name)
            pix.save(dest)
            written.append(dest)
        return written
    finally:
        doc.close()


def _load_figure_details(paper_dir: str) -> dict:
    for name in ("figures_extract_details.json", "figures_metadata.json"):
        path = os.path.join(paper_dir, "images", name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            continue
        if isinstance(data, dict) and any(isinstance(v, dict) and v.get("bbox") for v in data.values()):
            return data
    return {}


def _render_figures_at_dpi(pdf_path: str, details: dict, out_dir: str, dpi: int) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    written = []
    doc = fitz.open(pdf_path)
    try:
        for filename, meta in (details or {}).items():
            if not isinstance(meta, dict):
                continue
            bbox = meta.get("bbox")
            page_no = int(meta.get("page") or 1) - 1
            if not bbox or page_no < 0 or page_no >= len(doc):
                continue
            page = doc[page_no]
            rect = fitz.Rect(*[float(x) for x in bbox]) & page.rect
            if rect.width < 8 or rect.height < 8:
                continue
            try:
                pix = page.get_pixmap(dpi=dpi, clip=rect, alpha=False)
            except TypeError:
                zoom = dpi / 72.0
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect, alpha=False)
            dest_name = filename if str(filename).lower().endswith((".png", ".jpg", ".jpeg")) else f"{filename}.png"
            dest = os.path.join(out_dir, os.path.basename(dest_name))
            pix.save(dest)
            written.append(dest)
    finally:
        doc.close()
    return written


def export_figures(pdf_path: str, book_name: str, dpi: int = 300) -> str:
    """Re-extract paper figures at requested DPI into a zip."""
    dpi = max(72, min(int(dpi or 300), 600))
    target = _paper_dir(book_name)
    img_dir = os.path.join(target, "exports", f"figures_{dpi}dpi")
    if os.path.isdir(img_dir):
        shutil.rmtree(img_dir, ignore_errors=True)
    os.makedirs(img_dir, exist_ok=True)

    details = _load_figure_details(target)
    if not details:
        pm = ProjectManager(base_dir=target)
        images_root = os.path.join(target, "images")
        if not os.path.isdir(images_root) or not os.listdir(images_root):
            pm.extract_semantic_figures(pdf_path, target)
        details = _load_figure_details(target)

    written = _render_figures_at_dpi(pdf_path, details, img_dir, dpi) if details else []
    if not written:
        existing = os.path.join(target, "images")
        if os.path.isdir(existing):
            for f in os.listdir(existing):
                if f.lower().endswith((".png", ".jpg", ".jpeg")):
                    shutil.copy2(os.path.join(existing, f), os.path.join(img_dir, f))
                    written.append(os.path.join(img_dir, f))
    if not written:
        _dump_embedded_images(pdf_path, img_dir)

    zip_path = os.path.join(target, "exports", f"{book_name}_figures_{dpi}dpi.zip")
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in os.listdir(img_dir):
            z.write(os.path.join(img_dir, f), f)
    return zip_path


def _dump_embedded_images(pdf_path: str, out_dir: str):
    doc = fitz.open(pdf_path)
    try:
        n = 0
        for pno, page in enumerate(doc):
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha > 3:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    n += 1
                    pix.save(os.path.join(out_dir, f"embed_p{pno+1}_{n}.png"))
                except Exception:
                    continue
    finally:
        doc.close()


def export_docx(pdf_path: str, out_path: str) -> str:
    """PDF → Word via open-source pdf2docx (https://github.com/dothinking/pdf2docx)."""
    try:
        from pdf2docx import Converter
    except ImportError as e:
        raise RuntimeError("未安装 pdf2docx。请执行 pip install pdf2docx") from e
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv = Converter(pdf_path)
    try:
        cv.convert(out_path)
    finally:
        cv.close()
    if not os.path.isfile(out_path):
        raise RuntimeError("pdf2docx 未生成 Word 文件")
    return out_path


def export_markdown_or_latex(pdf_path: str, out_path: str, fmt: str = "md") -> str:
    """
    PDF → Markdown / LaTeX via pymupdf4llm (https://github.com/pymupdf/pymupdf4llm).
    Heavier neural converters (Nougat / Marker) are optional if installed.
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    text = ""
    try:
        import pymupdf4llm
        text = pymupdf4llm.to_markdown(pdf_path)
    except Exception:
        doc = fitz.open(pdf_path)
        try:
            parts = []
            for i, page in enumerate(doc):
                parts.append(f"\n\n% page {i+1}\n\n" + (page.get_text("text") or ""))
            text = "".join(parts)
        finally:
            doc.close()

    if fmt in ("tex", "latex"):
        body = _markdown_to_latex(text)
        if not out_path.endswith(".tex"):
            out_path = os.path.splitext(out_path)[0] + ".tex"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(body)
    else:
        if not out_path.endswith(".md"):
            out_path = os.path.splitext(out_path)[0] + ".md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text or "")
    return out_path


def _markdown_to_latex(md: str) -> str:
    # Prefer pandoc when present
    import subprocess
    import tempfile
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as tmp:
            tmp.write(md)
            md_path = tmp.name
        tex_path = md_path + ".tex"
        subprocess.run(
            ["pandoc", md_path, "-f", "markdown", "-t", "latex", "-o", tex_path, "--standalone"],
            check=True,
            capture_output=True,
            timeout=60,
        )
        with open(tex_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        escaped = (
            (md or "")
            .replace("\\", "\\textbackslash{}")
            .replace("&", "\\&")
            .replace("%", "\\%")
            .replace("$", "\\$")
            .replace("#", "\\#")
            .replace("_", "\\_")
        )
        return (
            "\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n"
            "\\usepackage{hyperref}\n\\begin{document}\n"
            + escaped
            + "\n\\end{document}\n"
        )


def _rapidocr_lines(result):
    if result is None:
        return []
    if hasattr(result, "txts") and hasattr(result, "boxes"):
        boxes = result.boxes or []
        txts = result.txts or []
        scores = list(getattr(result, "scores", None) or [1.0] * len(txts))
        return list(zip(boxes, txts, scores))
    if isinstance(result, tuple) and len(result) >= 2:
        boxes, txts = result[0], result[1]
        if boxes is None:
            return []
        scores = result[2] if len(result) > 2 and result[2] is not None else [1.0] * len(txts or [])
        return list(zip(boxes, txts or [], scores))
    if isinstance(result, list):
        out = []
        for item in result:
            if not item:
                continue
            box, text = item[0], item[1]
            score = item[2] if len(item) > 2 else 1.0
            out.append((box, text, score))
        return out
    return []


def _ocr_with_rapidocr(pdf_path: str, out_path: str) -> str:
    """Searchable PDF via RapidOCR (pip: rapidocr + onnxruntime). No Tesseract."""
    import numpy as np
    from rapidocr import RapidOCR

    engine = RapidOCR()
    font = fitz.Font("helv")
    fontfile = None
    for fp in (
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
    ):
        if os.path.isfile(fp):
            fontfile = fp
            break

    doc = fitz.open(pdf_path)
    wrote = 0
    try:
        zoom = 2.0
        mat = fitz.Matrix(zoom, zoom)
        for page in doc:
            existing = (page.get_text("text") or "").strip()
            if len(existing) > 80:
                continue
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            result = engine(img)
            lines = _rapidocr_lines(result)
            sx = page.rect.width / max(pix.width, 1)
            sy = page.rect.height / max(pix.height, 1)
            tw = fitz.TextWriter(page.rect)
            for box, text, score in lines:
                text = (text or "").strip()
                if not text or (isinstance(score, (int, float)) and score < 0.4):
                    continue
                try:
                    xs = [float(p[0]) for p in box]
                    ys = [float(p[1]) for p in box]
                except Exception:
                    continue
                rect = fitz.Rect(min(xs) * sx, min(ys) * sy, max(xs) * sx, max(ys) * sy)
                if rect.width < 2 or rect.height < 2:
                    continue
                tl = font.text_length(text, fontsize=1) or 1.0
                fontsize = max(4.0, min(rect.width / tl, rect.height * 0.9))
                pos = fitz.Point(rect.x0, rect.y1)
                try:
                    if fontfile:
                        page.insert_text(
                            pos, text, fontsize=fontsize, fontfile=fontfile,
                            render_mode=3, overlay=True,
                        )
                    else:
                        tw.append(pos, text, font=font, fontsize=fontsize)
                    wrote += 1
                except Exception:
                    continue
            if not fontfile:
                try:
                    tw.write_text(page, render_mode=3)
                except TypeError:
                    tw.writeText(page, render_mode=3)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        doc.save(out_path, incremental=False, deflate=True)
    finally:
        doc.close()
    if wrote == 0 and not os.path.isfile(out_path):
        raise RuntimeError("RapidOCR 未识别到文字")
    print(f"[OCR] RapidOCR wrote {wrote} text boxes -> {out_path}")
    return out_path


def ocr_pdf(pdf_path: str, out_path: str, lang: str = "eng") -> str:
    """
    Make a searchable PDF without requiring a system Tesseract install.
    Primary: RapidOCR (https://github.com/RapidAI/RapidOCR) via pip.
    Optional: OCRmyPDF if Tesseract is present on PATH.
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    errors = []

    try:
        return _ocr_with_rapidocr(pdf_path, out_path)
    except Exception as e:
        errors.append(f"RapidOCR: {e}")
        print(f"[OCR] RapidOCR failed: {e}")

    tesseract = shutil.which("tesseract")
    if tesseract:
        try:
            import ocrmypdf
            ocrmypdf.ocr(pdf_path, out_path, language=lang, skip_text=True, optimize=1)
            if os.path.isfile(out_path):
                return out_path
        except Exception as e:
            errors.append(f"ocrmypdf: {e}")
            print(f"[OCR] ocrmypdf failed: {e}")

    raise RuntimeError("OCR 失败：" + " | ".join(errors))


def rotate_pdf(pdf_path: str, out_path: str, angle: int = 90, pages: Optional[List[int]] = None) -> str:
    """Rotate PDF pages via pikepdf (https://github.com/pikepdf/pikepdf, wraps qpdf)."""
    import pikepdf

    angle = int(angle or 90) % 360
    if angle % 90 != 0:
        angle = 90
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with pikepdf.open(pdf_path) as pdf:
        indices = pages if pages else range(len(pdf.pages))
        for i in indices:
            if 0 <= i < len(pdf.pages):
                pdf.pages[i].rotate(angle, relative=True)
        pdf.save(out_path)
    return out_path


def split_pdf(pdf_path: str, out_path: str, start: int = 1, end: Optional[int] = None) -> str:
    """Extract an inclusive 1-based page range into a new PDF via pikepdf."""
    import pikepdf

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with pikepdf.open(pdf_path) as pdf:
        n = len(pdf.pages)
        s = max(1, int(start or 1))
        e = min(n, int(end or n))
        if s > e:
            raise ValueError("起始页不能大于结束页")
        new_pdf = pikepdf.new()
        try:
            for i in range(s - 1, e):
                new_pdf.pages.append(pdf.pages[i])
            new_pdf.save(out_path)
        finally:
            new_pdf.close()
    return out_path


def merge_pdfs(pdf_paths: List[str], out_path: str) -> str:
    """Merge multiple PDFs in order via pikepdf."""
    import pikepdf

    if len(pdf_paths) < 2:
        raise ValueError("合并需要至少两个 PDF")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    new_pdf = pikepdf.new()
    opened = []
    try:
        for p in pdf_paths:
            src = pikepdf.open(p)
            opened.append(src)
            new_pdf.pages.extend(src.pages)
        new_pdf.save(out_path)
    finally:
        new_pdf.close()
        for src in opened:
            src.close()
    return out_path


def compress_pdf(pdf_path: str, out_path: str) -> str:
    """Losslessly optimize PDF stream/object storage via pikepdf/qpdf."""
    import pikepdf

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with pikepdf.open(pdf_path) as pdf:
        try:
            pdf.remove_unreferenced_resources()
        except Exception:
            pass
        pdf.save(
            out_path,
            compress_streams=True,
            recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            linearize=True,
        )
    before = os.path.getsize(pdf_path)
    after = os.path.getsize(out_path)
    print(f"[Compress] {before / 1024:.0f}KB -> {after / 1024:.0f}KB ({pdf_path})")
    return out_path


def watermark_pdf(pdf_path: str, out_path: str, text: str, opacity: float = 0.15) -> str:
    """Stamp a tiled diagonal text watermark on every page via PyMuPDF."""
    text = (text or "").strip()
    if not text:
        raise ValueError("水印文字不能为空")
    opacity = max(0.03, min(float(opacity or 0.15), 1.0))
    doc = fitz.open(pdf_path)
    try:
        for page in doc:
            rect = page.rect
            fontsize = max(18, min(rect.width, rect.height) / 9)
            shape = page.new_shape()
            step_x, step_y = rect.width / 2.2, rect.height / 4.5
            gy = 0
            y = 40.0
            while y < rect.height:
                gx = 0
                x = 10.0
                while x < rect.width:
                    pos = fitz.Point(x, y)
                    shape.insert_text(
                        pos, text, fontsize=fontsize,
                        morph=(pos, fitz.Matrix(45)),
                        color=(0.5, 0.5, 0.5), fill_opacity=opacity,
                    )
                    x += step_x
                    gx += 1
                y += step_y
                gy += 1
            shape.commit()
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        doc.save(out_path, incremental=False, deflate=True)
    finally:
        doc.close()
    return out_path


def protect_pdf(pdf_path: str, out_path: str, password: str, owner_password: Optional[str] = None) -> str:
    """Encrypt a PDF with an open password via pikepdf."""
    import pikepdf

    password = (password or "").strip()
    if not password:
        raise ValueError("密码不能为空")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with pikepdf.open(pdf_path) as pdf:
        pdf.save(
            out_path,
            encryption=pikepdf.Encryption(user=password, owner=owner_password or password, R=6),
        )
    return out_path


def unlock_pdf(pdf_path: str, out_path: str, password: str = "") -> str:
    """Remove password protection from a PDF via pikepdf."""
    import pikepdf

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with pikepdf.open(pdf_path, password=password or "") as pdf:
        pdf.save(out_path)
    return out_path


def add_text_markup(
    pdf_path: str,
    out_path: str,
    page_number: int,
    quads_or_rects: List[dict],
    kind: str = "highlight",
    color: Tuple[float, float, float] = (1, 1, 0),
    note: str = "",
) -> str:
    """Add user highlight / underline / squiggly / note onto a PDF page (1-based)."""
    doc = fitz.open(pdf_path)
    try:
        idx = max(0, int(page_number) - 1)
        if idx >= len(doc):
            raise ValueError("page out of range")
        page = doc[idx]
        rects = []
        for item in quads_or_rects or []:
            r = fitz.Rect(
                float(item["x0"]), float(item["y0"]),
                float(item["x1"]), float(item["y1"]),
            )
            rects.append(r)
        if not rects:
            raise ValueError("no rects")
        kind = (kind or "highlight").lower()
        annot = None
        if kind in ("highlight", "hl"):
            annot = page.add_highlight_annot(rects)
        elif kind in ("underline", "ul"):
            annot = page.add_underline_annot(rects)
        elif kind in ("squiggly", "wave"):
            annot = page.add_squiggly_annot(rects)
        elif kind in ("strike", "strikethrough"):
            annot = page.add_strikeout_annot(rects)
        else:
            annot = page.add_highlight_annot(rects)
        if annot is not None:
            annot.set_colors(stroke=color)
            if note:
                annot.set_info(title="Note", content=note)
            annot.update()
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        doc.save(out_path, incremental=False, deflate=True)
        return out_path
    finally:
        doc.close()
