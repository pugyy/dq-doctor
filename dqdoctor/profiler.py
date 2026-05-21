from __future__ import annotations

from pathlib import Path

from dqdoctor.connectors.auto import ConnectionWrapper, get_connection, get_table_columns
from dqdoctor.models import ColumnProfile, ProfileResult

_SEMANTIC_PATTERNS: dict[str, list[str]] = {
    "identifier": ["id"],
    "measure": [
        "price", "amount", "cost", "total",
        "fee", "salary", "revenue", "qty", "quantity",
    ],
    "category": [
        "status", "type", "category", "method",
        "level", "grade", "class", "region", "gender",
    ],
    "timestamp": [
        "time", "date", "created_at", "updated_at",
        "deleted_at", "event_time", "order_time",
    ],
}


def infer_semantic_type(column_name: str) -> str:
    lower = column_name.lower()
    for sem_type, patterns in _SEMANTIC_PATTERNS.items():
        for pattern in patterns:
            if pattern in lower:
                return sem_type
    return "unknown"


_NUMERIC_TYPES = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT",
    "FLOAT", "DOUBLE", "DECIMAL", "HUGEINT",
}

_TEMPORAL_TYPES = {
    "TIMESTAMP", "TIMESTAMPTZ", "DATE", "TIME", "TIMESTAMP_NS",
    "TIMESTAMP WITH TIME ZONE", "TIMESTAMP WITHOUT TIME ZONE",
}


def _is_numeric(dtype: str) -> bool:
    upper = dtype.upper()
    return upper in _NUMERIC_TYPES or upper.startswith("DECIMAL")


def _is_temporal(dtype: str) -> bool:
    return dtype.upper() in _TEMPORAL_TYPES


def _fetch_min_max(
    con: ConnectionWrapper, table: str, col: str, dtype: str,
) -> tuple:
    row = con.fetchone(
        f"SELECT MIN({con.quote(col)}), MAX({con.quote(col)}) "
        f"FROM {table} WHERE {con.quote(col)} IS NOT NULL"
    )
    if row is None or row[0] is None:
        return None, None
    if _is_temporal(dtype):
        return str(row[0]), str(row[1])
    return row[0], row[1]


def profile_column(
    con: ConnectionWrapper, table: str, col: dict, row_count: int,
) -> ColumnProfile:
    name = col["name"]
    dtype = col["dtype"]
    qcol = con.quote(name)

    null_count = con.fetchone(
        f"SELECT COUNT(*) FROM {table} WHERE {qcol} IS NULL"
    )[0]
    null_rate = round(null_count / row_count, 4) if row_count > 0 else 0.0

    distinct_count = con.fetchone(
        f"SELECT COUNT(DISTINCT {qcol}) FROM {table}"
    )[0]
    distinct_rate = round(distinct_count / row_count, 4) if row_count > 0 else 0.0

    min_value = None
    max_value = None
    if _is_numeric(dtype) or _is_temporal(dtype):
        min_value, max_value = _fetch_min_max(con, table, name, dtype)
    elif dtype.upper() in ("VARCHAR", "TEXT", "STRING", "BLOB"):
        min_value, max_value = _fetch_min_max(con, table, name, dtype)

    sample_rows = con.fetchall(
        f"SELECT DISTINCT {qcol} FROM {table} "
        f"WHERE {qcol} IS NOT NULL LIMIT 10"
    )
    sample_values = [r[0] for r in sample_rows]
    if _is_temporal(dtype):
        sample_values = [str(v) for v in sample_values]

    distinct_values: list = []
    if distinct_count <= 20:
        dv_rows = con.fetchall(
            f"SELECT DISTINCT {qcol} FROM {table} "
            f"WHERE {qcol} IS NOT NULL ORDER BY {qcol}"
        )
        distinct_values = [r[0] for r in dv_rows]
        if _is_temporal(dtype):
            distinct_values = [str(v) for v in distinct_values]

    semantic = infer_semantic_type(name)

    return ColumnProfile(
        name=name,
        dtype=dtype,
        null_count=null_count,
        null_rate=null_rate,
        distinct_count=distinct_count,
        distinct_rate=distinct_rate,
        min_value=min_value,
        max_value=max_value,
        sample_values=sample_values,
        distinct_values=distinct_values,
        inferred_semantic_type=semantic,
    )


def profile_table(db_path: "str | Path", table_name: str) -> ProfileResult:
    con = get_connection(str(db_path))
    try:
        qt = con.quote(table_name)
        row_count = con.fetchone(f"SELECT COUNT(*) FROM {qt}")[0]
        columns_meta = get_table_columns(con, table_name)
        columns = [
            profile_column(con, qt, col, row_count) for col in columns_meta
        ]
        return ProfileResult(
            db_path=str(db_path),
            table_name=table_name,
            row_count=row_count,
            columns=columns,
        )
    finally:
        con.close()
