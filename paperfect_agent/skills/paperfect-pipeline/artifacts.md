# Artifact layout

Every paper is a folder named `book_name` (filesystem-safe, ≤72 chars). Display titles can be longer; always pass `book_name` to tools.

```
{PAPERFECT_WORK_DIR or PAPERFECT_ROOT/data/papers}/{book_name}/
├── raw/{book_name}.pdf
├── parsed/{book_name}_KnowledgeBase.md
├── parsed/body_info.json
├── translated/{book_name}_translated.pdf
├── marked/{book_name}_annotated.pdf
├── marked/annotations.json
├── images/Figure_N.png
├── images/figures_metadata.json          # { "Figure_1.png": pageNumber }
├── pptx/{book_name}_Full_Presentation.pptx
├── pptx/slide_sync_map.json
├── pptx/ppt_status.json                  # { complete, fallback_figures }
├── pptx/ppt_cache_zh.json | ppt_cache_en.json
├── metadata.json                         # analyzer output
├── pipeline.json                         # which stages were requested
├── upload_meta.json
├── cache/progress_*.json
└── exports/                              # pdf_tool outputs
```

Env:

- `PAPERFECT_ROOT` — Paperfect checkout (contains `backend/`).
- `PAPERFECT_WORK_DIR` — where *this* project stores workspaces. If unset, files go into Paperfect's own `data/papers` library.

`get_artifacts` is the source of truth for what exists.
