"""Redaction helpers: reports, profiles, logs and LLM payloads must not
leak raw sample values or connection secrets by default.

The policy (1.0): raw values stay in memory during a run; anything written
to disk or sent to a model goes through these helpers first. Text min/max
and distinct-value lists are the "indirect paths" called out by the
security review - they are replaced with shape descriptors.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any


def fingerprint(value: Any) -> str:
    """Short stable fingerprint of a value (no raw content)."""
    return hashlib.sha256(str(value).encode("utf-8", "replace")).hexdigest()[:12]


def redact_value(value: Any) -> str:
    """Display form of a sample-like value: type tag + fingerprint."""
    if value is None:
        return "null"
    return f"<{type(value).__name__}:{fingerprint(value)}>"


def redact_samples(values: list[Any]) -> list[str]:
    return [redact_value(v) for v in values]


def redact_scalar(value: Any, include_samples: bool = False) -> Any:
    """Redact a min/max-style scalar if it could carry free text content.

    Only ``str``/``bytes`` are content-bearing and therefore fingerprinted.
    Numbers - including ``Decimal`` - and temporal values are *statistics*,
    not content: a report that says ``<str:1f2e3d>`` instead of
    ``[0.00, 500.00]`` is useless, and a date range leaks nothing that a
    min/max aggregate does not already leak. 1.0 over-redacted these.
    """
    if include_samples or value is None:
        return value
    if isinstance(value, bool | int | float | Decimal | date | datetime | time):
        return value
    if isinstance(value, str | bytes | bytearray):
        return redact_value(value)
    return redact_value(value)


def column_stats_safe(profile_column: dict, include_samples: bool = False) -> dict:
    """Redacted view of one column profile for reports/JSON output."""
    out = dict(profile_column)
    out.pop("sample_values", None)
    out.pop("distinct_values", None)
    if not include_samples:
        out["min_value"] = redact_scalar(out.get("min_value"))
        out["max_value"] = redact_scalar(out.get("max_value"))
    return out


def llm_safe_profile(columns: list[dict]) -> list[dict]:
    """Column descriptors safe to send to an LLM: metadata only, no samples."""
    safe = []
    for c in columns:
        safe.append(
            {
                "name": c.get("name"),
                "dtype": c.get("dtype"),
                "null_rate": c.get("null_rate"),
                "distinct_count": c.get("distinct_count"),
                "semantic": c.get("inferred_semantic_type"),
            }
        )
    return safe
