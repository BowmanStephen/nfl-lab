"""Atomic JSON writes and a pre-commit check for the files the routines publish.

A scheduled run can die mid-write (timeout, cancel, runner loss). Writing to a
temp file in the same directory and renaming it means a reader, or the commit
step, sees either the old file or the new one, never half of one.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: Path, obj, **dump_kwargs) -> None:
    dump_kwargs.setdefault("indent", 2)
    # Serialize first: a value that cannot be encoded fails before the file is touched.
    atomic_write_text(path, json.dumps(obj, **dump_kwargs) + "\n")


def validate_json_tree(*roots: Path) -> list[str]:
    """Return one problem per unreadable JSON file or leftover temp file under ``roots``."""
    problems: list[str] = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.name.startswith(".") and path.name.endswith(".tmp"):
                problems.append(f"{path}: leftover temp file from an interrupted write")
                continue
            if path.suffix != ".json":
                continue
            try:
                obj = json.loads(path.read_text())
            except (OSError, ValueError) as exc:
                problems.append(f"{path}: not valid JSON ({exc})")
                continue
            if obj in (None, {}, []):
                problems.append(f"{path}: empty JSON")
    return problems


def main(argv: list[str] | None = None) -> int:
    import sys
    roots = [Path(p) for p in (argv if argv is not None else sys.argv[1:])] or [Path("public/api"), Path("output/live")]
    problems = validate_json_tree(*roots)
    for p in problems:
        print(f"INVALID: {p}", file=sys.stderr)
    if not problems:
        print(f"ok: JSON under {', '.join(map(str, roots))} parses")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
