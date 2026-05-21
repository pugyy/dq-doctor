from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from dqdoctor.connectors.auto import ConnectionWrapper, get_connection


class ColumnCorrelation(BaseModel):
    column_a: str
    column_b: str
    correlation_type: str
    description: str
    confidence: float


def detect_correlations(
    db_path: "str | Path", table_name: str,
) -> list[ColumnCorrelation]:
    con = get_connection(str(db_path))
    try:
        qt = con.quote(table_name)
        return _detect(con, qt)
    finally:
        con.close()


def _detect(con: ConnectionWrapper, table: str) -> list[ColumnCorrelation]:
    from dqdoctor.connectors.auto import get_table_columns

    columns = get_table_columns(con, table)
    numeric_cols = [c["name"] for c in columns if _is_likely_numeric(c["dtype"])]
    results: list[ColumnCorrelation] = []

    if len(numeric_cols) < 2:
        return results

    pairs_checked: set[tuple[str, str]] = set()
    for i, col_a in enumerate(numeric_cols):
        for col_b in numeric_cols[i + 1:]:
            pair = tuple(sorted([col_a, col_b]))
            if pair in pairs_checked:
                continue
            pairs_checked.add(pair)
            corr = _check_pair(con, table, col_a, col_b)
            if corr:
                results.append(corr)

    results.sort(key=lambda r: r.confidence, reverse=True)
    return results


def _is_likely_numeric(dtype: str) -> bool:
    upper = dtype.upper()
    numeric_types = {
        "TINYINT", "SMALLINT", "INTEGER", "BIGINT",
        "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT",
        "FLOAT", "DOUBLE", "DECIMAL", "HUGEINT",
    }
    return upper in numeric_types or upper.startswith("DECIMAL")


def _check_pair(
    con: ConnectionWrapper, table: str, col_a: str, col_b: str,
) -> ColumnCorrelation | None:
    qa = con.quote(col_a)
    qb = con.quote(col_b)

    row = con.fetchone(
        f"SELECT SUM({qa} * {qb}), SUM({qa}), SUM({qb}), "
        f"SUM({qa} * {qa}), SUM({qb} * {qb}), COUNT(*) "
        f"FROM {table} WHERE {qa} IS NOT NULL AND {qb} IS NOT NULL"
    )
    if row is None or row[5] < 5:
        return None

    sum_ab, sum_a, sum_b, sum_aa, sum_bb, n = row
    if n == 0:
        return None

    mean_a = sum_a / n
    mean_b = sum_b / n
    var_a = sum_aa / n - mean_a * mean_a
    var_b = sum_bb / n - mean_b * mean_b

    if var_a <= 0 or var_b <= 0:
        return None

    pearson = (sum_ab / n - mean_a * mean_b) / (var_a ** 0.5 * var_b ** 0.5)
    abs_pearson = abs(pearson)

    if abs_pearson >= 0.95:
        if pearson > 0:
            desc = f"'{col_a}' and '{col_b}' are highly correlated (r={pearson:.3f})"
        else:
            desc = f"'{col_a}' and '{col_b}' are strongly negatively correlated (r={pearson:.3f})"
        return ColumnCorrelation(
            column_a=col_a,
            column_b=col_b,
            correlation_type="pearson",
            description=desc,
            confidence=round(abs_pearson, 2),
        )

    ratio_row = con.fetchone(
        f"SELECT COUNT(*) FROM {table} "
        f"WHERE {qa} > 0 AND {qb} > 0 AND ABS({qa} - {qb}) < 0.01"
    )
    if ratio_row and ratio_row[0] > 0:
        total_row = con.fetchone(
            f"SELECT COUNT(*) FROM {table} WHERE {qa} > 0 AND {qb} > 0"
        )
        if total_row and total_row[0] > 5:
            match_rate = ratio_row[0] / total_row[0]
            if match_rate >= 0.8:
                return ColumnCorrelation(
                    column_a=col_a,
                    column_b=col_b,
                    correlation_type="near_equal",
                    description=f"'{col_a}' ≈ '{col_b}' ({match_rate:.0%} of rows match)",
                    confidence=round(match_rate, 2),
                )

    return None
