#!/usr/bin/env python3
# coding: utf-8
"""Paperfect MCP server (stdio).

Exposes the Paperfect academic-PDF pipeline as tools so other agents / IDEs
can ingest a paper, parse it, translate, annotate, generate PPT, and query
the knowledge base without the desktop UI.

Run:  python paperfect_agent/server.py
Env:  PAPERFECT_ROOT, PAPERFECT_WORK_DIR  (see README.md)
"""
from __future__ import annotations

import os
import sys

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from runtime import bootstrap, err  # noqa: E402

bootstrap()

try:
    try:
        from mcp.server.mcpserver import MCPServer as _MCP
    except ImportError:
        from mcp.server.fastmcp import FastMCP as _MCP
except ImportError:
    print(
        "Missing dependency: pip install mcp\n"
        "From this folder: python -m pip install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)

import stages  # noqa: E402
import workspace  # noqa: E402

_INSTRUCTIONS = (
    "Paperfect academic PDF tools. Always call health then get_artifacts "
    "before re-running a stage. ingest_pdf first. parse_paper is required "
    "before annotate_pdf / generate_ppt / ask_paper. Stages skip when "
    "artifacts already exist unless force=true. Long jobs (parse, "
    "translate, PPT) can take several minutes."
)
try:
    mcp = _MCP("paperfect", instructions=_INSTRUCTIONS)
except TypeError:
    mcp = _MCP("paperfect")


@mcp.tool()
def health() -> dict:
    """Check Paperfect root, API keys, Node.js, and PPT dependencies. Call this first in a new session."""
    try:
        return stages.health()
    except Exception as e:
        return err(str(e))


@mcp.tool()
def ingest_pdf(pdf_path: str, book_name: str = "") -> dict:
    """Copy a PDF into a Paperfect workspace and return book_name plus artifact paths. Use this before any processing stage. book_name is optional; a filesystem-safe stem is generated from the filename."""
    try:
        return workspace.ingest_pdf(pdf_path, book_name=book_name or None)
    except Exception as e:
        return err(str(e))


@mcp.tool()
def list_papers() -> dict:
    """List paper workspaces under PAPERFECT_WORK_DIR (or Paperfect data/papers). Returns titles and which artifacts exist."""
    try:
        return workspace.list_papers()
    except Exception as e:
        return err(str(e))


@mcp.tool()
def get_artifacts(book_name: str) -> dict:
    """Show which pipeline outputs exist for a paper (KB, translation, annotations, PPT, figures) and their paths. Call this before re-running a stage."""
    try:
        return workspace.get_artifacts(book_name)
    except Exception as e:
        return err(str(e))


@mcp.tool()
def read_artifact(book_name: str, kind: str = "kb", offset: int = 0, max_chars: int = 8000) -> dict:
    """Read a text artifact. kind is one of: kb, metadata, annotations, pipeline, body, sync_map. Use offset to page through long KnowledgeBase.md files."""
    try:
        p = workspace.resolve_paper(book_name)
    except Exception as e:
        return err(str(e))
    mapping = {
        "kb": p["kb_path"],
        "knowledge": p["kb_path"],
        "md": p["kb_path"],
        "metadata": p["metadata_json"],
        "annotations": p["annotations_json"],
        "pipeline": p["pipeline_json"],
        "body": p["body_info"],
        "sync_map": p["sync_map"],
        "upload_meta": p["upload_meta"],
        "reading_manifest": p["reading_manifest"],
        "notes": p["notes_md"],
        "notes_json": p["notes_json"],
    }
    path = mapping.get((kind or "kb").strip().lower())
    if not path:
        return err(f"Unknown kind {kind!r}", allowed=sorted(set(mapping)))
    return workspace.read_text_file(path, offset=offset, max_chars=max_chars)


@mcp.tool()
def detect_body_range(book_name: str) -> dict:
    """Detect where the paper body ends and references/appendix begin. Downstream parse/translate/annotate skip back-matter using this."""
    try:
        return stages.detect_body(book_name)
    except Exception as e:
        return err(str(e))


@mcp.tool()
def analyze_metadata(book_name: str, force: bool = False) -> dict:
    """Extract title, Chinese title, authors, year, venue, CCF/JCR rank, abstract, and keywords. Uses DOI/arXiv + Semantic Scholar when possible. Does not require parse_paper."""
    try:
        return stages.analyze_metadata(book_name, force=force)
    except Exception as e:
        return err(str(e))


@mcp.tool()
def extract_figures(book_name: str, force: bool = False) -> dict:
    """Crop Figure N panels from the PDF into images/Figure_N.png using caption-aware layout. parse_paper also does this in parallel."""
    try:
        return stages.extract_figures(book_name, force=force)
    except Exception as e:
        return err(str(e))


@mcp.tool()
def parse_paper(
    book_name: str,
    prompt_type: str = "提示词汇总",
    lang: str = "zh",
    force: bool = False,
) -> dict:
    """Deep-parse the paper into KnowledgeBase.md. Splits the selected prompt file on ### headings and answers each section in parallel. Required before annotate_pdf, generate_ppt, and ask_paper. prompt_type is a stem in backend/standalone_pdf2ppt/prompts/ (default 提示词汇总). lang is zh or en."""
    try:
        return stages.parse_paper(book_name, prompt_type=prompt_type, lang=lang, force=force)
    except Exception as e:
        return err(str(e))


@mcp.tool()
def translate_pdf(book_name: str, lang: str = "zh", force: bool = False) -> dict:
    """Produce a layout-preserving bilingual/Chinese PDF. Independent of parse. lang=en copies the original. Can take several minutes."""
    try:
        return stages.translate_pdf(book_name, lang=lang, force=force)
    except Exception as e:
        return err(str(e))


@mcp.tool()
def annotate_pdf(book_name: str, force: bool = False) -> dict:
    """Four-color semantic PDF annotations (yellow=contribution, red=limitation, blue=method/metric, green=summary). Requires KnowledgeBase.md from parse_paper."""
    try:
        return stages.annotate_pdf(book_name, force=force)
    except Exception as e:
        return err(str(e))


@mcp.tool()
def generate_ppt(
    book_name: str,
    mode: str = "creative",
    lang: str = "zh",
    force: bool = False,
) -> dict:
    """Build a callout-style PPTX from extracted figures plus KnowledgeBase.md. Requires parse_paper. Returns complete=false if some figure labels fell back. Needs Node.js and ppt_maker/node_modules. Can take several minutes."""
    try:
        return stages.generate_ppt(book_name, mode=mode, lang=lang, force=force)
    except Exception as e:
        return err(str(e))


@mcp.tool()
def run_pipeline(
    book_name: str,
    do_translate: bool = True,
    do_parse: bool = True,
    do_annotate: bool = True,
    do_ppt: bool = True,
    prompt_type: str = "提示词汇总",
    ppt_mode: str = "creative",
    lang: str = "zh",
    force: bool = False,
) -> dict:
    """Run the full Paperfect pipeline: metadata + (translate || parse) then (annotate || PPT). Skips stages that already have artifacts unless force=true. Prefer this when the user wants everything; use individual tools when they only want one stage."""
    try:
        return stages.run_pipeline(
            book_name,
            do_translate=do_translate,
            do_parse=do_parse,
            do_annotate=do_annotate,
            do_ppt=do_ppt,
            prompt_type=prompt_type,
            ppt_mode=ppt_mode,
            lang=lang,
            force=force,
        )
    except Exception as e:
        return err(str(e))


@mcp.tool()
def ask_paper(book_name: str, question: str, lang: str = "zh") -> dict:
    """Answer a question about one paper using keyword RAG over KnowledgeBase.md. Requires parse_paper. Use for methods, claims, numbers, limitations."""
    try:
        return stages.ask_paper(book_name, question, lang=lang)
    except Exception as e:
        return err(str(e))


@mcp.tool()
def search_library(query: str, lang: str = "zh", limit: int = 10) -> dict:
    """Search ingested papers by title, abstract, venue, keywords, CCF. Uses metadata.json in the work root (does not require the desktop UI)."""
    try:
        return stages.search_library(query, lang=lang, limit=limit)
    except Exception as e:
        return err(str(e))


@mcp.tool()
def list_prompts(lang: str = "zh") -> dict:
    """List available parse prompt templates (提示词汇总, 计算机+人工智能, 默认, ...). Pass the id as parse_paper prompt_type."""
    try:
        return stages.list_prompts(lang=lang)
    except Exception as e:
        return err(str(e))


@mcp.tool()
def list_skills() -> dict:
    """List repository-owned generation skills and their content hashes."""
    from backend.services.skill_registry import list_skills as catalog
    return {"ok": True, "skills": catalog()}


@mcp.tool()
def read_skill(name: str) -> dict:
    """Read paper-translation, paper-reading or paper-presentation instructions."""
    from backend.services.skill_registry import load_skill
    try:
        return {"ok": True, "name": name, "instructions": load_skill(name)}
    except (ValueError, OSError) as exc:
        return err(str(exc))


@mcp.tool()
def translate_reading(book_name: str, pages: list[int] | None = None, localize: bool = True, force: bool = False) -> dict:
    """Create Chinese HTML, editable tables and source/localized SVG assets. pages are physical PDF pages; None covers all pages. Requires a vision-capable translation model. Resumes fingerprinted page caches. Outputs require visual review."""
    from backend.services.research_workspace import translate_reading as generate
    try:
        p = workspace.resolve_paper(book_name)
        result = generate(p["pdf_path"], os.path.join(p["paper_dir"], "research", "reading"), pages=pages, localize=localize, force=force)
        return {"ok": True, **result}
    except Exception as exc:
        return err(f"{type(exc).__name__}: reading edition failed; check source and provider configuration")


@mcp.tool()
def generate_notes(book_name: str, force: bool = False) -> dict:
    """Generate detailed paper notes with physical page citations and exact-quote location checks. Covers all extracted pages in bounded chunks; text matching is not a scientific or visual audit."""
    from backend.services.research_workspace import generate_notes as generate
    try:
        p = workspace.resolve_paper(book_name)
        return {"ok": True, **generate(p["pdf_path"], os.path.join(p["paper_dir"], "research", "notes"), force=force)}
    except Exception as exc:
        return err(f"{type(exc).__name__}: detailed notes failed; check source and provider configuration")


@mcp.tool()
def pdf_tool(
    action: str,
    book_name: str = "",
    pdf_path: str = "",
    extra_pdf_paths: str = "",
    text: str = "",
    password: str = "",
    dpi: int = 300,
    fmt: str = "md",
    angle: int = 90,
    start: int = 1,
    end: int = 0,
    source: str = "raw",
    lang: str = "eng",
    opacity: float = 0.15,
) -> dict:
    """Deterministic PDF utilities (no LLM). action: export_images, export_figures, export_docx, export_text, ocr, rotate, split, merge, compress, watermark, protect, unlock. Provide book_name (preferred) or pdf_path. For merge, extra_pdf_paths is a semicolon-separated list of additional PDFs. source is raw, translated, or annotated."""
    extras = [x.strip() for x in (extra_pdf_paths or "").replace(",", ";").split(";") if x.strip()]
    try:
        return stages.pdf_tool(
            action=action,
            book_name=book_name,
            pdf_path=pdf_path,
            extra_pdf_paths=extras or None,
            text=text,
            password=password,
            dpi=dpi,
            fmt=fmt,
            angle=angle,
            start=start,
            end=(end or None),
            source=source,
            lang=lang,
            opacity=opacity,
        )
    except Exception as e:
        return err(str(e))


if __name__ == "__main__":
    mcp.run(transport="stdio")
