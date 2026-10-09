from pathlib import Path

p = Path(__file__).resolve().parents[1] / "backend" / "services" / "file_manager.py"
lines = p.read_text(encoding="utf-8").splitlines(True)
out = []
i = 0
changed = 0
while i < len(lines):
    stripped = lines[i].strip()
    if (
        stripped == "if os.path.exists(pptx_path):"
        and i + 1 < len(lines)
        and 'status = "ready"' in lines[i + 1]
    ):
        indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
        out.append(indent + "pptx_ok = os.path.exists(pptx_path) and os.path.getsize(pptx_path) >= 8000\n")
        out.append(indent + "if pptx_ok:\n")
        changed += 1
        i += 1
        continue
    out.append(lines[i])
    i += 1

p.write_text("".join(out), encoding="utf-8")
print(f"changed {changed} blocks in {p}")
