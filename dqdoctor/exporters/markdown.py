from __future__ import annotations

from pathlib import Path

from dqdoctor.models import ProfileResult, RuleSuggestion


def export_markdown(
    profile: ProfileResult,
    rules: list[RuleSuggestion],
) -> str:
    lines: list[str] = []
    lines.append(f"# Data Dictionary: {profile.table_name}")
    lines.append("")
    lines.append(f"- **Database**: {profile.db_path}")
    lines.append(f"- **Rows**: {profile.row_count}")
    lines.append("")

    lines.append("## Columns")
    lines.append("")
    lines.append(
        "| Column | Type | Nullable | Distinct | "
        "Min | Max | Semantic |"
    )
    lines.append(
        "|--------|------|----------|----------|"
        "-----|-----|----------|"
    )
    for col in profile.columns:
        nullable = "Yes" if col.null_rate > 0 else "No"
        lines.append(
            f"| {col.name} | {col.dtype} | {nullable} | "
            f"{col.distinct_count} | "
            f"{col.min_value if col.min_value is not None else '-'} | "
            f"{col.max_value if col.max_value is not None else '-'} | "
            f"{col.inferred_semantic_type} |"
        )

    lines.append("")
    lines.append("## Quality Rules")
    lines.append("")
    lines.append("| Type | Column | Confidence | Severity | Reason |")
    lines.append("|------|--------|------------|----------|--------|")
    for rule in rules:
        lines.append(
            f"| {rule.rule_type} | {rule.column} | "
            f"{rule.confidence:.0%} | {rule.severity} | "
            f"{rule.reason} |"
        )

    lines.append("")
    return "\n".join(lines)


def save_markdown(
    profile: ProfileResult,
    rules: list[RuleSuggestion],
    output_path: "str | Path",
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = export_markdown(profile, rules)
    output_path.write_text(content, encoding="utf-8")
    return output_path
