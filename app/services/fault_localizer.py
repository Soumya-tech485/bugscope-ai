from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

from app.services.ast_mapper import CodeMap


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "file",
    "line",
    "code",
    "function",
    "error",
    "when",
    "what",
    "please",
    "need",
    "should",
    "could",
    "would",
    "there",
    "where",
    "which",
    "while",
    "return",
    "returns",
    "def",
    "class",
    "self",
    "none",
    "true",
    "false",
}


@dataclass
class Suspect:
    id: str
    file: str
    name: str
    kind: str
    start_line: int
    end_line: int
    score: float
    reasons: List[str] = field(default_factory=list)
    code: str = ""
    root_cause: str = ""


def tokenize(text: str) -> List[str]:
    if not text:
        return []

    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.lower())
    return [token for token in tokens if len(token) > 2 and token not in STOPWORDS]


def parse_traceback(trace: str) -> List[Dict[str, str | int]]:
    pattern = r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>.+)'
    frames = []

    for match in re.finditer(pattern, trace or ""):
        frames.append(
            {
                "file": match.group("file"),
                "line": int(match.group("line")),
                "func": match.group("func").strip(),
            }
        )

    return frames


def localize(
    code_map: CodeMap,
    bug_report: str = "",
    error_trace: str = "",
    top_n: int = 8,
) -> List[Suspect]:
    scores: Dict[str, float] = {}
    reasons: Dict[str, List[str]] = {}

    entities = list(code_map.entities.values())

    if not entities:
        return []

    frames = parse_traceback(error_trace or "")
    bug_tokens = set(tokenize((bug_report or "") + "\n" + (error_trace or "")))

    error_lines = (error_trace or "").strip().splitlines()
    last_error_line = error_lines[-1].lower() if error_lines else ""
    exception_name = last_error_line.split(":")[0].strip() if last_error_line else ""

    def add_score(entity_id: str, points: float, reason: str):
        if points <= 0:
            return

        scores[entity_id] = scores.get(entity_id, 0.0) + float(points)
        reason_list = reasons.setdefault(entity_id, [])

        if reason and reason not in reason_list:
            reason_list.append(reason)

    # Keyword and exception-based scoring
    for entity in entities:
        haystack_tokens = set(tokenize(entity.name + " " + entity.doc))
        overlap = bug_tokens & haystack_tokens

        if overlap:
            sample = ", ".join(sorted(overlap)[:5])
            add_score(
                entity.id,
                min(40, 5 * len(overlap)),
                f"Keyword overlap: {sample}",
            )

        if exception_name and exception_name in entity.code.lower():
            add_score(
                entity.id,
                15,
                f"Exception-like text found: {exception_name}",
            )

    # Traceback-based scoring
    for frame in frames:
        frame_file = str(frame["file"]).replace("\\", "/")
        frame_file_name = frame_file.split("/")[-1]

        for entity in entities:
            entity_file = entity.file.replace("\\", "/")
            entity_file_name = entity_file.split("/")[-1]

            file_match = (
                frame_file.endswith(entity_file)
                or entity_file.endswith(frame_file)
                or frame_file_name == entity_file_name
            )

            if file_match:
                add_score(
                    entity.id,
                    50,
                    f"Traceback file matches: {frame_file}",
                )

                if entity.start_line <= int(frame["line"]) <= entity.end_line:
                    add_score(
                        entity.id,
                        80,
                        f"Traceback line {frame['line']} is inside {entity.name}",
                    )

                if frame["func"] and frame["func"] == entity.name.split(".")[-1]:
                    add_score(
                        entity.id,
                        70,
                        f"Traceback function matches: {frame['func']}",
                    )

    # Call-graph propagation
    name_index: Dict[str, List[str]] = {}

    for entity in entities:
        simple_name = entity.name.split(".")[-1].lower()
        name_index.setdefault(simple_name, []).append(entity.id)

    current_scores = dict(scores)

    for entity_id, score in current_scores.items():
        entity = code_map.entities.get(entity_id)

        if not entity:
            continue

        for called_name in entity.calls:
            callee_ids = name_index.get(called_name.lower(), [])

            for callee_id in callee_ids:
                if callee_id == entity_id:
                    continue

                add_score(
                    callee_id,
                    score * 0.25,
                    f"Called by suspicious function: {entity.name}",
                )

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)

    if not ranked:
        ranked = [(entity.id, 0.0) for entity in entities[:top_n]]

    suspects: List[Suspect] = []

    for entity_id, score in ranked[:top_n]:
        entity = code_map.entities[entity_id]

        suspects.append(
            Suspect(
                id=entity.id,
                file=entity.file,
                name=entity.name,
                kind=entity.kind,
                start_line=entity.start_line,
                end_line=entity.end_line,
                score=round(score, 2),
                reasons=reasons.get(entity_id, []),
                code=entity.code,
            )
        )

    return suspects