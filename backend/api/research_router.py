"""Optional research artifacts: restart-safe outputs and bounded background jobs."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Literal
import json
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.core.config import get_base_dir
from backend.services.research_workspace import generate_notes, translate_reading, write_json
from backend.services.skill_registry import list_skills

router = APIRouter(prefix="/api/research", tags=["research"])
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="research")
_ACTIVE = set()
_GUARD = Lock()


class ResearchRequest(BaseModel):
    kind: Literal["reading", "notes"]
    pages: list[int] | None = Field(default=None, max_length=1000)
    localize: bool = True
    force: bool = False


def paper_dir(book_name):
    root = (Path(get_base_dir()) / "data" / "papers").resolve()
    directory = (root / book_name).resolve()
    if directory.parent != root or not (directory / "raw" / f"{book_name}.pdf").is_file():
        raise HTTPException(404, "Paper not found")
    return directory


@router.get("/skills")
def api_skills():
    return {"skills": list_skills()}


@router.post("/{book_name}/jobs", status_code=202)
def start_job(book_name: str, request: ResearchRequest):
    directory = paper_dir(book_name)
    out = directory / "research" / request.kind
    state_file = out / "job.json"
    identity = str(out)
    with _GUARD:
        if identity in _ACTIVE:
            return json.loads(state_file.read_text(encoding="utf-8"))
        # Bound queued as well as running jobs.
        if len(_ACTIVE) >= 4:
            raise HTTPException(429, "Research queue full; retry after an active job finishes")
        _ACTIVE.add(identity)
        state = {"id": uuid.uuid4().hex, "kind": request.kind, "status": "queued"}
        try:
            write_json(state_file, state)
        except Exception:
            _ACTIVE.discard(identity)
            raise

    def run():
        try:
            state["status"] = "running"
            write_json(state_file, state)
            pdf = str(directory / "raw" / f"{book_name}.pdf")
            if request.kind == "reading":
                result = translate_reading(pdf, str(out), pages=request.pages, localize=request.localize, force=request.force)
            else:
                result = generate_notes(pdf, str(out), force=request.force)
            state.update(status=result["status"], file=f"{request.kind}/index.html")
        except Exception as exc:
            # Provider exceptions can contain request details; don't publish them.
            state.update(status="failed", error=f"{type(exc).__name__}: generation failed; check provider configuration and source pages")
        finally:
            write_json(state_file, state)
            with _GUARD:
                _ACTIVE.discard(identity)

    _POOL.submit(run)
    return dict(state)


@router.get("/{book_name}/jobs/{kind}")
def job_status(book_name: str, kind: Literal["reading", "notes"]):
    out = paper_dir(book_name) / "research" / kind
    state_file = out / "job.json"
    if not state_file.exists():
        return {"status": "not_started"}
    state = json.loads(state_file.read_text(encoding="utf-8"))
    with _GUARD:
        if state["status"] in ("queued", "running") and str(out) not in _ACTIVE:
            state["status"] = "interrupted"
    manifest = out / "manifest.json"
    if kind == "reading" and manifest.exists():
        report = json.loads(manifest.read_text(encoding="utf-8"))
        state["completed_pages"] = len(report.get("completed_pages", []))
        state["total_pages"] = len(report.get("selected_pages", []))
        state["failures"] = report.get("failures", [])
    return state


@router.get("/{book_name}/files/{filename:path}")
def research_file(book_name: str, filename: str):
    root = (paper_dir(book_name) / "research").resolve()
    target = (root / filename).resolve()
    if not target.is_relative_to(root) or not target.is_file() or target.suffix not in (".html", ".svg", ".png", ".json", ".md"):
        raise HTTPException(404, "Artifact not found")
    return FileResponse(target, headers={"Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox allow-downloads", "X-Content-Type-Options": "nosniff"})
