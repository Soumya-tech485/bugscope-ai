from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import models
from app.config import TEST_COMMAND
from app.services import (
    ast_mapper,
    fault_localizer,
    fixer,
    llm_client,
    repo_loader,
    validator,
)

app = FastAPI(title="BugScope AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def home():
    return FileResponse(static_dir / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/projects/upload")
async def upload_project(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload a .zip file")

    try:
        project_id = repo_loader.create_project_from_zip(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"project_id": project_id}


@app.post("/api/projects/analyze")
def analyze_project(req: models.AnalyzeRequest):
    root = repo_loader.project_path(req.project_id)
    code_map = ast_mapper.parse_repo(root)

    if not code_map.entities:
        return {
            "project_id": req.project_id,
            "suspects": [],
            "message": "No Python functions or classes found.",
        }

    suspects = fault_localizer.localize(
        code_map=code_map,
        bug_report=req.bug_report,
        error_trace=req.error_trace,
        top_n=req.top_n,
    )

    llm = llm_client.LLMClient()

    if llm.enabled and suspects:
        top = suspects[0]

        system = (
            "You are an expert root-cause analyzer. "
            "Return JSON only with keys: root_cause, confidence, fix_plan."
        )

        user = f"""
Bug report:
{req.bug_report}

Error trace:
{req.error_trace}

Top suspect:
File: {top.file}
Function: {top.name}
Lines: {top.start_line}-{top.end_line}

Code:
{top.code[:8000]}
"""

        try:
            data = llm.chat_json(system, user, temperature=0.0, max_tokens=700)
            top.root_cause = str(data.get("root_cause", data))
        except Exception as exc:
            top.root_cause = f"LLM error: {exc}"

    return {
        "project_id": req.project_id,
        "suspects": [asdict(suspect) for suspect in suspects],
    }


@app.post("/api/projects/fix")
def fix_suspect(req: models.FixRequest):
    root = repo_loader.project_path(req.project_id)
    code_map = ast_mapper.parse_repo(root)

    entity = code_map.get_entity(req.suspect_id)

    if not entity:
        raise HTTPException(
            status_code=404,
            detail="Suspect not found. Re-analyze after file changes.",
        )

    llm = llm_client.LLMClient()

    try:
        result = fixer.generate_fix(
            entity=entity,
            bug_report=req.instructions,
            error_trace="",
            instructions=req.instructions,
            llm=llm,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Fix generation failed: {exc}")

    if not result.replacement_code.strip():
        raise HTTPException(
            status_code=500,
            detail="LLM did not return replacement_code.",
        )

    if req.apply_fix:
        fixer.apply_fix(root, entity, result.replacement_code)

        ok, err = validator.validate_python_file(root / entity.file)

        result.applied = True
        result.validation = "Syntax OK" if ok else f"Syntax error after patch: {err}"
    else:
        preview_code = fixer.ensure_indent(entity.code, result.replacement_code)
        ok, err = validator.validate_python_code(preview_code)

        result.validation = "Syntax OK" if ok else f"Preview syntax error: {err}"

    return asdict(result)


@app.get("/api/projects/{project_id}/file")
def read_project_file(project_id: str, path: str = Query(...)):
    root = repo_loader.project_path(project_id)

    try:
        target = repo_loader.safe_join(root, path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return {
        "path": path,
        "content": target.read_text(encoding="utf-8", errors="ignore"),
    }


@app.put("/api/projects/{project_id}/file")
def write_project_file(project_id: str, payload: models.FileContent):
    root = repo_loader.project_path(project_id)

    try:
        target = repo_loader.safe_join(root, payload.path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")

    response = {
        "path": payload.path,
        "saved": True,
    }

    if payload.path.endswith(".py"):
        ok, err = validator.validate_python_file(target)
        response["syntax_ok"] = ok
        response["error"] = err

    return response


@app.post("/api/projects/{project_id}/run-tests")
def run_project_tests(project_id: str):
    root = repo_loader.project_path(project_id)
    return validator.run_tests(root, TEST_COMMAND)