"""The 1.0 rule contract: an editable, versioned file that pins rule
definitions so new batches are checked against *fixed* expectations.

Layout (YAML or JSON)::

    version: 1
    datasource: demo.duckdb          # optional; CLI --db wins
    generated_at: 2026-11-17T...
    tables:
      orders:
        rules:
          - id: not_null:order_id
            type: not_null
            column: order_id
            severity: high
            params: {}
            reason: ...
          - id: range:total_amount
            type: range
            column: total_amount
            params: {min: "45.00", max: "680.00"}   # strings keep precision

Values learned from reference data (accepted sets, ranges) are frozen at
generation time - ``check --rules`` never re-learns them from the batch
under test. Legacy 0.7 files are migrated once via ``migrate_legacy``.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from dqdoctor import rules as R
from dqdoctor.datasources import redact_url
from dqdoctor.models import RuleSpec, TableProfile


class ContractError(Exception):
    """Raised for structurally invalid contract files."""


class TableRules(BaseModel):
    rules: list[RuleSpec] = Field(default_factory=list)


class Contract(BaseModel):
    version: int = 1
    datasource: str | None = None
    generated_at: str = ""
    tables: dict[str, TableRules] = Field(default_factory=dict)

    def specs_for(self, table: str) -> list[RuleSpec]:
        tr = self.tables.get(table)
        return list(tr.rules) if tr else []


# ---------------------------------------------------------------------------
# Load / save


def load_contract(path: Path) -> Contract:
    if not path.exists():
        raise ContractError(f"Contract file not found: {path}")
    text_value = path.read_text(encoding="utf-8-sig")
    try:
        data = yaml.safe_load(text_value) if path.suffix in (".yaml", ".yml") \
            else json.loads(text_value)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ContractError(f"Cannot parse contract file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError(f"Contract file {path} must be a mapping")
    if "rules" in data and "tables" not in data:
        # 0.7 single-table rules file
        raise ContractError(
            f"{path} looks like a legacy 0.7 rules file. Run "
            "`dqdoctor migrate` to convert it to the 1.0 contract format."
        )
    version = data.get("version")
    if version != 1:
        raise ContractError(
            f"Unsupported contract version {version!r} in {path} "
            "(expected: 1)"
        )
    tables_raw = data.get("tables") or {}
    if not isinstance(tables_raw, dict):
        raise ContractError("'tables' must be a mapping of table name -> rules")
    tables: dict[str, TableRules] = {}
    seen_ids: set[str] = set()
    for table, tr in tables_raw.items():
        if not isinstance(tr, dict):
            raise ContractError(f"tables.{table} must be a mapping")
        raw_rules = tr.get("rules", [])
        if not isinstance(raw_rules, list):
            raise ContractError(f"tables.{table}.rules must be a list")
        specs = []
        for i, raw in enumerate(raw_rules):
            if not isinstance(raw, dict):
                raise ContractError(f"tables.{table}.rules[{i}] must be a mapping")
            try:
                validated = R.validate_spec(raw, i, table=str(table))
            except ValueError as exc:
                raise ContractError(f"{path}: tables.{table}: {exc}") from exc
            if validated["id"] in seen_ids:
                raise ContractError(
                    f"{path}: duplicate rule id {validated['id']!r} - ids must "
                    "be unique across the contract"
                )
            seen_ids.add(validated["id"])
            specs.append(RuleSpec(**validated))
        tables[str(table)] = TableRules(rules=specs)
    datasource = data.get("datasource")
    if datasource is not None and not isinstance(datasource, str):
        raise ContractError("'datasource' must be a string")
    return Contract(
        version=1,
        datasource=datasource,
        generated_at=str(data.get("generated_at") or ""),
        tables=tables,
    )


def save_contract(contract: Contract, path: Path) -> Path:
    datasource = contract.datasource
    if datasource and "://" in datasource:
        datasource = redact_url(datasource)
    payload: dict[str, Any] = {
        "version": 1,
        "datasource": datasource,
        "generated_at": contract.generated_at,
        "tables": {
            table: {
                "rules": [
                    {
                        "id": r.id,
                        "type": r.type,
                        "column": r.column,
                        "params": _freeze_params(r.params),
                        "severity": r.severity,
                        "reason": r.reason,
                        "enabled": r.enabled,
                    }
                    for r in tr.rules
                ]
            }
            for table, tr in contract.tables.items()
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".json":
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    return path


def _freeze_params(params: dict) -> dict:
    """Numeric boundaries are stored as strings to preserve precision.

    ``Decimal('45.00')`` round-trips through YAML as a string; loaders call
    ``rules.as_number`` to restore exact numerics at execution time.
    """
    frozen = {}
    for key, value in params.items():
        if isinstance(value, bool):
            frozen[key] = value
        elif isinstance(value, int):
            frozen[key] = value
        elif isinstance(value, float):
            frozen[key] = repr(value)
        else:
            frozen[key] = value
    return frozen


# ---------------------------------------------------------------------------
# Generation from reference profiles (rules-init)


def build_contract(
    profiles: list[TableProfile],
    specs_by_table: dict[str, list[RuleSpec]],
    datasource: str | None = None,
) -> Contract:
    tables: dict[str, TableRules] = {}
    for profile in profiles:
        specs = specs_by_table.get(profile.table_name, [])
        tables[profile.table_name] = TableRules(rules=specs)
    return Contract(
        version=1,
        datasource=datasource,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        tables=tables,
    )


# ---------------------------------------------------------------------------
# One-time migration from 0.7 formats


def migrate_legacy(path: Path) -> Contract:
    """Convert a 0.7 rules file or .dqdoctor.yml into a 1.0 contract."""
    if not path.exists():
        raise ContractError(f"Legacy file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    if not isinstance(data, dict):
        raise ContractError(f"{path}: expected a mapping")

    if "rules" in data and "tables" not in data:
        return _migrate_rules_file(data, path)
    if "tables" in data:
        return _migrate_config_file(data, path)
    raise ContractError(
        f"{path}: not a recognizable 0.7 file (expected 'rules' or 'tables')"
    )


def _migrate_rules_file(data: dict, path: Path) -> Contract:
    table = str(data.get("table") or "TABLE_NAME")
    specs: list[RuleSpec] = []
    for raw in data.get("rules") or []:
        rule_id = raw.get("rule_id") or raw.get("id")
        rule_type = raw.get("rule_type") or raw.get("type")
        column = raw.get("column", "*")
        if not rule_id:
            rule_id = R.default_rule_id(str(rule_type), str(column))
        # 0.7 ids carried a global counter suffix (range:amount.7); strip it
        # so ids stay stable across regenerations.
        if isinstance(rule_id, str) and "." in rule_id:
            rule_id = rule_id.rsplit(".", 1)[0]
        specs.append(
            RuleSpec(
                id=str(rule_id),
                type=str(rule_type),
                column=str(column),
                params=_migrate_params(raw.get("params") or {}),
                severity=str(raw.get("severity") or "medium"),
                reason=str(raw.get("reason") or ""),
                source="contract",
                enabled=bool(raw.get("enabled", True)),
            )
        )
    return Contract(
        version=1,
        datasource=data.get("db"),
        generated_at=datetime.now().isoformat(timespec="seconds"),
        tables={table: TableRules(rules=specs)},
    )


def _migrate_params(params: dict) -> dict:
    migrated = {}
    for key, value in params.items():
        if key == "values" and isinstance(value, list):
            migrated[key] = [str(v) for v in value]
        else:
            migrated[key] = value
    return migrated


def _legacy_disabled(
    disabled_keys: set, table_disabled_types: set, rule_type: str, column: str
) -> bool:
    return (
        f"{rule_type}:{column}" in disabled_keys
        or f"{column}:{rule_type}" in disabled_keys
        or rule_type in table_disabled_types
    )


def _legacy_severity(severity_map: dict, rule_type: str, column: str, default: str) -> str:
    for key in (f"{rule_type}:{column}", f"{column}:{rule_type}"):
        if key in severity_map:
            return str(severity_map[key])
    return default


def _migrate_config_file(data: dict, path: Path) -> Contract:
    tables: dict[str, TableRules] = {}
    for table, tc in (data.get("tables") or {}).items():
        specs: list[RuleSpec] = []
        # 0.7 disable_rules / severity overrides carry over as *disabled*
        # contract entries plus explicit severity values, so nothing the
        # operator configured is silently dropped by the migration.
        disabled_keys = set(tc.get("disable_rules") or [])
        severity_map = tc.get("severity") or {}
        table_disabled_types = {k for k in disabled_keys if ":" not in str(k)}

        def _disabled(
            rule_type: str,
            column: str,
            _dis=disabled_keys,
            _types=table_disabled_types,
        ) -> bool:
            return _legacy_disabled(_dis, _types, rule_type, column)

        def _severity(
            rule_type: str, column: str, default: str, _sev=severity_map
        ) -> str:
            return _legacy_severity(_sev, rule_type, column, default)

        for raw in tc.get("sql_rules") or []:
            name = str(raw.get("name") or "unnamed_sql")
            expect_raw = raw.get("expect", 0)
            expect = (
                {"mode": "eq", "value": expect_raw}
                if not isinstance(expect_raw, dict)
                else expect_raw
            )
            specs.append(
                RuleSpec(
                    id=f"sql:{name}",
                    type="sql",
                    column="*",
                    params={"query": str(raw.get("query") or ""), "expect": expect},
                    severity=_severity("sql", name, "medium"),
                    reason="migrated from .dqdoctor.yml sql_rules",
                    source="contract",
                    enabled=not _disabled("sql", name),
                )
            )
        freshness = tc.get("freshness") or {}
        for column, override in freshness.items():
            specs.append(
                RuleSpec(
                    id=f"freshness:{column}",
                    type="freshness",
                    column=str(column),
                    params={"max_age_hours": override.get("max_age_hours", 24)},
                    severity=_severity("freshness", str(column), "high"),
                    reason="migrated from .dqdoctor.yml freshness override",
                    source="contract",
                    enabled=not _disabled("freshness", str(column)),
                )
            )
        for key in sorted(disabled_keys):
            rule_type, _, column = str(key).partition(":")
            if not column:
                continue  # bare type disable is applied via _disabled()
            if any(s.type == rule_type and s.column == column for s in specs):
                continue
            specs.append(
                RuleSpec(
                    id=f"{rule_type}:{column}",
                    type=rule_type if rule_type in R.RULE_TYPES else "not_null",
                    column=column,
                    severity=_severity(rule_type, column, "medium"),
                    reason="migrated from .dqdoctor.yml disable_rules",
                    source="contract",
                    enabled=False,
                )
            )
        # Ids are contract-wide unique: scope every migrated rule to its table
        # so a multi-table config migrates into a loadable contract.
        tables[str(table)] = TableRules(
            rules=[
                r.model_copy(update={"id": R.scope_rule_id(r.id, str(table))})
                for r in specs
            ]
        )
    return Contract(
        version=1,
        datasource=data.get("db"),
        generated_at=datetime.now().isoformat(timespec="seconds"),
        tables=tables,
    )
