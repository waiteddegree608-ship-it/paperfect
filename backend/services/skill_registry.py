"""Versioned, repository-owned skills shared by desktop pipelines and MCP."""
import hashlib
import re
from pathlib import Path
from backend.core.config import get_base_dir

SKILL_ROOT = Path(get_base_dir()) / "backend" / "skills"


def load_skill(name: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name):
        raise ValueError("Invalid skill name")
    text = (SKILL_ROOT / name / "SKILL.md").read_text(encoding="utf-8-sig")
    return text.split("---", 2)[-1].strip() if text.startswith("---") else text


def list_skills() -> list:
    return [{"name": p.parent.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(SKILL_ROOT.glob("*/SKILL.md"))]
