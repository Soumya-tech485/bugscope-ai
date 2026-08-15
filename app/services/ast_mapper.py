from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set

from app.services.repo_loader import IGNORED_DIRECTORIES


@dataclass
class CodeEntity:
    id: str
    file: str
    name: str
    kind: str
    start_line: int
    end_line: int
    doc: str
    code: str
    calls: Set[str] = field(default_factory=set)


@dataclass
class CodeMap:
    root: str
    files: List[str]
    entities: Dict[str, CodeEntity]

    def get_entity(self, entity_id: str) -> CodeEntity | None:
        return self.entities.get(entity_id)


def parse_repo(root: Path) -> CodeMap:
    entities: Dict[str, CodeEntity] = {}
    files: List[str] = []

    root = Path(root).resolve()

    for path in root.rglob("*.py"):
        if any(part in IGNORED_DIRECTORIES for part in path.parts):
            continue

        rel_path = str(path.relative_to(root))
        files.append(rel_path)

        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
            parsed_entities = parse_python_source(source, rel_path)

            for entity in parsed_entities:
                entities[entity.id] = entity
        except Exception:
            continue

    return CodeMap(root=str(root), files=files, entities=entities)


def parse_python_source(source: str, rel_path: str) -> List[CodeEntity]:
    tree = ast.parse(source)
    entities: List[CodeEntity] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack: List[str] = []
            self.class_stack: List[str] = []

        def qualified_name(self, name: str) -> str:
            return ".".join(self.stack + [name])

        def visit_ClassDef(self, node: ast.ClassDef):
            name = self.qualified_name(node.name)
            entity_id = f"{rel_path}::{node.lineno}:{name}"

            entities.append(
                CodeEntity(
                    id=entity_id,
                    file=rel_path,
                    name=name,
                    kind="class",
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                    doc=ast.get_docstring(node) or "",
                    code=ast.get_source_segment(source, node) or "",
                    calls=set(),
                )
            )

            self.stack.append(node.name)
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef):
            self._handle_function(node, "function")

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            self._handle_function(node, "async_function")

        def _handle_function(self, node, base_kind: str):
            kind = "method" if self.class_stack else base_kind
            name = self.qualified_name(node.name)
            entity_id = f"{rel_path}::{node.lineno}:{name}"

            calls: Set[str] = set()

            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        calls.add(child.func.id)
                    elif isinstance(child.func, ast.Attribute):
                        calls.add(child.func.attr)

            entities.append(
                CodeEntity(
                    id=entity_id,
                    file=rel_path,
                    name=name,
                    kind=kind,
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                    doc=ast.get_docstring(node) or "",
                    code=ast.get_source_segment(source, node) or "",
                    calls=calls,
                )
            )

            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

    Visitor().visit(tree)
    return entities
    