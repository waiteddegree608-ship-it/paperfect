"""Source-grounded reading editions, figure overlays and detailed paper notes.

Artifacts are separate from the legacy bilingual PDF. Per-request fingerprints
allow interrupted jobs to resume without reusing outputs from another source,
model or skill. No provider credentials are written into artifacts.
"""
from __future__ import annotations

import base64
import hashlib
import html
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import threading

import fitz
from openai import OpenAI

from backend.core.config import load_config, opencode_headers
from backend.services.model_pick import strip_think
from backend.services.skill_registry import load_skill

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
STYLE = """body{font:17px/1.85 system-ui,'Microsoft YaHei',sans-serif;color:#172b3a;background:#f5f7fa;margin:0}main{max-width:960px;margin:auto;padding:36px;background:white}h1,h2,h3{line-height:1.35}section{margin:40px 0;border-top:1px solid #dbe3ea;padding-top:24px}img{max-width:100%;height:auto}figure{margin:24px 0}figcaption,small{color:#566579}table{border-collapse:collapse;display:block;overflow:auto}td,th{border:1px solid #ced8e2;padding:8px}details{background:#f1f5f9;padding:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere}.warning{color:#9a3412}a{color:#075985}@media print{main{padding:0}details{display:none}}"""


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def workspace_lock(out: Path):
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(str(out.resolve()), threading.Lock())


class SafeHTML(HTMLParser):
    """Allow semantic markup only; generated content cannot load remote resources."""
    TAGS = set("h1 h2 h3 h4 p ul ol li strong em sub sup table thead tbody tr th td caption div span pre code blockquote figure figcaption br".split())

    def __init__(self, assets):
        super().__init__(convert_charrefs=True)
        self.assets, self.parts, self.stack = assets, [], []

    def handle_starttag(self, tag, attrs):
        if tag == "asset":
            self.parts.append(self.assets.get(dict(attrs).get("id"), '<p class="warning">Missing source asset</p>'))
        elif tag in self.TAGS:
            safe = ""
            for key, value in attrs:
                if tag in ("td", "th") and key in ("rowspan", "colspan") and str(value).isdigit() and 1 <= int(value) <= 100:
                    safe += f' {key}="{int(value)}"'
            self.parts.append(f"<{tag}{safe}>")
            if tag != "br":
                self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack:
                current = self.stack.pop()
                self.parts.append(f"</{current}>")
                if current == tag:
                    break

    def handle_data(self, text):
        self.parts.append(html.escape(text))

    def result(self):
        return "".join(self.parts) + "".join(f"</{tag}>" for tag in reversed(self.stack))


def sanitize_html(text, assets):
    parser = SafeHTML(assets)
    parser.feed(text)
    return parser.result()


def validate_bbox(value):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("Expected bbox [x0,y0,x1,y1]")
    box = [float(v) for v in value]
    if not all(math.isfinite(v) and 0 <= v <= 1000 for v in box) or box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError("Invalid or out-of-bounds crop")
    return box


def validate_labels(data):
    labels = data.get("labels")
    if not isinstance(labels, list):
        raise ValueError("Missing labels list")
    clean = []
    for label in labels:
        box = validate_bbox(label.get("bbox"))
        if not isinstance(label.get("text"), str) or not isinstance(label.get("source"), str):
            raise ValueError("Invalid label text")
        rotation = label.get("rotation", 0)
        if rotation not in (0, 90, -90):
            raise ValueError("Unsupported label rotation")
        colors = {k: label.get(k, default) for k, default in (("background", "#ffffff"), ("color", "#172b3a"))}
        if any(not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in colors.values()):
            raise ValueError("Invalid label color")
        clean.append({**label, **colors, "bbox": box, "rotation": rotation})
    return clean


def validate_page(data, number):
    if data.get("page") != number or not isinstance(data.get("html"), str) or not data["html"].strip():
        raise ValueError("Missing page or translation content")
    if not isinstance(data.get("crops", []), list) or not isinstance(data.get("warnings", []), list):
        raise ValueError("Invalid page assets or warnings")
    ids = set()
    for crop in data.get("crops", []):
        cid = crop.get("id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", cid) or cid in ids or crop.get("kind") not in ("figure", "equation", "table_original"):
            raise ValueError("Invalid crop identity")
        ids.add(cid)
        validate_bbox(crop.get("bbox"))


def validate_note_part(data, source_pages):
    if not isinstance(data.get("summary"), str) or not data["summary"].strip() or not data.get("sections") or not data.get("evidence"):
        raise ValueError("Missing explanation or evidence")
    for section in data["sections"]:
        if not isinstance(section.get("text"), str) or not section["text"].strip() or not section.get("pages"):
            raise ValueError("Missing detailed section or source pages")
        if any(type(n) is not int or n not in source_pages for n in section["pages"]):
            raise ValueError("Section cites a page not supplied to the model")


def localized_svg(png: bytes, width: int, height: int, labels: list) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<title>Chinese label overlay — original pixels retained; visual review required</title>',
             f'<image width="{width}" height="{height}" href="data:image/png;base64,{base64.b64encode(png).decode()}"/>']
    for lab in validate_labels({"labels": labels}):
        x0, y0, x1, y1 = lab["bbox"]
        x, y, w, h = x0 * width / 1000, y0 * height / 1000, (x1-x0)*width/1000, (y1-y0)*height/1000
        lines = lab["text"].replace("\\n", "\n").splitlines() or [""]
        rw, rh = (h, w) if lab["rotation"] else (w, h)
        units = max(sum(1 if ord(c) > 255 else .56 for c in line) for line in lines)
        size = min(rh / (len(lines)*1.2), rw / max(1, units))
        parts.append(f'<g><title>{html.escape(lab["source"])}</title><rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{lab["background"]}"/>')
        parts.append(f'<g transform="translate({x+w/2:.2f} {y+h/2:.2f}) rotate({lab["rotation"]})" font-family="Microsoft YaHei,Noto Sans SC,sans-serif" font-size="{size:.2f}" text-anchor="middle" fill="{lab["color"]}">')
        for i, line in enumerate(lines):
            parts.append(f'<text x="0" y="{(i-(len(lines)-1)/2)*size*1.2:.2f}" dominant-baseline="central">{html.escape(line)}</text>')
        parts.append("</g></g>")
    return "".join(parts) + "</svg>"


class ResearchClient:
    def __init__(self, stage):
        cfg = load_config()
        self.model, self.url = cfg[f"{stage}_model"], cfg[f"{stage}_api_url"]
        key = cfg.get(f"{stage}_api_key")
        if not key:
            raise ValueError(f"Configure {stage.upper()}_API_KEY in Settings")
        self.client = OpenAI(api_key=key, base_url=self.url, timeout=180, max_retries=0,
                             default_headers=opencode_headers(f"paperfect-{stage}-reading"))

    def json(self, skill, content, cache: Path, force=False, validate=None):
        fingerprint = hashlib.sha256(json.dumps([self.url, self.model, skill, content], ensure_ascii=False).encode()).hexdigest()
        if cache.exists() and not force:
            saved = json.loads(cache.read_text(encoding="utf-8"))
            if saved.get("fingerprint") == fingerprint:
                if validate:
                    validate(saved["data"])
                return saved["data"]
        response = self.client.chat.completions.create(model=self.model, messages=[
            {"role": "system", "content": skill}, {"role": "user", "content": content}], max_tokens=12000)
        if not response.choices or response.choices[0].finish_reason != "stop":
            raise ValueError("Model output incomplete; cached artifact was not replaced")
        raw = strip_think(response.choices[0].message.content or "")
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        if validate:
            validate(data)
        write_json(cache, {"fingerprint": fingerprint, "model": self.model, "data": data,
                           "usage": response.usage.model_dump() if response.usage else None})
        return data


def image_content(png):
    return {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}


def translate_reading(pdf_path: str, output_dir: str, pages: list[int] | None = None,
                      localize=True, force=False, client=None) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with workspace_lock(out):
        return _translate_reading(pdf_path, out, pages, localize, force, client)


def _translate_reading(pdf_path, out, pages, localize, force, client):
    skill = load_skill("paper-translation")
    client = client or ResearchClient("translate")
    digest = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
    assets = out / "assets"
    assets.mkdir(exist_ok=True)
    records, sections, failures = [], [], []
    with fitz.open(pdf_path) as doc:
        selected = list(range(1, len(doc)+1)) if pages is None else sorted(set(pages))
        if not selected or any(type(p) is not int or not 1 <= p <= len(doc) for p in selected):
            raise ValueError("Select valid physical PDF page numbers")
        report = {"source_sha256": digest, "selected_pages": selected, "completed_pages": [],
                  "status": "running", "visual_review": "required", "figures": records, "failures": failures}
        write_json(out / "manifest.json", report)
        for n in selected:
            page = doc[n-1]
            original = page.get_text(sort=True)
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(1400/page.rect.width, 1400/page.rect.width))
                blocks = [{"bbox": list(b[:4]), "text": b[4]} for b in page.get_text("blocks") if b[6] == 0]
                context = doc[n-2].get_text()[-600:] if n > 1 else ""
                obj = client.json(skill, [{"type": "text", "text": f"Translate physical PDF page {n}. Source SHA256: {digest}. Page size: {page.rect.width} x {page.rect.height}. Text block coordinates are PDF points. Prior-page context (do not translate twice): {context}\nBlocks: {json.dumps(blocks, ensure_ascii=False)}"}, image_content(pix.tobytes("png"))], out / "cache" / f"page_{n}.json", force, validate=lambda data: validate_page(data, n))
                if obj.get("page") != n or not isinstance(obj.get("html"), str) or not obj["html"].strip():
                    raise ValueError("Missing page or translation content")
                replacements, page_records = {}, []
                for crop in obj.get("crops", []):
                    cid = crop.get("id", "")
                    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", cid) or cid in replacements:
                        raise ValueError("Invalid or duplicated asset ID")
                    if crop.get("kind") not in ("figure", "equation", "table_original"):
                        raise ValueError("Unknown crop kind")
                    box = validate_bbox(crop.get("bbox"))
                    clip = fitz.Rect(box[0]*page.rect.width/1000, box[1]*page.rect.height/1000, box[2]*page.rect.width/1000, box[3]*page.rect.height/1000)
                    stem = f"p{n:04}_{cid}"
                    crop_pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip)
                    png = crop_pix.tobytes("png")
                    (assets / f"{stem}.png").write_bytes(png)
                    # Export the original PDF region as SVG, preserving vectors
                    # when present; embedded raster images remain raster.
                    with fitz.open() as vector:
                        vp = vector.new_page(width=clip.width, height=clip.height)
                        vp.show_pdf_page(vp.rect, doc, n-1, clip=clip)
                        (assets / f"{stem}_original.svg").write_text(vp.get_svg_image(), encoding="utf-8")
                    record = {**crop, "page": n, "original": f"assets/{stem}.png", "original_svg": f"assets/{stem}_original.svg", "labels": [], "review_status": "pending"}
                    if localize and crop["kind"] == "figure":
                        try:
                            candidates = []
                            for block in page.get_text("dict", clip=clip)["blocks"]:
                                for line in block.get("lines", []):
                                    x0, y0, x1, y1 = line["bbox"]
                                    candidates.append({"text": "".join(span["text"] for span in line["spans"]), "bbox": [(x0-clip.x0)/clip.width*1000, (y0-clip.y0)/clip.height*1000, (x1-clip.x0)/clip.width*1000, (y1-clip.y0)/clip.height*1000], "direction": line.get("dir")})
                            label_data = client.json(skill + "\nThis request is FIGURE LOCALIZATION ONLY. Return the labels schema, not page HTML.",
                                [{"type": "text", "text": f"Localize labels in {crop.get('label', cid)}. Preserve scientific data. Use these precise PDF line candidates when possible; boxes are normalized to the crop: {json.dumps(candidates, ensure_ascii=False)}"}, image_content(png)], out / "cache" / f"{stem}_labels.json", force, validate=validate_labels)
                            record["labels"] = validate_labels(label_data)
                            record["warnings"] = label_data.get("warnings", [])
                            record["localized_svg"] = f"assets/{stem}_zh.svg"
                            (out / record["localized_svg"]).write_text(localized_svg(png, crop_pix.width, crop_pix.height, record["labels"]), encoding="utf-8")
                        except Exception as exc:
                            record["warnings"] = [f"Figure localization failed ({type(exc).__name__}); original retained"]
                            failures.append({"page": n, "asset": cid, "error": record["warnings"][0]})
                    display = record.get("localized_svg", record["original"])
                    replacements[cid] = f'<img src="{display}" alt="{html.escape(str(crop.get("label", cid)), quote=True)}"><small><a href="{record["original_svg"]}" download>原始 SVG</a>' + (f' · <a href="{display}" download>中文 SVG</a>' if record.get("localized_svg") else '') + '</small>'
                    page_records.append(record)
                content = sanitize_html(obj["html"], replacements)
                # A crop the model forgot to reference must still be available.
                for cid, fragment in replacements.items():
                    if not re.search(r'<asset\s+[^>]*id=[\"\x27]' + re.escape(cid) + r'[\"\x27]', obj["html"]):
                        content += '<figure>' + fragment + '</figure>'
                warnings = [str(w) for w in obj.get("warnings", [])]
                records.extend(page_records)
                report["completed_pages"].append(n)
                sections.append(f'<section id="page-{n}"><h2>PDF 第 {n} 页</h2>{content}<p class="warning">{html.escape("; ".join(warnings))}</p><details><summary>英文原文核对</summary><pre>{html.escape(original)}</pre></details></section>')
            except Exception as exc:
                failures.append({"page": n, "error": f"Page processing failed ({type(exc).__name__}); retry this page"})
                sections.append(f'<section><h2>PDF 第 {n} 页 · 翻译未完成</h2><pre>{html.escape(original)}</pre></section>')
            report["status"] = "partial" if failures else "running"
            write_json(out / "manifest.json", report)
            (out / "index.html").write_text(f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>中文阅读版</title><style>{STYLE}</style><main><h1>中文阅读版</h1><p>机器翻译校对稿 · 图内中文为覆盖文字层，需核对遮挡、术语与数据。范围：PDF 页 {html.escape(str(selected))}。</p>' + "".join(sections) + '</main></html>', encoding="utf-8")
        report["status"] = "partial" if failures else "complete"
        write_json(out / "manifest.json", report)
        return {**report, "html_path": str(out / "index.html"), "manifest_path": str(out / "manifest.json")}


def generate_notes(pdf_path: str, output_dir: str, force=False, client=None) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with workspace_lock(out):
        client = client or ResearchClient("paper")
        skill = load_skill("paper-reading")
        digest = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
        with fitz.open(pdf_path) as doc:
            pages = [p.get_text(sort=True) for p in doc]
        # Bounded chunks cover every page; no silent first-N-character cutoff.
        chunks, current, size = [], [], 0
        for n, text in enumerate(pages, 1):
            if current and size + len(text) > 24000:
                chunks.append(current)
                current, size = [], 0
            current.append({"page": n, "text": text})
            size += len(text)
        if current:
            chunks.append(current)
        if not any(t.strip() for t in pages):
            raise ValueError("No extractable text; run OCR before generating detailed notes")
        outputs = []
        for i, chunk in enumerate(chunks):
            outputs.append(client.json(skill + "\nAnalyze the supplied part faithfully. You have text only; flag all visual claims for review. Return the required reading JSON.",
                                       json.dumps({"source_sha256": digest, "pages": chunk}, ensure_ascii=False), out / "cache" / f"part_{i}.json", force, validate=lambda data: validate_note_part(data, [p["page"] for p in chunk])))
        sections, evidence, uncertainties = [], [], []
        for obj in outputs:
            for section in obj.get("sections", []):
                if not isinstance(section.get("text"), str) or not section["text"].strip():
                    raise ValueError("Invalid note section")
                if not section.get("pages") or any(type(n) is not int or not 1 <= n <= len(pages) for n in section["pages"]):
                    raise ValueError("Invalid note page citation")
                sections.append(section)
            for ev in obj.get("evidence", []):
                n, quote = ev.get("page"), ev.get("quote", "")
                norm = lambda t: re.sub(r"\s+", " ", t).strip()
                matched = type(n) is int and 1 <= n <= len(pages) and isinstance(quote, str) and bool(quote.strip()) and norm(quote) in norm(pages[n-1])
                evidence.append({**ev, "quote_found_on_page": bool(matched)})
            uncertainties.extend(str(v) for v in obj.get("uncertainties", []))
        if not sections or not evidence:
            raise ValueError("Detailed notes require sections and source evidence")
        overview = client.json(skill + "\nReturn JSON with summary only: a coherent whole-paper overview in Chinese, connecting motivation, mechanism, evidence and limitations. Use only the supplied part analyses; do not repeat them as a list.",
                               json.dumps({"source_sha256": digest, "part_summaries": [o.get("summary", "") for o in outputs], "section_map": [{"title": s.get("title"), "pages": s["pages"]} for s in sections]}, ensure_ascii=False), out / "cache" / "overview.json", force) if len(outputs) > 1 else outputs[0]
        report = {"source_sha256": digest, "pages_covered": list(range(1, len(pages)+1)),
                  "summary": str(overview.get("summary", "")), "sections": sections,
                  "evidence": evidence, "uncertainties": uncertainties, "status": "draft",
                  "visual_review": "not_performed", "evidence_check": "text_location_only"}
        write_json(out / "notes.json", report)
        text = "# 论文详细解读\n\n> AI 初稿；仅核对引文文字位置，未完成科学事实与图表审计。页码为 PDF 物理页。\n\n" + report["summary"]
        for s in sections:
            text += f'\n\n## {s.get("title", "解读")}\n\n{s["text"]}\n\nPDF 页：{s["pages"]}'
        text += "\n\n## 待核查\n\n" + "\n".join("- " + u for u in uncertainties)
        (out / "notes.md").write_text(text, encoding="utf-8")
        body = '<h1>论文详细解读</h1><p>AI 初稿；文字定位通过不等于科学结论核验通过。</p><p>' + html.escape(report['summary']).replace('\n', '<br>') + '</p>'
        for s in sections:
            body += f'<section><h2>{html.escape(str(s.get("title", "解读")))}</h2><p>{html.escape(s["text"]).replace(chr(10), "<br>")}</p><small>PDF 页 {s["pages"]}</small></section>'
        body += '<h2>证据定位</h2>' + ''.join(f'<p>{html.escape(str(e.get("claim", "")))} · PDF {e.get("page")} · {"文字匹配" if e["quote_found_on_page"] else "待核查"}<br><q>{html.escape(str(e.get("quote", "")))}</q></p>' for e in evidence)
        body += '<h2>待核查</h2>' + ''.join('<p>' + html.escape(u) + '</p>' for u in uncertainties)
        (out / "index.html").write_text(f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>详细解读</title><style>{STYLE}</style><main>{body}</main></html>', encoding="utf-8")
        return {**report, "notes_path": str(out / "notes.md"), "html_path": str(out / "index.html")}
