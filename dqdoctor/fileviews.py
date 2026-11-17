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
    name = re.sub(r"[^A-Za-z0-9_]", "_", f.stem) or "dataset"
    if not _NAME_OK.match(name):
        name = "t_" + name.lstrip("0123456789_")
    if not _NAME_OK.match(name):
        name = "dataset"
    return name


def _path_literal(f: Path) -> str:
    """Escaped SQL string literal for a local, operator-selected file path."""
    return "'" + str(f.resolve()).replace("'", "''") + "'"


def register_file_views(con, files: list[Path]) -> list[str]:
    """Create one view per file; returns the view names."""
    names: list[str] = []
    for f in files:
        name = view_name_for(f)
        reader = READERS[f.suffix.lower()]
        escaped = _path_literal(f)
        con.execute(
            'CREATE VIEW "' + name + '" AS SELECT * FROM ' + reader + "(" + escaped + ")"
        )
        names.append(name)
    return names
