---
name: paperfect-reading
description: Interprets Paperfect paper outputs — four-color annotations, KnowledgeBase.md, bilingual PDF, figure PPT with callouts, and slide-page mapping. Use when reading an already-processed paper, explaining highlights, or answering questions from a Paperfect workspace.
---

# Reading Paperfect outputs

Assume the paper was processed with Paperfect MCP (`book_name` known). Use artifacts; do not re-parse unless asked.

## What to open for which question

| User wants | Tool / file |
|---|---|
| Claims, methods, numbers, limitations | `ask_paper` or `read_artifact(kind="kb")` |
| Title / venue / CCF | `read_artifact(kind="metadata")` |
| Why a sentence is highlighted | `read_artifact(kind="annotations")` + original PDF |
| Figure explanation / talk slides | `pptx/...Full_Presentation.pptx` |
| Chinese layout clone of the paper | `translated/..._translated.pdf` |
| Body vs references cutoff | `read_artifact(kind="body")` |

Keep answers grounded in KB / annotations. If the KB does not contain it, say so.

## Four-color legend

Annotations are both burned into `{name}_annotated.pdf` and listed in `annotations.json`.

| Color | PDF appearance | Meaning |
|---|---|---|
| Yellow | highlight | Contribution / innovation |
| Red | squiggly underline | Limitation / prior-work gap |
| Blue | underline | Method, module, dataset, metric |
| Green | sticky note | Paragraph / page gist |

Each JSON item has `pageNumber`, `text` (verbatim English anchor), `type`, `note_content`, `rects` (percent of page). When explaining a highlight, quote `text` and paraphrase `note_content`.

## PPT

- Narrative slides explain the question, mechanism, evidence and limitations; figure slides add callouts. Speaker notes retain detailed explanations.
- `slide_sync_map.json`: `page_mapping[slideIndex] = pdfPage` (1-based).
- `ppt_status.complete=false` means narrative planning or some figure labels are incomplete; you may `generate_ppt` again to fill them.

## Q&A style

- Prefer `ask_paper` over dumping the whole KB into the chat.
- For long reports, page with `read_artifact(kind="kb", offset=..., max_chars=8000)`.
- Cite figure files as `images/Figure_N.png` when the answer is about a diagram.
