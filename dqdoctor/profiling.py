"""Table profiling: orchestration over the batched aggregate SQL.

The heavy lifting lives in ``dqdoctor.aggregates`` (2-3 queries per table
regardless of column count). This module maps aggregate results onto the
``TableProfile`` model, attaches sampling info, semantic guesses and PII
evidence.
"""
from __future__ import annotations

from typing import Optional

from dqdoctor import aggregates, samples
from dqdoctor.models import ColumnProfile, SamplingInfo, TableProfile
from dqdoctor.pii import detect_pii
from dqdoctor.scanref import full_scan, sampled_scan
from dqdoctor.queries import table_columns

_NUMERIC_PREFIXES = (
    "int", "bigint", "smallint", "tinyint", "numeric", "decimal",
    "float", "double", "real", "hugeint", "uint",
)
_NUMERIC_EXACT = {"money"}
_TEMPORAL = ("timestamp", "date")
_TEXTISH = ("varchar", "char", "text", "string", "bpchar", "enum")


def is_numeric(dtype: str) -> bool:
    base = dtype.strip().lower().split("(")[0].split(" ")[0]
    return base in _NUMERIC_EXACT or any(base.startswith(p) for p in _NUMERIC_PREFIXES)


def is_temporal(dtype: str) -> bool:
    d = dtype.strip().lower()
    return d.startswith("timestamp") or d == "date"


def _is_text(dtype: str) -> bool:
    """Text-ish columns are the only ones that can carry PII evidence."""
    d = dtype.strip().lower()
    return any(d.startswith(p) for p in _TEXTISH)


_SEMANTIC_PATTERNS: list[tuple[str, list[str]]] = [
    ("identifier", ["id"]),
    ("measure", ["price", "amount", "cost", "total", "fee", "salary", "revenue",
                 "qty", "quantity"]),
    ("category", ["status", "type", "category", "method", "level", "grade",
                  "class", "region", "gender", "channel"]),
    ("event_time", ["created_at", "updated_at", "deleted_at", "event_time",
                    "order_time", "occurred_at"]),
    ("birthdate", ["birth", "birthday", "dob"]),
]


def infer_semantic_type(column_name: str, dtype: str) -> str:
    """Semantic guess combining name and physical type.

    ``event_time`` requires an actual TIMESTAMP/DATE dtype - a VARCHAR or
    INTEGER column merely named ``*_time*`` is not freshness material
    (0.7 crash). ``birthdate`` outranks generic time words so birth dates
    never become freshness checks.
    """
    lower = column_name.lower()
    for sem, patterns in _SEMANTIC_PATTERNS:
        for pattern in patterns:
            if pattern not in lower:
                continue
            if sem == "event_time" and not is_temporal(dtype):
                continue
            return sem
    if is_temporal(dtype) and any(w in lower for w in ("time", "date", "at")):
        return "event_time"
    return "unknown"


def profile_table(
    con,
    display: str,
    table: str,
    sample_rows: Optional[int] = None,
) -> TableProfile:
    """Profile one table on an open connection (2-3 queries + low-card extras)."""
    columns = table_columns(con, table)
    qt = con.table_ref(table)

    sampled = sample_rows is not None and sample_rows > 0
    if sampled:
        scan = sampled_scan(con, qt, sample_rows)
        full_rows = aggregates.count_scan(con, full_scan(qt))
        scan_rows = aggregates.count_scan(con, scan)
    else:
        scan = full_scan(qt)
        full_rows = None
        scan_rows = None

    quoted = []
    for col in columns:
        qc = con.quote_identifier(col["name"])
        want_mm = (
            is_numeric(col["dtype"])
            or is_temporal(col["dtype"])
            or col["dtype"].strip().lower().startswith(_TEXTISH)
        )
        quoted.append((col["name"], qc, want_mm))

    row_count, stats = aggregates.aggregate(con, scan, quoted)
    sampling = SamplingInfo(
        method="sample" if sampled else "full",
        sample_size=scan_rows if scan_rows is not None else row_count,
        row_count=full_rows if full_rows is not None else row_count,
    )

    # Distinct value lists are only fetched where they carry information:
    # categorical columns (enumeration drives accepted_values suggestions)
    # and text columns (PII evidence). Numeric/id columns keep just the
    # counts from the aggregate, so the query count stays flat with width.
    enum_cols = []
    for name, qc, _mm in quoted:
        col_meta = next(c for c in columns if c["name"] == name)
        sem = infer_semantic_type(name, col_meta["dtype"])
        if 0 < stats[name]["distinct"] <= 20 and (sem == "category" or _is_text(col_meta["dtype"])):
            enum_cols.append((name, qc))
    low_card = {} if sampled else aggregates.low_cardinality_values(con, qt, enum_cols)

    profiles: list[ColumnProfile] = []
    pii_evidence: dict[str, object] = {}
    for col in columns:
        name = col["name"]
        s = stats[name]
        distinct_values = low_card.get(name, [])
        sample_vals = distinct_values[:10]
        if not sample_vals and _is_text(col["dtype"]):
            sample_vals = samples.sample_values(con, scan, con.quote_identifier(name))
        evidence = detect_pii(name, sample_vals)
        profiles.append(
            ColumnProfile(
                name=name,
                dtype=col["dtype"],
                null_count=row_count - s["nonnull"],
                null_rate=round((row_count - s["nonnull"]) / row_count, 4)
                if row_count
                else 0.0,
                distinct_count=s["distinct"],
                distinct_rate=round(s["distinct"] / row_count, 4) if row_count else 0.0,
                min_value=s.get("min"),
                max_value=s.get("max"),
                sample_values=sample_vals,
                distinct_values=distinct_values,
                inferred_semantic_type=infer_semantic_type(name, col["dtype"]),
                pii_type=evidence.pii_type if evidence else None,
            )
        )
        if evidence is not None:
            pii_evidence[name] = evidence
    table_profile = TableProfile(
        datasource=display,
        table_name=table,
        row_count=sampling.row_count,
        columns=profiles,
        sampling=sampling,
    )
    # Evidence travels with the profile (object attribute, not serialized);
    # the engine turns it into PIIFinding rows for reports.
    object.__setattr__(table_profile, "pii_evidence", pii_evidence)
    return table_profile
