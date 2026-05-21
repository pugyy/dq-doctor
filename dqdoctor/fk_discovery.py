from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from dqdoctor.connectors.auto import ConnectionWrapper, get_connection


class FKRelationship(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    overlap_rate: float
    confidence: float


def _is_fk_candidate(col_name: str) -> bool:
    lower = col_name.lower()
    if lower == "id":
        return False
    return lower.endswith("_id")


def discover_foreign_keys(
    db_path: "str | Path", min_overlap: float = 0.5,
) -> list[FKRelationship]:
    con = get_connection(str(db_path))
    try:
        return _discover(con, min_overlap)
    finally:
        con.close()


def _discover(con: ConnectionWrapper, min_overlap: float) -> list[FKRelationship]:
    from dqdoctor.connectors.auto import get_table_columns, list_tables

    tables = list_tables(con)
    table_columns: dict[str, list[dict]] = {}
    for t in tables:
        table_columns[t] = get_table_columns(con, t)

    all_id_cols: list[tuple[str, str]] = []
    for t in tables:
        for c in table_columns[t]:
            if _is_fk_candidate(c["name"]):
                all_id_cols.append((t, c["name"]))

    relationships: list[FKRelationship] = []
    for src_table, src_col in all_id_cols:
        for tgt_table in tables:
            if tgt_table == src_table:
                continue
            tgt_col_names = [c["name"] for c in table_columns[tgt_table]]
            matching = [
                tc for tc in tgt_col_names
                if tc.lower() == src_col.lower()
            ]
            for tgt_col in matching:
                overlap = _compute_overlap(con, src_table, src_col, tgt_table, tgt_col)
                if overlap >= min_overlap:
                    confidence = _estimate_confidence(src_col, tgt_col, overlap)
                    relationships.append(FKRelationship(
                        from_table=src_table,
                        from_column=src_col,
                        to_table=tgt_table,
                        to_column=tgt_col,
                        overlap_rate=round(overlap, 4),
                        confidence=round(confidence, 2),
                    ))

    relationships.sort(key=lambda r: r.confidence, reverse=True)
    return relationships


def _compute_overlap(
    con: ConnectionWrapper,
    src_table: str, src_col: str,
    tgt_table: str, tgt_col: str,
) -> float:
    qt_s = con.quote(src_table)
    qt_t = con.quote(tgt_table)
    qc_s = con.quote(src_col)
    qc_t = con.quote(tgt_col)

    src_row = con.fetchone(
        f"SELECT COUNT(DISTINCT {qc_s}) FROM {qt_s} WHERE {qc_s} IS NOT NULL"
    )
    if src_row is None or src_row[0] == 0:
        return 0.0

    overlap_row = con.fetchone(
        f"SELECT COUNT(DISTINCT s.{qc_s}) "
        f"FROM {qt_s} s "
        f"INNER JOIN {qt_t} t ON s.{qc_s} = t.{qc_t} "
        f"WHERE s.{qc_s} IS NOT NULL"
    )
    if overlap_row is None:
        return 0.0
    return overlap_row[0] / src_row[0]


def _estimate_confidence(src_col: str, tgt_col: str, overlap: float) -> float:
    score = overlap * 0.7
    if src_col.lower() == tgt_col.lower():
        score += 0.2
    if tgt_col.lower() == "id":
        score += 0.1
    return min(1.0, score)
