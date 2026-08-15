from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

from app.services.ast_mapper import CodeEntity
from app.services.llm_client import LLMClient


@dataclass
class FixResult:
    explanation: str
    replacement_code: str
    raw: str
    applied: bool = False
    validation: str = ""


SYSTEM_PROMPT = """
You are a precise senior software debugger.

Rules:
1. Return valid JSON only.
2. Do not return markdown.
3. Required keys: explanation, replacement_code.
4. replacement_code must completely replace the selected code section.
5. Preserve indentation and surrounding code contract.
6. Keep the fix minimal.
7. Do not hallucinate unrelated changes.
"""


def clean_code(code: str) -> str:
    if not code:
        return ""

    code = str(code)

    code = re.sub(
        r"^```(?:python)?\s*|\s*```$",
        "",
        code.strip(),
        flags=re.MULTILINE,
    )

    return code.strip()


def generate_fix(
    entity: CodeEntity,
    bug_report: str,
    error_trace: str,
    instructions: str,
    llm: LLMClient,
) -> FixResult:
    user_prompt = f"""
Bug context:
{bug_report or "No bug report provided."}

Error trace:
{error_trace or "No error trace provided."}

Additional instructions:
{instructions or "Fix the root cause."}

File:
{entity.file}

Selected code section lines {entity.start_line}-{entity.end_line}:

{entity.code}

Return JSON only:
{{"explanation": "...", "replacement_code": "..."}}
"""

    data = llm.chat_json(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        temperature=0.0,
        max_tokens=1600,
    )

    replacement_code = clean_code(
        data.get("replacement_code")
        or data.get("code")
        or data.get("raw")
        or ""
    )

    explanation = str(data.get("explanation", ""))

    return FixResult(
        explanation=explanation,
        replacement_code=replacement_code,
        raw=str(data),
    )


def ensure_indent(original_code: str, replacement_code: str) -> str:
    original_lines = original_code.splitlines()
    replacement_lines = replacement_code.splitlines()

    if not original_lines or not replacement_lines:
        return replacement_code

    original_indent = len(original_lines[0]) - len(original_lines[0].lstrip())
    replacement_indent = len(replacement_lines[0]) - len(replacement_lines[0].lstrip())

    diff = original_indent - replacement_indent

    if diff == 0:
        return replacement_code

    if diff > 0:
        return textwrap.indent(replacement_code, " " * diff)

    non_empty_indents = [
        len(line) - len(line.lstrip())
        for line in replacement_lines
        if line.strip()
    ]

    if not non_empty_indents:
        return replacement_code

    cut = min(abs(diff), min(non_empty_indents))

    return "\n".join(
        line[cut:] if line.strip() else line
        for line in replacement_lines
    )


def apply_fix(root: Path, entity: CodeEntity, replacement_code: str) -> None:
    path = (root / entity.file).resolve()

    if not str(path).startswith(str(root.resolve())):
        raise ValueError("Invalid file path")

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()

    replacement_code = ensure_indent(entity.code, replacement_code)
    replacement_lines = replacement_code.splitlines()

    start_index = max(0, entity.start_line - 1)
    end_index = min(entity.end_line, len(lines))

    new_lines = lines[:start_index] + replacement_lines + lines[end_index:]

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    