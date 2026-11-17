"""Redaction helpers: reports, profiles, logs and LLM payloads must not
leak raw sample values or connection secrets by default.

The policy (1.0): raw values stay in memory during a run; anything written
to disk or sent to a model goes through these helpers first. Text min/max
and distinct-value lists are the "indirect paths" called out by the
security review - they are replaced with shape descriptors.
"""
from __future__ import annotations

import hashlib
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
    """Redact a min/max-style scalar if it could carry content.

    Numbers, booleans and dates are safe as-is; strings and blobs are
    replaced by fingerprints unless the operator explicitly opted in.
    """
    if include_samples or value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
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
