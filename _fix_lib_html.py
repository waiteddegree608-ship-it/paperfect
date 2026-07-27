from pathlib import Path
import re
p = Path(r"E:/workspace/paperfect/frontend/templates/library.html")
t = p.read_text(encoding="utf-8")
t = re.sub(
    r'<script[^>]*src="/static/js/library/main\.js[^"]*"[^>]*></script>',
    '<script src="/static/js/library/main.js?v=2026072702"></script>',
    t,
)
t = t.replace(
    """.main-view {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
        }""",
    """.main-view {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
            min-height: 0;
            box-sizing: border-box;
        }""",
)
p.write_text(t, encoding="utf-8")
for line in p.read_text(encoding="utf-8").splitlines():
    if "main.js" in line:
        print(line)
print("done")
