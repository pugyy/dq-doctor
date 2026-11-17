"""Heuristic FK candidates and referential-integrity checks.

Heuristic discovery (``*_id`` name matching) is gated by type compatibility
and target-key uniqueness to cut 0.7's false positives; declared keys
always win. Checks count orphans over NULL-safe join predicates
(MySQL ``<=>`` / ``IS NOT DISTINCT FROM``) so composite keys behave. Orphan
samples are never materialized - counts only.
"""
from __future__ import annotations

from dqdoctor.fkdeclared import FKPlan, FKRelationship
from dqdoctor.models import FKIssue


def build_plan(con, include_heuristic: bool = True) -> FKPlan:
    """Assemble the run-once FK plan: declared first, heuristics appended."""
    from dqdoctor.fkdeclared import declared_foreign_keys

    relationships = declared_foreign_keys(con)
    notes = [f"declared relationships: {len(relationships)}"]
    if include_heuristic:
        added = 0
        known = {
            (r.from_table, tuple(r.from_columns), r.to_table, tuple(r.to_columns), r.to_schema)
            for r in relationships
        }
        for cand in heuristic_candidates(con):
            key = (cand.from_table, tuple(cand.from_columns),
                   cand.to_table, tuple(cand.to_columns), cand.to_schema)
            if key not in known:
                relationships.append(cand)
                added += 1
        notes.append(f"heuristic candidates added: {added}")
    return FKPlan(relationships=relationships, discovery_notes=notes)


def heuristic_candidates(con) -> list[FKRelationship]:
    """Candidate parents for ``*_id`` columns, name- or table-derived.

    A column matches a target when either:
    - the target has a column with the same name (``user_id -> users.user_id``),
      or
    - the column's stem names the target table and the target has a single
      --column primary key (``parent_id -> parent.id`` / ``-> parents.id``).

    Candidates are gated by type family equality and by target-key
    uniqueness (an all-NULL target column is not a key), and the pair is
    recorded once with the direction pointing at the unique key side.
    """
    from dqdoctor.queries import list_tables, table_columns

    tables = list_tables(con)
    schemas = {t: table_columns(con, t) for t in tables}
    families = {
        (t, col["name"]): _family(col["dtype"])
        for t, cols in schemas.items() for col in cols
    }
    candidates: list[FKRelationship] = []
    seen: set[tuple] = set()

    for src in tables:
        for col in schemas[src]:
            name = col["name"]
            lower = name.lower()
            if lower == "id" or not lower.endswith("_id"):
                continue
            column_stems = _column_stems(lower)
            for tgt in tables:
                if tgt == src:
                    continue
                for tcol in schemas[tgt]:
                    tname = tcol["name"].lower()
                    same_name = tname == lower
                    stem_matches_table = (
                        tname == "id"
                        and bool(column_stems & _table_stems(tgt))
                    )
                    if not (same_name or stem_matches_table):
                        continue
                    if families.get((src, name)) != families.get((tgt, tcol["name"])):
                        continue  # int -> int, text -> text only
                    if not _is_unique(con, tgt, tcol["name"]):
                        continue  # target must look like a key
                    key = tuple(sorted([
                        (src, name), (tgt, tcol["name"]),
                    ]))
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(
                        FKRelationship(
                            from_table=src, from_columns=[name],
                            to_table=tgt, to_columns=[tcol["name"]],
                            declared=False, confidence=0.6,
                        )
                    )
    return candidates


def _table_stems(table: str) -> set[str]:
    """Accepted singular/plural forms of a table name for ``*_id`` matching."""
    t = table.lower()
    stems = {t}
    if t.endswith("s"):
        stems.add(t[:-1])
    else:
        stems.add(t + "s")
    if t.endswith("es"):
        stems.add(t[:-2])
    return stems


def _column_stems(column_lower: str) -> set[str]:
    """Candidate table names implied by an ``*_id`` column.

    ``parent_id`` -> {parent, parents}; ``user_id`` -> {user, users};
    ``order_item_id`` -> {order_item, order_items}. Shared-token names map
    too, so ``parent_id`` also covers a ``parent``/``parents`` table.
    """
    stem = column_lower[: -len("_id")]
    if not stem:
        return set()
    forms = {stem, stem + "s"}
    if stem.endswith("s"):
        forms.add(stem[:-1])
    return forms


def _family(dtype: str) -> str:
    d = dtype.strip().lower()
    if d.startswith(("int", "bigint", "smallint", "tinyint", "hugeint")):
        return "int"
    if d.startswith(("varchar", "char", "text", "string")):
        return "text"
    return d.split("(")[0]


def _is_unique(con, table: str, column: str) -> bool:
    """Target column must hold distinct non-null values to look like a key."""
    qt = con.table_ref(table)
    qc = con.quote_identifier(column)
    con.query_count += 1
    if con.backend == "duckdb":
        row = con._raw.execute(
            "SELECT COUNT(" + qc + "), COUNT(DISTINCT " + qc + ") FROM " + qt
            + " WHERE " + qc + " IS NOT NULL"
        ).fetchone()
    else:
        from sqlalchemy import text

        row = con._raw.execute(
            text("SELECT COUNT(" + qc + "), COUNT(DISTINCT " + qc + ") FROM "
                 + qt + " WHERE " + qc + " IS NOT NULL")
        ).fetchone()
    # An empty (or all-NULL) column is trivially "0 == 0" but is not a key;
    # requiring at least one value stops empty tables from becoming targets.
    return row[0] > 0 and row[0] == row[1]


def check_relationship(con, rel: FKRelationship) -> FKIssue:
    """Count orphan rows for one relationship (single or composite key)."""
    qsrc = con.table_ref(rel.from_table)
    qtgt = (
        con.quote_qualified(rel.to_table, rel.to_schema)
        if rel.to_schema else con.table_ref(rel.to_table)
    )
    not_null = " AND ".join(
        "s." + con.quote_identifier(c) + " IS NOT NULL" for c in rel.from_columns
    )
    match = _null_safe_match(con, rel)
    predicate = "NOT EXISTS (SELECT 1 FROM " + qtgt + " t WHERE " + match + ")"

    con.query_count += 1
    if con.backend == "duckdb":
        total_row = con._raw.execute(
            "SELECT COUNT(*) FROM " + qsrc + " s WHERE " + not_null
        ).fetchone()
        orphan_row = con._raw.execute(
            "SELECT COUNT(*) FROM " + qsrc + " s WHERE " + not_null
            + " AND " + predicate
        ).fetchone()
    else:
        from sqlalchemy import text

        total_row = con._raw.execute(
            text("SELECT COUNT(*) FROM " + qsrc + " s WHERE " + not_null)
        ).fetchone()
        orphan_row = con._raw.execute(
            text("SELECT COUNT(*) FROM " + qsrc + " s WHERE " + not_null
                 + " AND " + predicate)
        ).fetchone()
    return FKIssue(
        from_table=rel.from_table,
        from_column="+".join(rel.from_columns),
        to_table=f"{rel.to_schema}.{rel.to_table}" if rel.to_schema else rel.to_table,
        to_column="+".join(rel.to_columns),
        orphan_rows=orphan_row[0],
        total_rows=total_row[0],
        declared=rel.declared,
    )


def _null_safe_match(con, rel: FKRelationship) -> str:
    """NULL-safe join predicate across backends (MySQL <=>, others IS NOT
    DISTINCT FROM) so composite keys with NULL parts match correctly."""
    parts = []
    for src_c, tgt_c in zip(rel.from_columns, rel.to_columns, strict=False):
        s = "s." + con.quote_identifier(src_c)
        t = "t." + con.quote_identifier(tgt_c)
        if con.backend == "mysql":
            parts.append(t + " <=> " + s)
        else:
            parts.append(t + " IS NOT DISTINCT FROM " + s)
    return " AND ".join(parts)


def check_all(con, plan: FKPlan) -> list[FKIssue]:
    return [check_relationship(con, rel) for rel in plan.relationships]
