from __future__ import annotations

from pathlib import Path

from dqdoctor.models import ProfileResult, RuleSuggestion


def export_soda_cl(
    profile: ProfileResult,
    rules: list[RuleSuggestion],
) -> str:
    lines = [
        f"checks for {profile.table_name}:",
    ]
    for rule in rules:
        if rule.rule_type == "not_null":
            lines.append(f"  - missing_count({rule.column}) = 0")
        elif rule.rule_type == "unique":
            lines.append(f"  - duplicate_count({rule.column}) = 0")
        elif rule.rule_type == "accepted_values":
            values = rule.params.get("values", [])
            vals_str = ", ".join(f"'{v}'" for v in values)
            lines.append(
                f"  - invalid_count({rule.column}) = 0:"
                f" {{ values: [{vals_str}] }}"
            )
        elif rule.rule_type == "range":
            min_v = rule.params.get("min")
            max_v = rule.params.get("max")
            if min_v is not None:
                lines.append(f"  - min({rule.column}) >= {min_v}")
            if max_v is not None:
                lines.append(f"  - max({rule.column}) <= {max_v}")
        elif rule.rule_type == "freshness":
            hours = rule.params.get("max_age_hours", 24)
            lines.append(f"  - freshness({rule.column}) < {hours}h")
    return "\n".join(lines) + "\n"


def save_soda_cl(
    profile: ProfileResult,
    rules: list[RuleSuggestion],
    output_path: "str | Path",
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(export_soda_cl(profile, rules), encoding="utf-8")
    return output_path
