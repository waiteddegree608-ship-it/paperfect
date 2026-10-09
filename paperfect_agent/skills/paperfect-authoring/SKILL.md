---
name: paperfect-authoring
description: Create source-grounded Chinese reading editions, translated figure SVG assets, detailed paper explanations and academic presentations through Paperfect MCP.
---

Use Paperfect MCP for a requested translation, paper explanation or presentation. Call health, then ingest_pdf if needed and get_artifacts before generating. Keep the user's scope: selected physical PDF pages for a reading edition, or the full paper when requested. Existing generated files do not prove they have been scientifically reviewed.

- Read `read_skill("paper-translation")` before `translate_reading`. Set `localize=true` for Chinese figure labels. The result includes HTML, editable tables, original SVG exports and localized SVG overlays. Check manifest failures and warnings. A raster image with SVG labels is not a completely vectorized diagram.
- Read `read_skill("paper-reading")` before `generate_notes`. Inspect `read_artifact(kind="notes_json")`: each claim needs a page and an exact source quote. Matching quote text only checks location. Disclose absent visual inspection and uncertain evidence.
- Read `read_skill("paper-presentation")` before preparing slides. Run parse_paper if the knowledge base is absent. Generate the reading edition first when translated figures are wanted, then generate_ppt. The deck combines narrative explanation, figure callouts and detailed notes; localized labels are editable PowerPoint objects. For an existing PPT that predates the localized figures, request a deliberate regeneration with force=true.

Long jobs consume the configured provider's API quota. Reuse fingerprinted caches after interruption; force=true requests fresh model calls. Return artifact paths and generation/review status, and surface partial failures rather than claiming completion. Read source pages to resolve uncertainties before upgrading a machine-generated draft to a verified interpretation.
