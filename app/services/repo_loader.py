import shutil
import uuid
import zipfile
from pathlib import Path

from fastapi import UploadFile

from app.config import WORKSPACE_DIR

IGNORED_DIRECTORIES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".next",
    ".pytest_cache",
    ".mypy_cache",
}


def create_project_from_zip(upload: UploadFile) -> str:
    project_id = uuid.uuid4().hex
    project_dir = WORKSPACE_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    tmp_zip = project_dir / "upload.zip"

    with tmp_zip.open("wb") as f:
        shutil.copyfileobj(upload.file, f)

    with zipfile.ZipFile(tmp_zip) as zf:
        project_root = str(project_dir.resolve())

        for member in zf.namelist():
            target_path = (project_dir / member).resolve()
            if not str(target_path).startswith(project_root):
                raise ValueError("Unsafe zip path detected")

        zf.extractall(project_dir)

    tmp_zip.unlink(missing_ok=True)
    return project_id


def project_path(project_id: str) -> Path:
    path = (WORKSPACE_DIR / project_id).resolve()

    if not str(path).startswith(str(WORKSPACE_DIR.resolve())):
        raise ValueError("Invalid project id")

    return path


def safe_join(root: Path, rel_path: str) -> Path:
    target = (root / rel_path).resolve()

    if not str(target).startswith(str(root.resolve())):
        raise ValueError("Invalid file path")

    return target
