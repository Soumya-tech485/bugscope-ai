from __future__ import annotations

import shlex
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Dict, Tuple


def validate_python_file(path: Path) -> Tuple[bool, str]:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        compile(source, str(path), "exec")
        return True, ""
    except SyntaxError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)


def validate_python_code(code: str) -> Tuple[bool, str]:
    try:
        compile(textwrap.dedent(code or ""), "<patch>", "exec")
        return True, ""
    except SyntaxError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)


def run_tests(root: Path, command: str, timeout: int = 60) -> Dict[str, Any]:
    if not command.strip():
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": "No test command configured",
        }

    try:
        process = subprocess.run(
            shlex.split(command),
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return {
            "returncode": process.returncode,
            "stdout": process.stdout[-10000:],
            "stderr": process.stderr[-10000:],
        }
    except subprocess.TimeoutExpired:
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": "Test command timed out",
        }
    except Exception as exc:
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc),
        }