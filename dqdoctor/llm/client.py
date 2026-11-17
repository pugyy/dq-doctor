"""LLM-assisted rule suggestions (optional, opt-in, not on the check path).

Two hard rules:

1. **Metadata only.** The prompt carries column names, types, null rates and
   distinct counts - never sample values. 0.7 embedded ``sample_values[:5]``
   in the prompt, which shipped PII to a third party.
2. **Suggestions are not rules.** Output is returned as ``RuleSpec`` entries
   with ``source="llm"``; nothing here executes them. A human must copy them
   into a contract (``enabled: true``) for them to gate anything.

The API key is read from the caller (CLI/env), never from source or config.
"""
from __future__ import annotations

import json
from typing import Any

from dqdoctor.models import ColumnProfile, RuleSpec
from dqdoctor.redact import llm_safe_profile


def _build_prompt(columns: list[ColumnProfile]) -> str:
    described = llm_safe_profile([c.model_dump() for c in columns])
    return (
        "You are a data quality expert. Given column metadata (no data "
        "values are included), suggest additional quality rules beyond "
        "not_null, unique, accepted_values, range and freshness.\n\n"
        "Columns:\n"
        + json.dumps(described, indent=2)
        + "\n\nReturn a JSON array. Each element must have: type "
        "(regex|row_count|cross_field|sql), column, params, severity "
        "(high|medium|low), reason. Return ONLY the JSON array."
    )


def _parse_response(text: str) -> list[dict[str, Any]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(
            line for line in cleaned.splitlines() if not line.startswith("```")
        )
    for candidate in (cleaned, cleaned[cleaned.find("["): cleaned.rfind("]") + 1]):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return parsed
    return []


def suggest_rules_llm(
    columns: list[ColumnProfile],
    api_key: str | None = None,
    base_url: str | None = None,
    model: str = "deepseek-chat",
    timeout: float = 30.0,
) -> list[RuleSpec]:
    """Return LLM-proposed rules as *suggestions* (never executed here)."""
    if not api_key:
        return []
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError(
            "openai is required for LLM suggestions. "
            "Install with: pip install 'dq-doctor[llm]'"
        ) from exc

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": _build_prompt(columns)}],
        temperature=0.2,
        max_tokens=2000,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or ""
    specs: list[RuleSpec] = []
    for i, raw in enumerate(_parse_response(content)):
        rule_type = str(raw.get("type") or raw.get("rule_type") or "")
        column = str(raw.get("column") or "")
        if not rule_type or not column:
            continue
        specs.append(
            RuleSpec(
                id=f"llm/{rule_type}:{column}:{i}",
                type=rule_type,
                column=column,
                params=dict(raw.get("params") or {}),
                severity=str(raw.get("severity") or "medium"),
                reason=str(raw.get("reason") or "Suggested by LLM."),
                source="llm",
                enabled=False,  # a suggestion, never an executed rule
            )
        )
    return specs
