"""Read source pages for narrative PPT planning; disclose all excerpt limits."""
import json
from pathlib import Path
import sys
import fitz


def prepare(pdf_path, output_path):
    with fitz.open(pdf_path) as doc:
        cap = max(400, min(5000, 90000 // max(1, len(doc))))
        pages = []
        for n, page in enumerate(doc, 1):
            text = page.get_text(sort=True)
            pages.append({"page": n, "text": text[:cap], "excerpt_truncated": len(text) > cap})
        result = {"page_count": len(doc), "pages": pages, "visual_review": "not_performed"}
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    prepare(sys.argv[1], sys.argv[2])
