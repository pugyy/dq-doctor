"""Register local files as DuckDB views (the ``files`` datasource backend).

DuckDB DDL statements cannot take bound parameters, so registering a file
view is the one place in dq-doctor where a value (the file path) is rendered
into SQL text. The DDL is assembled from exactly three controlled pieces:

1. a view name derived from the file stem, restricted to
   ``[A-Za-z0-9_]`` and quoted;
2. a reader function chosen from the fixed allowlist ``READERS`` by the
   file extension;
3. a local, operator-selected, existence-checked path with every single
   quote doubled (``_path_literal``).

No other text varies, and no other module renders values into SQL text.
"""
from __future__ import annotations

import re
from pathlib import Path

READERS = {
    ".csv": "read_csv_auto",
    ".tsv": "read_csv_auto",
    ".parquet": "read_parquet",
    ".pq": "read_parquet",
    ".json": "read_json_auto",
    ".jsonl": "read_json_auto",
    ".ndjson": "read_json_auto",
}

_NAME_OK = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def view_name_for(f: Path) -> str:
    """View name for a file.

    ``users.csv`` and ``users.parquet`` both sanitize to ``users``; the
    extension is appended when the stem alone would be ambiguous, so a
    directory source with the same dataset in two formats keeps working
    (``users_csv`` / ``users_parquet``) instead of failing on a duplicate
    CREATE VIEW.
    """
    stem = re.sub(r"[^A-Za-z0-9_]", "_", f.stem) or "dataset"
    suffix = re.sub(r"[^A-Za-z0-9_]", "", f.suffix.lower().lstrip("."))
    name = stem
    if suffix and suffix not in ("csv", "parquet", "json", "jsonl"):
        name = stem + "_" + suffix
    if not _NAME_OK.match(name):
        name = "t_" + name.lstrip("0123456789_")
    if not _NAME_OK.match(name):
        name = "dataset"
    return name


def unique_view_name(f: Path, taken: set[str]) -> str:
    """Collision-free view name for a file given the names already used."""
    base = view_name_for(f)
    if base not in taken:
        return base
    suffix = re.sub(r"[^A-Za-z0-9_]", "", f.suffix.lower().lstrip(".")) or "file"
    candidate = base + "_" + suffix
    if candidate not in taken:
        return candidate
    index = 2
    while f"{candidate}{index}" in taken:
        index += 1
    return f"{candidate}{index}"


def _path_literal(f: Path) -> str:
    """Escaped SQL string literal for a local, operator-selected file path."""
    return "'" + str(f.resolve()).replace("'", "''") + "'"


def register_file_views(con, files: list[Path]) -> list[str]:
    """Create one view per file; returns the view names actually used."""
    names: list[str] = []
    taken: set[str] = set()
    for f in files:
        name = unique_view_name(f, taken)
        taken.add(name)
        reader = READERS[f.suffix.lower()]
        escaped = _path_literal(f)
        con.execute(
            'CREATE VIEW "' + name + '" AS SELECT * FROM ' + reader + "(" + escaped + ")"
        )
        names.append(name)
    return names
