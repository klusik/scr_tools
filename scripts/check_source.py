# Project: SCR Tools
# Repository: SCR-Tools (local Git-ready source)
# File path: scripts/check_source.py
# Module Type: Static contributor verification
# Purpose: Check mechanically enforceable Python source standards.
# Responsibilities: Validate headers, docstrings, annotations and imports.
# Author: Rudolf Klusal
# License: MIT

"""Check source policy without importing Windows APIs or creating a GUI."""

import ast
import sys
from pathlib import Path


ROOT: Path = Path(__file__).resolve().parents[1]
HEADER_FIELDS: tuple[str, ...] = (
    "Project: SCR Tools", "Repository:", "File path:", "Module Type:",
    "Purpose:", "Responsibilities:", "Author: Rudolf Klusal", "License: MIT",
)
IGNORED_PARTS: frozenset[str] = frozenset(
    {".git", ".build", "build", "dist", "release", "__pycache__"}
)


def check_python_file(path: Path) -> list[str]:
    """Inspect one complete Python file for objective policy violations.

    Args:
        path (Path): Maintained Python source within the repository.

    Returns:
        list[str]: Human-readable errors, or an empty list on success.

    Raises:
        OSError: If the file cannot be read.
    """
    relative: str = path.relative_to(ROOT).as_posix()
    source: str = path.read_text("utf-8")
    errors: list[str] = []
    header: str = "\n".join(source.splitlines()[:15])
    for required in HEADER_FIELDS:
        if required not in header:
            errors.append(f"{relative}: missing header {required!r}")
    if f"File path: {relative}" not in header:
        errors.append(f"{relative}: header path does not match the file")
    try:
        tree: ast.Module = ast.parse(source, filename=relative)
    except SyntaxError as error:
        return errors + [f"{relative}: syntax error: {error.msg}"]
    for node in ast.walk(tree):
        prefix: str = f"{relative}:{getattr(node, 'lineno', 1)}"
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node) is None:
                errors.append(f"{prefix}: {node.name} lacks a docstring")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is None:
                errors.append(f"{prefix}: {node.name} lacks a return annotation")
            arguments: list[ast.arg] = [
                *node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs
            ]
            if node.args.vararg is not None:
                arguments.append(node.args.vararg)
            if node.args.kwarg is not None:
                arguments.append(node.args.kwarg)
            for argument in arguments:
                if argument.arg not in {"self", "cls"} and argument.annotation is None:
                    errors.append(
                        f"{prefix}: {node.name}.{argument.arg} lacks a type"
                    )
            for nested in ast.walk(node):
                if isinstance(nested, (ast.Import, ast.ImportFrom)):
                    errors.append(f"{prefix}: {node.name} contains an inner import")
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            errors.append(f"{prefix}: future imports are prohibited")
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            if any(alias.name == "Any" for alias in node.names):
                errors.append(f"{prefix}: uninformative Any import")
    return errors


def main() -> int:
    """Check maintained Python files and return an explicit process status.

    Returns:
        int: Zero when all static checks pass; one if any check fails.

    Raises:
        OSError: If source files cannot be enumerated or read.
    """
    sources: list[Path] = sorted(
        path for path in ROOT.rglob("*.py")
        if not IGNORED_PARTS.intersection(path.relative_to(ROOT).parts)
    )
    errors: list[str] = []
    for path in sources:
        errors.extend(check_python_file(path))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"Static source check failed: {len(errors)} issue(s).", file=sys.stderr)
        return 1
    print(f"Static source check passed for {len(sources)} Python files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
