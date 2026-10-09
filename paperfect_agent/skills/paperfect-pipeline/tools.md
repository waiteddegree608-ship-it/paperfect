# MCP tools

Server name: **paperfect**. All tools return `{ ok, error?, ... }`.

| Tool | Role |
|---|---|
| `health` | Root, API key, Node, ppt `node_modules` |
| `ingest_pdf` | Copy PDF → workspace, return `book_name` |
| `list_papers` | Workspaces in the work root |
| `get_artifacts` | Flags + paths for one paper |
| `read_artifact` | `kind`: kb / metadata / annotations / pipeline / body / sync_map |
| `detect_body_range` | Body vs references pages |
| `analyze_metadata` | Title, venue, CCF/JCR, abstract, keywords |
| `extract_figures` | `Figure_N.png` crops |
| `parse_paper` | KnowledgeBase.md (needs prompt_type, lang) |
| `translate_pdf` | Layout-preserving translation |
| `annotate_pdf` | Four-color annotated PDF + annotations.json |
| `generate_ppt` | PPTX + slide_sync_map.json |
| `run_pipeline` | Full graph with flags |
| `ask_paper` | RAG Q&A on one KB |
| `search_library` | Search ingested metadata |
| `list_prompts` | Parse template ids |
| `pdf_tool` | Deterministic PDF ops (`action=`) |

`pdf_tool` actions: `export_images`, `export_figures`, `export_docx`, `export_text`, `ocr`, `rotate`, `split`, `merge`, `compress`, `watermark`, `protect`, `unlock`.

`merge`: `extra_pdf_paths` is a semicolon-separated list.

Typical calls:

```
ingest_pdf(pdf_path="D:/papers/foo.pdf")
run_pipeline(book_name="<from ingest>", lang="zh", prompt_type="提示词汇总")
ask_paper(book_name="...", question="这篇的核心贡献是什么？")
```
