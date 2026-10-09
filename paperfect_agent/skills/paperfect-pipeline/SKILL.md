---
name: paperfect-pipeline
description: Runs the Paperfect academic-PDF pipeline via MCP — ingest, metadata, parse, translate, four-color annotate, PPT. Use when processing research papers, PDFs of papers, generating paper PPT, bilingual translation, KnowledgeBase.md, or when the user mentions Paperfect.
---

# Paperfect pipeline

Other projects do **not** reimplement parsing. Call the **paperfect** MCP tools. If tools are missing, tell the user to add the server (see the `paperfect_agent` README) and stop.

## First actions this session

1. `health` — confirm `has_api_key` and (if PPT is needed) `node_ok` + `ppt_node_modules`.
2. `ingest_pdf` with the PDF path → keep `book_name`.
3. `get_artifacts` — **never redo a stage whose artifact already exists** unless the user asked to regenerate (`force=true`).

## Stage graph

```
ingest_pdf
 ├─ analyze_metadata          (independent)
 ├─ translate_pdf             (independent; skip if lang=en)
 └─ parse_paper               (figures + KnowledgeBase.md)
      ├─ annotate_pdf         (needs KB)
      ├─ generate_ppt         (needs KB + Figure_N.png)
      └─ ask_paper            (needs KB)
```

Prefer `run_pipeline` when the user wants the full pack. Use single-stage tools when they only want translation, PPT, Q&A, etc.

`parse_paper` / `translate_pdf` / `generate_ppt` can take **several minutes**. Do not start a duplicate call; poll with `get_artifacts` if the client timed out.

## Defaults

| Param | Default | When to change |
|---|---|---|
| `prompt_type` | `提示词汇总` | CS/AI papers: `计算机+人工智能`. List via `list_prompts`. |
| `lang` | `zh` | English-only report/PPT: `en` |
| `ppt_mode` | `creative` | keep unless user asks otherwise |
| `force` | `false` | only when user wants a redo |

## Resume rules

| Artifact | Skip this tool |
|---|---|
| `parsed/{name}_KnowledgeBase.md` ≥ 200 bytes | `parse_paper` |
| `translated/{name}_translated.pdf` | `translate_pdf` |
| `marked/{name}_annotated.pdf` | `annotate_pdf` |
| `pptx/...pptx` **and** `ppt_status.complete` | `generate_ppt` |
| PPT exists but `complete=false` | call `generate_ppt` again (`force=false` retries unlabeled figures) |

## After success

- Return **paths**, not huge file dumps.
- To inspect the report: `read_artifact(kind="kb")` with `offset` paging (max ~8000 chars per call).
- Questions about the paper: `ask_paper`, not a generic web search.
- Layout / export / OCR: `pdf_tool` (no LLM).

## Do not

- Do not invent a second PDF pipeline (pymupdf + your own prompts) while Paperfect MCP is available.
- Do not call `annotate_pdf` or `generate_ppt` before KB exists.
- Do not put API keys in chat; they live in Paperfect `.env`.

## More

- Artifact folder contract: [artifacts.md](artifacts.md)
- MCP tool cheat sheet: [tools.md](tools.md)
- Prompt templates: skill `paperfect-prompts`
- How to read four-color marks / PPT: skill `paperfect-reading`
