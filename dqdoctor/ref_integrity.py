from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from dqdoctor.connectors.auto import get_connection
from dqdoctor.fk_discovery import FKRelationship, discover_foreign_keys


class RefIntegrityResult(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    total_rows: int
    orphan_rows: int
    orphan_rate: float
    passed: bool
    sample_orphans: list = []


def check_referential_integrity(
    db_path: "str | Path", relationships: list[FKRelationship] | None = None,
) -> list[RefIntegrityResult]:
    con = get_connection(str(db_path))
    try:
        if relationships is None:
            relationships = discover_foreign_keys(db_path)
        return [_check_one(con, fk) for fk in relationships]
    finally:
        con.close()


def _check_one(con, fk: FKRelationship) -> RefIntegrityResult:
    qt_src = con.quote(fk.from_table)
    qt_tgt = con.quote(fk.to_table)
    qc_src = con.quote(fk.from_column)
    qc_tgt = con.quote(fk.to_column)

    total_row = con.fetchone(
        f"SELECT COUNT(*) FROM {qt_src} WHERE {qc_src} IS NOT NULL"
    )
    total = total_row[0] if total_row else 0

    if total == 0:
        return RefIntegrityResult(
            from_table=fk.from_table,
            from_column=fk.from_column,
            to_table=fk.to_table,
            to_column=fk.to_column,
            total_rows=0,
            orphan_rows=0,
            orphan_rate=0.0,
            passed=True,
        )

    orphan_row = con.fetchone(
        f"SELECT COUNT(*) FROM {qt_src} s "
        f"WHERE s.{qc_src} IS NOT NULL "
        f"AND NOT EXISTS ("
        f"SELECT 1 FROM {qt_tgt} t WHERE t.{qc_tgt} = s.{qc_src}"
        f")"
    )
    orphans = orphan_row[0] if orphan_row else 0

    sample_rows = con.fetchall(
        f"SELECT DISTINCT s.{qc_src} FROM {qt_src} s "
        f"WHERE s.{qc_src} IS NOT NULL "
        f"AND NOT EXISTS ("
        f"SELECT 1 FROM {qt_tgt} t WHERE t.{qc_tgt} = s.{qc_src}"
        f") LIMIT 10"
    )
    sample_orphans = [r[0] for r in sample_rows]

    orphan_rate = round(orphans / total, 4)
    return RefIntegrityResult(
        from_table=fk.from_table,
        from_column=fk.from_column,
        to_table=fk.to_table,
        to_column=fk.to_column,
        total_rows=total,
        orphan_rows=orphans,
        orphan_rate=orphan_rate,
        passed=orphans == 0,
        sample_orphans=sample_orphans,
    )
