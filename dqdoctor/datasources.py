"""Data source resolution and connection lifecycle for dq-doctor 1.0.

- ``resolve()`` turns a CLI/config string (URL, path, or registered alias)
  into a ``DataSource``. PostgreSQL/MySQL go through SQLAlchemy, DuckDB
  files and CSV/Parquet/JSON files go through DuckDB directly (file
  registration lives in ``dqdoctor.fileviews``).
- ``DataSource.open()`` returns a ``Connection``: identifier quoting, schema
  selection, session read-only enforcement, statement timeouts. Metadata
  queries live in ``dqdoctor.queries``.
- ``describe()`` never leaks credentials.

Security model: identifiers are allowlist-validated before quoting (the
only variable text spliced into SQL), session settings run as literals
with bound values, and every query elsewhere binds its values. The single
value-in-SQL-text case (file paths in DuckDB DDL) is isolated in
``dqdoctor.fileviews``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from dqdoctor.fileviews import register_file_views

FILE_EXTENSIONS = {
    ".csv": "csv",
    ".tsv": "csv",
    ".parquet": "parquet",
    ".pq": "parquet",
    ".json": "json",
    ".jsonl": "json",
    ".ndjson": "json",
}


class DatasourceError(Exception):
    """User-facing error: bad spec, missing file, unreadable source."""


class IdentifierError(DatasourceError):
    """An identifier (table/column/schema name) failed validation."""


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
# Anything a database can legally hold in an identifier once quoted: letters
# (including CJK), digits, underscore, dollar, space, hyphen, dot. Control
# characters and quotes are rejected; quotes are escaped by the caller.
_IDENT_ANY_RE = re.compile(r"^[^\x00-\x1f\x7f\"]+$")


def validate_identifier(name: str, what: str = "identifier") -> str:
    """Validate a name that will be spliced into SQL as a quoted identifier.

    Accepts any non-empty name without control characters or double quotes
    (CJK column names, hyphens, spaces and digits-first names are legal
    once quoted - 0.7 supported them). Callers must pass the result through
    ``quote_identifier``, which escapes quotes for the backend.
    """
    if not name or not name.strip():
        raise IdentifierError(f"Empty {what}.")
    if not _IDENT_ANY_RE.match(name):
        raise IdentifierError(
            f"Invalid {what} {name!r}: control characters and double quotes "
            "are not allowed."
        )
    return name


def is_simple_identifier(name: str) -> bool:
    """True when the name needs no quoting on any supported backend."""
    return bool(_IDENT_RE.match(name))


# ---------------------------------------------------------------------------
# Spec parsing


@dataclass
class ConnectionSpec:
    kind: str  # duckdb | files | postgresql | mysql
    original: str  # what the user passed
    display: str  # redacted for logs/reports
    url: str | None = None  # sqlalchemy URL (sql backends)
    path: Path | None = None  # duckdb file
    files: list[Path] | None = None  # csv/parquet/json files
    schema: str | None = None  # non-default schema/database for sql backends


# Query-string keys whose values must never be printed or persisted.
_SECRET_QUERY_KEYS = (
    "password", "passwd", "pwd", "secret", "token", "api_key", "apikey",
    "access_token", "auth", "credential", "credentials", "sslkey",
)


def _is_secret_query_key(key: str) -> bool:
    lowered = key.lower()
    return any(secret in lowered for secret in _SECRET_QUERY_KEYS)


def redact_url(url: str) -> str:
    """Mask userinfo passwords AND secret query parameters for display.

    ``postgresql://u@h/db?password=s3cret`` is as sensitive as
    ``postgresql://u:s3cret@h/db``; both forms are used in the wild, so both
    are redacted. Non-secret parameters (``sslmode=require``) are kept so the
    display still describes the connection.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid-url>"

    query_pairs = parse_qsl(parts.query, keep_blank_values=True) if parts.query else []
    redacted_query = "&".join(
        f"{key}=***" if _is_secret_query_key(key) else f"{key}={value}"
        for key, value in query_pairs
    )
    has_secret_query = any(_is_secret_query_key(k) for k, _ in query_pairs)
    if parts.password is None and not has_secret_query:
        return url

    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    if parts.username and parts.password is not None:
        userinfo = f"{parts.username}:***@"
    elif parts.username:
        userinfo = f"{parts.username}@"
    elif parts.password is not None:
        userinfo = "***@"
    else:
        userinfo = ""
    base = f"{parts.scheme}://{userinfo}{host}{parts.path}"
    return f"{base}?{redacted_query}" if redacted_query else base


def _sql_url(spec: str) -> tuple[str, str, str | None]:
    """Normalize a SQL URL to (kind, sqlalchemy_url, schema)."""
    parts = urlsplit(spec)
    scheme = parts.scheme.lower()
    if scheme in ("postgres", "postgresql"):
        kind = "postgresql"
        url = spec.replace(f"{parts.scheme}://", "postgresql://", 1)
    elif scheme in ("mysql", "mysql+pymysql"):
        kind = "mysql"
        url = spec.replace(f"{scheme}://", "mysql+pymysql://", 1)
    else:
        raise DatasourceError(
            f"Unsupported database scheme {scheme!r} in {redact_url(spec)}. "
            "Supported: postgresql://, mysql://, DuckDB file path, "
            "CSV/Parquet/JSON file or directory."
        )
    schema = None
    query = parts.query
    match = re.search(r"(?:^|&)schema=([^&]+)", query) if query else None
    if match:
        schema = match.group(1)
        cleaned = re.sub(r"(?:^|&)schema=[^&]*", "", query).strip("&")
        base = url.rsplit("?", 1)[0]
        if kind == "mysql":  # fold schema into the URL database segment
            base = base.rstrip("/") + "/" + schema
            schema = None
        url = f"{base}?{cleaned}" if cleaned else base
    return kind, url, schema


def parse_spec(spec: str, base_dir: Path | None = None) -> ConnectionSpec:
    """Parse a datasource string into a ConnectionSpec (light I/O for dirs)."""
    spec = spec.strip()
    if not spec:
        raise DatasourceError("Empty datasource spec.")
    if "://" in spec:
        kind, url, schema = _sql_url(spec)
        return ConnectionSpec(
            kind=kind, original=spec, display=redact_url(spec), url=url, schema=schema
        )

    path = Path(spec)
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    suffix = path.suffix.lower()
    if suffix in (".duckdb", ".db", ".ddb"):
        return ConnectionSpec(kind="duckdb", original=spec, display=str(path), path=path)
    if suffix in FILE_EXTENSIONS:
        if not path.is_file():
            raise DatasourceError(f"File not found: {path}")
        return ConnectionSpec(kind="files", original=spec, display=str(path), files=[path])
    if path.is_dir():
        files = sorted(p for p in path.iterdir() if p.suffix.lower() in FILE_EXTENSIONS)
        if not files:
            raise DatasourceError(f"No CSV/Parquet/JSON files found in {path}.")
        return ConnectionSpec(kind="files", original=spec, display=str(path), files=files)
    implied = path.with_suffix(".duckdb")
    if implied.exists():
        return ConnectionSpec(
            kind="duckdb", original=spec, display=str(implied), path=implied
        )
    raise DatasourceError(
        f"Cannot resolve datasource {spec!r}: not a URL, and no matching "
        "DuckDB file or CSV/Parquet/JSON file/directory exists."
    )


# ---------------------------------------------------------------------------
# Registry (.dqdoctor.yml datasources section)


@dataclass
class Registry:
    datasources: dict[str, str] = field(default_factory=dict)
    default: str | None = None


def load_registry(path: Path) -> Registry:
    import yaml

    if not path.exists():
        return Registry()
    data = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    datasources = data.get("datasources") or {}
    if not isinstance(datasources, dict):
        raise DatasourceError("'datasources' in config must be a name -> spec mapping.")
    return Registry(
        datasources={str(k): str(v) for k, v in datasources.items()},
        default=data.get("default"),
    )


# ---------------------------------------------------------------------------
# Connection: lifecycle, identifiers, session settings.


class Connection:
    """Backend-agnostic connection handle.

    Attributes used by ``dqdoctor.queries``: ``backend`` (duckdb /
    postgresql / mysql), ``source_kind`` (duckdb / files / postgresql /
    mysql), ``sql_schema`` (schema for postgresql), ``mysql_schema``
    (explicit database for mysql, None = current database), ``_raw`` (the
    driver connection) and ``query_count`` (instrumentation).
    """

    def __init__(self, raw: Any, backend: str, source_kind: str | None = None,
                 sql_schema: str = "public", mysql_schema: str | None = None):
        self._raw = raw
        self.backend = backend
        self.source_kind = source_kind or backend
        self.sql_schema = sql_schema
        self.mysql_schema = mysql_schema
        self.query_count = 0

    # -- Identifiers -------------------------------------------------------

    def quote_identifier(self, name: str, what: str = "identifier") -> str:
        """Quote a name for this backend, escaping the quote character.

        ``validate_identifier`` rejects control characters and double quotes;
        escaping here is defence in depth and makes CJK/hyphen/space names
        usable (0.7 supported them, an earlier 1.0 draft did not).
        """
        validate_identifier(name, what)
        if self.backend == "mysql":
            return "`" + name.replace("`", "``") + "`"
        return '"' + name.replace('"', '""') + '"'

    def quote_qualified(self, table: str, schema: str | None = None) -> str:
        parts = []
        if schema:
            parts.append(self.quote_identifier(schema, "schema name"))
        parts.append(self.quote_identifier(table, "table name"))
        return ".".join(parts)

    def table_ref(self, table: str) -> str:
        """Quoted table reference for this connection's scope."""
        if self.backend == "postgresql":
            return self.quote_qualified(table, self.sql_schema)
        return self.quote_identifier(table, "table name")

    # -- Session settings ---------------------------------------------------

    def enforce_read_only(self) -> None:
        """Session-level read-only enforcement for custom SQL rules."""
        if self.backend == "postgresql":
            self.query_count += 1
            self._raw.exec_driver_sql(
                "SELECT set_config('default_transaction_read_only', 'on', false)"
            )
        elif self.backend == "mysql":
            self.query_count += 1
            self._raw.exec_driver_sql("SET SESSION TRANSACTION READ ONLY")

    def set_statement_timeout(self, seconds: float) -> None:
        if seconds <= 0:
            return
        self.query_count += 1
        if self.backend == "postgresql":
            self._raw.exec_driver_sql(
                "SELECT set_config('statement_timeout', %s, false)",
                (str(int(seconds * 1000)),),
            )
        elif self.backend == "mysql":
            self._raw.exec_driver_sql(
                "SET SESSION max_execution_time = %s", (int(seconds * 1000),)
            )
        # duckdb: the SQL-rule executor interrupts via a watchdog thread.

    def interrupt(self) -> None:
        if self.backend == "duckdb":
            try:
                self._raw.interrupt()
            except Exception:  # pragma: no cover - best effort
                pass

    def close(self) -> None:
        try:
            if self.backend != "duckdb":
                engine = self._raw.engine
                self._raw.close()
                engine.dispose()
            else:
                self._raw.close()
        except Exception:  # pragma: no cover
            pass


# ---------------------------------------------------------------------------
# Data sources


class DataSource:
    """A resolved datasource: opens connections and lists tables."""

    def __init__(self, spec: ConnectionSpec):
        self.spec = spec
        if spec.kind in ("postgresql", "mysql"):
            try:
                import sqlalchemy  # noqa: F401

                self._sqlalchemy = True
            except ImportError as exc:
                raise DatasourceError(
                    "SQLAlchemy is required for PostgreSQL/MySQL. "
                    "Install with: pip install 'dq-doctor[sql]'"
                ) from exc

    @property
    def kind(self) -> str:
        return self.spec.kind

    def describe(self) -> str:
        """Redacted form, for display only (never persisted, never reconnected)."""
        return self.spec.display

    def safe_persistent_ref(self) -> str:
        """Datasource reference that is safe to write into a contract file.

        URL datasources **always** yield the redacted form - userinfo
        passwords and secret query parameters alike - and the real URL is
        supplied at check time via ``--db`` or an alias. Local paths are
        stored absolute: a contract that lives in another directory (or is
        moved) must still find its database.
        """
        if self.spec.kind in ("postgresql", "mysql"):
            return redact_url(self.spec.original)
        if self.spec.path is not None:
            return str(self.spec.path.resolve())
        if self.spec.files:
            parents = {f.resolve().parent for f in self.spec.files}
            if len(parents) == 1:
                return str(parents.pop())
        return self.spec.original

    def requires_secret_handling(self) -> bool:
        """True when the datasource embeds credentials anywhere in the URL."""
        if self.spec.kind not in ("postgresql", "mysql"):
            return False
        return redact_url(self.spec.original) != self.spec.original

    def open(self, read_only: bool = True) -> Connection:
        """Open a connection.

        DuckDB files are always opened with ``enable_external_access=false``:
        every table lives inside the file, so nothing legitimate needs file
        or network access, and it makes operator SQL unable to read paths via
        ``query_table``/``glob``/replacement scans. File datasources are the
        exception - their views re-read the file per query.
        """
        if self.spec.kind == "duckdb":
            path = self.spec.path
            if read_only and (path is None or not path.exists()):
                raise DatasourceError(
                    f"DuckDB database not found: {path}. "
                    "Create one with `dqdoctor demo` or point --db at an existing file."
                )
            import duckdb

            # DuckDB forbids opening the same file twice with different
            # configurations, so the restriction has to be decided once, at
            # open time. A DuckDB file needs no external access once attached:
            # every table is inside it. Blocking file/network access here means
            # operator SQL cannot escape via query_table/glob/replacement
            # scans even if the shape policy is bypassed.
            raw = duckdb.connect(
                str(path),
                read_only=read_only,
                config={"enable_external_access": "false"},
            )
            return Connection(raw, "duckdb")

        if self.spec.kind == "files":
            import duckdb

            raw = duckdb.connect(":memory:")
            con = Connection(raw, "duckdb", source_kind="files")
            names = register_file_views(raw, self.spec.files or [])
            con.query_count = len(names)
            # NOTE: external access must stay enabled here. DuckDB views over
            # CSV/Parquet re-read the file on every query, so disabling it
            # would block the datasource's own tables. SQL rules on file
            # sources rely on the shape policy instead; this is documented in
            # docs/limitations.md.
            return con

        from sqlalchemy import create_engine

        connect_args: dict[str, Any] = {}
        # Read-only is a *request*, not a constant: `open(read_only=False)` is
        # used by fixtures and maintenance tooling, and hardcoding the session
        # flag made those connections read-only too (PostgreSQL then refused
        # even DROP TABLE IF EXISTS).
        if self.spec.kind == "postgresql" and read_only:
            connect_args["options"] = "-c default_transaction_read_only=on"
        engine = create_engine(self.spec.url, connect_args=connect_args)
        con = Connection(
            engine.connect(),
            self.spec.kind,
            sql_schema=self.spec.schema or "public",
            mysql_schema=self.spec.schema,
        )
        if self.spec.kind == "mysql" and read_only:
            con.enforce_read_only()
        if self.spec.kind == "postgresql" and self.spec.schema:
            validate_identifier(self.spec.schema, "schema")
            con.query_count += 1
            con._raw.exec_driver_sql(
                "SELECT set_config('search_path', %s, false)", (self.spec.schema,)
            )
        return con

    def tables(self) -> list[str]:
        if self.spec.kind == "files":
            from dqdoctor.fileviews import unique_view_name

            # Same collision resolution as register_file_views, so listed
            # names match the views that actually exist.
            names: list[str] = []
            taken: set[str] = set()
            for f in self.spec.files or []:
                name = unique_view_name(f, taken)
                taken.add(name)
                names.append(name)
            return names
        from dqdoctor import queries

        con = self.open(read_only=True)
        try:
            return queries.list_tables(con)
        finally:
            con.close()

    def columns(self, table: str) -> list[dict]:
        from dqdoctor import queries

        con = self.open(read_only=True)
        try:
            return queries.table_columns(con, table)
        finally:
            con.close()

    def dialect(self) -> dict:
        if self.spec.kind in ("duckdb", "files"):
            return {"regex": "duckdb"}
        if self.spec.kind == "postgresql":
            return {"regex": "postgresql"}
        return {"regex": "mysql"}


def resolve(
    spec: str,
    config_path: Path | None = None,
    base_dir: Path | None = None,
) -> DataSource:
    """Resolve a CLI/config datasource string (alias, URL, path, or default).

    An empty ``spec`` falls back to the registry's ``default`` alias, which
    is what makes `dqdoctor init` followed by `check --config` work.
    """
    registry = load_registry(config_path if config_path else Path(".dqdoctor.yml"))
    if not spec and registry.default:
        spec = registry.default
    resolved = registry.datasources.get(spec, spec)
    if not resolved:
        available = ", ".join(sorted(registry.datasources)) or "none"
        raise DatasourceError(
            "Empty datasource spec: pass --db, or set 'default:' in the config "
            f"(registered aliases: {available})."
        )
    return DataSource(parse_spec(resolved, base_dir=base_dir))
