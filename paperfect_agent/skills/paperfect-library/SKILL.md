---
name: paperfect-library
description: Manages Paperfect paper workspaces — ingest, list, metadata (venue, CCF/JCR, keywords), and library search. Use when organizing papers, looking up CCF rank, searching a local paper collection, or mapping book_name to titles.
---

# Paperfect library (headless)

This is the on-disk collection used by MCP, not the Electron UI. `book_name` is the folder id; `display_title` / `en_title` is what humans see.

## Inventory

- `list_papers` — every workspace under `PAPERFECT_WORK_DIR`.
- `search_library` — title, abstract, venue, keywords, CCF. Examples: `CCF A 视觉`, `survey transformer`.
- `analyze_metadata` — fill `metadata.json` if ingest skipped it. Safe to run without parse.

## Metadata fields (metadata.json)

`en_title`, `zh_title`, `authors`, `year`, `doi`, `venue`, `ccf_partition` (A/B/C), `jcr_partition`, `paper_type` (`研究` or `综述`), `abstract` (zh), `en_abstract`, `zh_keywords`, `en_keywords`, `research_field`, `research_direction`.

Venue matching uses local CCF/JCR tables in Paperfect. Weak venues like bare "arxiv" are enriched via Semantic Scholar / Crossref when an id exists.

## Other-project isolation

Set `PAPERFECT_WORK_DIR` to a folder **inside the client project** so papers do not land in the Paperfect desktop library. `PAPERFECT_ROOT` still points at the Paperfect code + `.env`.

## Naming

`book_name` is sanitized (no `<>:"/\|?*`, max length 72). Always pass `book_name` from `ingest_pdf` / `list_papers`, never a raw long PDF title, or tools will 404.
