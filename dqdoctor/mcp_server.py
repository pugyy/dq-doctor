"""Minimal stdio MCP server for dq-doctor.

Tools: ``list_datasets``, ``profile_table``, ``run_check``, ``get_summary``.
All tools reuse :class:`dqdoctor.engine.CheckEngine` - the same code path
as the CLI. stdout is reserved for the MCP protocol; logs go to stderr.
Datasources come from the startup config (.dqdoctor.yml) or its registry
aliases - never free-form URLs from callers.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("dqdoctor.mcp")
logger.addHandler(logging.StreamHandler(sys.stderr))


def _config_path(config: Path | None) -> Path:
    return Path(config) if config else Path(".dqdoctor.yml")


def _resolve(name: str, config: Path | None):
    from dqdoctor.datasources import DataSource, DatasourceError, load_registry, parse_spec

    path = _config_path(config)
    registry = load_registry(path)
    spec = registry.datasources.get(name)
    if spec is None:
        raise DatasourceError(
            "Unknown datasource alias. Use list_datasets to find available aliases."
        )
    return DataSource(parse_spec(spec, base_dir=path.parent))


def serve(config: Path | None = None) -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(
            "The MCP SDK is required. Install with: pip install 'dq-doctor[mcp]'"
        ) from exc

    mcp = FastMCP("dq-doctor")

    @mcp.tool()
    def list_datasets() -> dict[str, Any]:
        """List registered datasource aliases from the startup config."""
        from dqdoctor.datasources import load_registry

        registry = load_registry(_config_path(config))
        return {
            "datasources": sorted(registry.datasources),
            "default": registry.default,
        }

    @mcp.tool()
    def profile_table(datasource: str, table: str) -> dict[str, Any]:
        """Profile one table: row count, per-column stats, PII evidence.

        Raw sample values are never returned; text min/max are redacted.
        """
        import json

        from dqdoctor.cli import json_safe_profile
        from dqdoctor.profiling import profile_table as _profile

        ds = _resolve(datasource, config)
        con = ds.open()
        try:
            result = _profile(con, ds.describe(), table)
        finally:
            con.close()
        return json.loads(json_safe_profile(result))

    @mcp.tool()
    def run_check(
        datasource: str,
        table: str | None = None,
        all_tables: bool | None = None,
        rules_path: str | None = None,
    ) -> dict[str, Any]:
        """Run a check and return the full JSON outcome.

        Without rules_path this is explore mode (suggestions only).
        """
        from dqdoctor.contract import load_contract
        from dqdoctor.engine import CheckEngine
        from dqdoctor.outputs import _redacted_payload

        if (table and all_tables is True) or (not table and all_tables is False):
            raise ValueError("Specify one table or request all tables.")
        ds = _resolve(datasource, config)
        contract = None
        if rules_path:
            contract = load_contract(Path(rules_path))
        engine = CheckEngine(ds)
        outcome = engine.run(
            tables=[table] if table else None,
            contract=contract,
            explore=contract is None,
        )
        return _redacted_payload(outcome)

    @mcp.tool()
    def get_summary(datasource: str, table: str) -> dict[str, Any]:
        """One-table summary: score, status counts, PII list."""
        from dqdoctor.engine import CheckEngine

        ds = _resolve(datasource, config)
        engine = CheckEngine(ds)
        outcome = engine.run(tables=[table], explore=True)
        t = outcome.tables[0]
        counts: dict[str, int] = {}
        for r in t.rule_results:
            counts[r.status.value] = counts.get(r.status.value, 0) + 1
        return {
            "table": t.table_name,
            "score": t.score,
            "rule_counts": counts,
            "pii": [p.model_dump() for p in t.pii_findings],
        }

    logger.info("starting dq-doctor MCP server (stdio)")
    mcp.run()
