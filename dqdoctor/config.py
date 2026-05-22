from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

_DEFAULT_CONFIG_NAME = ".dqdoctor.yml"


class TableConfig(BaseModel):
    freshness: dict[str, dict[str, Any]] = Field(default_factory=dict)
    disable_rules: list[str] = Field(default_factory=list)
    severity: dict[str, str] = Field(default_factory=dict)
    sql_rules: list[dict[str, Any]] = Field(default_factory=list)


class DQConfig(BaseModel):
    db: Optional[str] = None
    tables: dict[str, TableConfig] = Field(default_factory=dict)
    rules: list[dict[str, Any]] = Field(default_factory=list)


def load_config(path: "str | Path | None" = None) -> DQConfig:
    if path is None:
        candidates = [
            Path(_DEFAULT_CONFIG_NAME),
            Path(".dqdoctor.yaml"),
        ]
        for c in candidates:
            if c.exists():
                path = c
                break
        if path is None:
            return DQConfig()

    path = Path(path)
    if not path.exists():
        return DQConfig()

    content = path.read_text(encoding="utf-8-sig")
    data = yaml.safe_load(content) or {}
    return DQConfig(**data)


def apply_config_to_rules(
    rules: list, table_name: str, config: DQConfig,
) -> list:
    tc = config.tables.get(table_name)
    if tc is None:
        return rules

    result = []
    for r in rules:
        rule_key = f"{r.rule_type}:{r.column}"
        rule_key_alt = f"{r.column}:{r.rule_type}"
        if rule_key in tc.disable_rules or rule_key_alt in tc.disable_rules:
            continue
        if r.rule_type in tc.disable_rules:
            continue
        if rule_key in tc.severity:
            r.severity = tc.severity[rule_key]
        elif rule_key_alt in tc.severity:
            r.severity = tc.severity[rule_key_alt]
        if r.rule_type == "freshness" and r.column in tc.freshness:
            override = tc.freshness[r.column]
            if "max_age_hours" in override:
                r.params["max_age_hours"] = override["max_age_hours"]
        result.append(r)
    return result


def get_sql_rules(config: DQConfig, table_name: str) -> list[dict[str, Any]]:
    tc = config.tables.get(table_name)
    if tc is None:
        return []
    return tc.sql_rules
