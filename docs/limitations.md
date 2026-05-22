# Known Limitations

## Experimental Features

These features work but are marked **experimental** — they may have edge cases:

| Feature | Status | Note |
|---------|--------|------|
| LLM rule suggestions | Experimental | Quality depends on model and prompt |
| Column correlation | Experimental | Pearson only; not causal |
| Data lineage | Experimental | Based on FK + correlation heuristics |
| Soda CL export | Starter | Basic metric mapping |
| Deequ export | Starter | Basic constraint mapping |
| Web dashboard | Starter | Read-only, no auth |

## General Limitations

- **DuckDB is first-class**: PostgreSQL and MySQL work but are less tested
- **No incremental profiling**: Full table scan each time (not optimized for large tables)
- **FK discovery is heuristic-based**: Relies on column name overlap, not DDL metadata
- **PII detection is regex-based**: No ML/NLP — may have false positives/negatives
- **No scheduling built-in**: Use Airflow operator or cron
- **Single-database scope**: No cross-database lineage
- **No streaming support**: Batch only (files and relational databases)

## Not Suitable For

- Real-time data quality monitoring
- Enterprise data governance / catalog
- Multi-tenant SaaS deployments
- Spark / Flink / Kafka integrations
