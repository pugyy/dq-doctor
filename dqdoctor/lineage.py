from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from dqdoctor.connectors.auto import get_connection
from dqdoctor.correlation import detect_correlations
from dqdoctor.fk_discovery import discover_foreign_keys


class LineageEdge(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    lineage_type: str
    confidence: float
    description: str


class LineageResult(BaseModel):
    edges: list[LineageEdge]
    summary: str


def discover_lineage(db_path: "str | Path") -> LineageResult:
    con = get_connection(str(db_path))
    try:
        fks = discover_foreign_keys(db_path)
        edges: list[LineageEdge] = []

        for fk in fks:
            edges.append(
                LineageEdge(
                    source_table=fk.from_table,
                    source_column=fk.from_column,
                    target_table=fk.to_table,
                    target_column=fk.to_column,
                    lineage_type="foreign_key",
                    confidence=fk.confidence,
                    description=(
                        f"{fk.from_table}.{fk.from_column} → "
                        f"{fk.to_table}.{fk.to_column} "
                        f"(overlap: {fk.overlap_rate:.0%})"
                    ),
                )
            )

        from dqdoctor.connectors.auto import list_tables

        tables = list_tables(con)
        for table in tables:
            corrs = detect_correlations(db_path, table)
            for corr in corrs:
                if corr.correlation_type == "near_equal":
                    edges.append(
                        LineageEdge(
                            source_table=table,
                            source_column=corr.column_a,
                            target_table=table,
                            target_column=corr.column_b,
                            lineage_type="correlation",
                            confidence=corr.confidence,
                            description=corr.description,
                        )
                    )

        fk_count = sum(1 for e in edges if e.lineage_type == "foreign_key")
        corr_count = sum(1 for e in edges if e.lineage_type == "correlation")
        summary = f"Found {len(edges)} lineage edge(s): {fk_count} FK, {corr_count} correlation"

        return LineageResult(edges=edges, summary=summary)
    finally:
        con.close()
