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
    db_path: "str | Path",
    min_overlap: float = 0.5,
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
    table_col_names: dict[str, list[str]] = {}
    for t in tables:
        table_columns[t] = get_table_columns(con, t)
        table_col_names[t] = [c["name"] for c in table_columns[t]]

    relationships: list[FKRelationship] = []
    seen_pairs: set[tuple[str, str, str, str]] = set()

    for src_table in tables:
        for src_col_info in table_columns[src_table]:
            src_col = src_col_info["name"]
            if not _is_fk_candidate(src_col):
                continue

            for tgt_table in tables:
                if tgt_table == src_table:
                    continue
                tgt_cols = table_col_names[tgt_table]
                matching = [tc for tc in tgt_cols if tc.lower() == src_col.lower()]
                for tgt_col in matching:
                    is_tgt_pk = tgt_col.lower() == "id"
                    if not is_tgt_pk and "id" in tgt_cols:
                        non_id_cols = [tc.lower() for tc in tgt_cols if tc.lower() != "id"]
                        if src_col.lower() not in non_id_cols:
                            continue

                    pair_key = tuple(
                        sorted(
                            [
                                (src_table, src_col),
                                (tgt_table, tgt_col),
                            ]
                        )
                    )
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    overlap = _compute_overlap(
                        con,
                        src_table,
                        src_col,
                        tgt_table,
                        tgt_col,
                    )
                    if overlap >= min_overlap:
                        if is_tgt_pk:
                            from_t, from_c = src_table, src_col
                            to_t, to_c = tgt_table, tgt_col
                        else:
                            from_t, from_c = src_table, src_col
                            to_t, to_c = tgt_table, tgt_col

                        confidence = _estimate_confidence(
                            from_c,
                            to_c,
                            overlap,
                            is_tgt_pk,
                        )
                        relationships.append(
                            FKRelationship(
                                from_table=from_t,
                                from_column=from_c,
                                to_table=to_t,
                                to_column=to_c,
                                overlap_rate=round(overlap, 4),
                                confidence=round(confidence, 2),
                            )
                        )

    relationships.sort(key=lambda r: r.confidence, reverse=True)
    return relationships


def _compute_overlap(
    con: ConnectionWrapper,
    src_table: str,
    src_col: str,
    tgt_table: str,
    tgt_col: str,
) -> float:
    qt_s = con.quote(src_table)
    qt_t = con.quote(tgt_table)
    qc_s = con.quote(src_col)
    qc_t = con.quote(tgt_col)

    src_row = con.fetchone(f"SELECT COUNT(DISTINCT {qc_s}) FROM {qt_s} WHERE {qc_s} IS NOT NULL")
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


def _estimate_confidence(
    src_col: str,
    tgt_col: str,
    overlap: float,
    is_tgt_pk: bool,
) -> float:
    score = overlap * 0.6
    if is_tgt_pk:
        score += 0.2
    if src_col.lower() == tgt_col.lower():
        score += 0.1
    return min(1.0, score)
