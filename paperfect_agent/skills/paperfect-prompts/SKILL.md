---
name: paperfect-prompts
description: Chooses Paperfect parse prompt templates (提示词汇总, 计算机+人工智能, 默认) and explains ### section splitting. Use when selecting prompt_type for parse_paper, customizing academic analysis sections, or generating a Chinese vs English KnowledgeBase.
---

# Parse prompts

`parse_paper(prompt_type=..., lang=zh|en)` loads `backend/standalone_pdf2ppt/prompts/{id}.md` (or `_{lang}.md`). The file is split on `###` headings; **each section is one parallel LLM job**. Keep sections focused; do not paste a novel into one heading.

Call `list_prompts` to see ids installed on this machine.

## Built-in ids

| `prompt_type` | Use when |
|---|---|
| `提示词汇总` | Default: contribution, method, results, limitations (4 jobs) |
| `计算机+人工智能` | CS/AI: problem framing, sequential reading, stitching-modules / ablation check, architecture-figure explanation |
| `默认` | Short two-section overview + sequential walkthrough |

Full text of shipped templates: [catalog.md](catalog.md).

## lang

- `zh` (default): KnowledgeBase, PPT labels, annotation notes in Chinese.
- `en`: English report and PPT. `translate_pdf` then just copies the original PDF.

## Custom templates (maintainers)

Add `{Name}.md` next to the shipped prompts. Structure:

```markdown
## Name shown in UI
### Section title
What this job must extract...
### Next section
...
```

The first `##` line is the display name. Jobs ignore a section titled `提示词汇总` / `Prompt summary`. After adding a file, `list_prompts` will show it; pass the filename stem as `prompt_type`.
