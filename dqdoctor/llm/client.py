from __future__ import annotations

import json
from typing import Any, Optional

from dqdoctor.models import ColumnProfile, RuleSuggestion


def _build_prompt(columns: list[ColumnProfile]) -> str:
    col_desc = []
    for col in columns:
        col_desc.append(
            f"- {col.name} ({col.dtype}): "
            f"null_rate={col.null_rate:.2%}, "
            f"distinct={col.distinct_count}, "
            f"sample={col.sample_values[:5]}, "
            f"semantic={col.inferred_semantic_type}"
        )
    return (
        "You are a data quality expert. Given the following column profiles, "
        "suggest additional quality rules beyond the obvious ones "
        "(not_null, unique, accepted_values, range, freshness).\n\n"
        "Columns:\n"
        + "\n".join(col_desc)
        + "\n\nReturn a JSON array of rules. Each rule must have:\n"
        '- rule_type: string (e.g. "regex_pattern", "cross_field", '
        '"business_rule")\n'
        "- column: string\n"
        "- params: object with rule-specific parameters\n"
        "- confidence: float 0-1\n"
        "- severity: high/medium/low\n"
        "- reason: string explaining why this rule is suggested\n\n"
        "Return ONLY the JSON array, no other text."
    )


def _parse_response(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.startswith("```")]
        text = "\n".join(lines)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return []


def suggest_rules_llm(
    columns: list[ColumnProfile],
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: str = "deepseek-chat",
) -> list[RuleSuggestion]:
    if not api_key:
        return []

    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "openai package is required for LLM features. Install with: pip install dq-doctor[llm]"
        )

    client = OpenAI(api_key=api_key, base_url=base_url)
    prompt = _build_prompt(columns)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=2000,
    )

    content = response.choices[0].message.content or ""
    raw_rules = _parse_response(content)

    rules: list[RuleSuggestion] = []
    for i, raw in enumerate(raw_rules):
        rules.append(
            RuleSuggestion(
                rule_id=f"llm.{raw.get('column', 'unknown')}.{i}",
                rule_type=raw.get("rule_type", "unknown"),
                column=raw.get("column", ""),
                params=raw.get("params", {}),
                confidence=min(1.0, max(0.0, float(raw.get("confidence", 0.5)))),
                severity=raw.get("severity", "medium"),
                reason=raw.get("reason", "Suggested by LLM."),
                source="llm",
            )
        )
    return rules
