"""SQL access to the cashier database.

The client is deliberately small: it builds a SQLAlchemy URL from the profile,
runs statements off the event loop, and returns plain rows. PostgreSQL is the
default because that is what SetRetail ships, but any SQLAlchemy dialect works
(``dialect`` in :class:`~cashdesk_control.core.models.DatabaseSettings`).
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .models import DatabaseSettings

logger = logging.getLogger("cashdesk_control.db")

#: Statements the read-only inspector is willing to run for schema discovery.
_SAFE_DIALECTS = {"postgresql", "sqlite", "mysql", "mssql", "oracle"}


@dataclass(slots=True)
class QueryResult:
    """Rows returned by one statement."""

    sql: str
    columns: list[str] = field(default_factory=list)
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    rowcount: int = 0
    duration_ms: float = 0.0
    error: str | None = None
    is_select: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_csv(self, delimiter: str = ";") -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
        writer.writerow(self.columns)
        for row in self.rows:
            writer.writerow(["" if value is None else str(value) for value in row])
        return buffer.getvalue()

    def save_csv(self, path: str | Path, delimiter: str = ";") -> Path:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_csv(delimiter), encoding="utf-8-sig")
        return target

    def preview(self, limit: int = 12) -> str:
        if self.error:
            return self.error
        if not self.columns:
            return f"Выполнено: затронуто строк {self.rowcount}"
        widths = [len(name) for name in self.columns]
        text_rows: list[list[str]] = []
        for row in self.rows[:limit]:
            text_rows.append([("" if value is None else str(value)) for value in row])
        for row in text_rows:
            for index, cell in enumerate(row):
                widths[index] = max(widths[index], len(cell))
        line = " | ".join(name.ljust(widths[index]) for index, name in enumerate(self.columns))
        separator = "-+-".join("-" * width for width in widths)
        body = "\n".join(" | ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)) for row in text_rows)
        out = "\n".join(part for part in (line, separator, body) if part)
        if len(self.rows) > limit:
            out += f"\n… ещё {len(self.rows) - limit} строк"
        return out


@dataclass(slots=True)
class TableInfo:
    schema: str
    name: str
    kind: str = "table"
    row_estimate: int | None = None

    @property
    def qualified(self) -> str:
        if self.schema in {"", "main"}:
            return self.name
        return f"{self.schema}.{self.name}"


class DatabaseClient:
    """Execute SQL against the cashier database."""

    def __init__(self, settings: DatabaseSettings, password: str | None = None) -> None:
        self.settings = settings
        self._password = password
        self._engine: Any = None
        self._connect_args: dict[str, Any] = {}

    # -- lifecycle ----------------------------------------------------------
    @property
    def is_connected(self) -> bool:
        return self._engine is not None

    @property
    def display_url(self) -> str:
        """URL without the password, safe for the status bar."""

        base = self.settings.url(host=self.settings.host)
        if self._password:
            return base.replace(f":{self._password}@", ":***@", 1) if f":{self._password}@" in base else base
        return base

    def connect(self, *, host: str | None = None, port: int | None = None) -> None:
        """Create the engine. ``host``/``port`` point at a tunnel endpoint."""

        try:
            from sqlalchemy import create_engine
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise DatabaseError("SQLAlchemy не установлен: pip install 'cashdesk-control[db]'") from exc
        if self.settings.dialect not in _SAFE_DIALECTS:
            raise DatabaseError(f"неподдерживаемый диалект: {self.settings.dialect}")
        url = self.settings.url(self._password, host=host, port=port)
        kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}
        if self.settings.dialect == "postgresql":
            kwargs["connect_args"] = {"connect_timeout": 10}
        if self.settings.dialect == "sqlite":
            kwargs.pop("pool_pre_ping")
        self._engine = create_engine(url, **kwargs)

    def dispose(self) -> None:
        if self._engine is not None:
            try:
                self._engine.dispose()
            except Exception as exc:  # pragma: no cover - best effort
                logger.debug("engine dispose warning: %s", exc)
            self._engine = None

    async def connect_async(self, *, host: str | None = None, port: int | None = None) -> None:
        await asyncio.to_thread(self.connect, host=host, port=port)
        await self.ping_async()

    def _require_engine(self) -> Any:
        if self._engine is None:
            raise DatabaseError("нет подключения к базе данных")
        return self._engine

    # -- introspection -------------------------------------------------------
    def ping(self) -> float:
        """Round-trip the database and return the latency in milliseconds."""

        from sqlalchemy import text

        engine = self._require_engine()
        started = time.monotonic()
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        return (time.monotonic() - started) * 1000

    async def ping_async(self) -> float:
        return await asyncio.to_thread(self.ping)

    def list_tables(self, schema: str | None = None) -> list[TableInfo]:
        from sqlalchemy import inspect

        engine = self._require_engine()
        target_schema = schema or (self.settings.schema if self.settings.dialect != "sqlite" else None)
        inspector = inspect(engine)
        available = inspector.get_schema_names() if self.settings.dialect != "sqlite" else [None]
        results: list[TableInfo] = []
        schemas = [target_schema] if target_schema else list(available)
        for candidate in schemas:
            if candidate is not None and candidate not in available:
                continue
            for name in inspector.get_table_names(candidate):
                results.append(TableInfo(schema=candidate or "", name=name, kind="table"))
            for name in inspector.get_view_names(candidate):
                results.append(TableInfo(schema=candidate or "", name=name, kind="view"))
        results.sort(key=lambda item: (item.schema, item.name))
        return results

    async def list_tables_async(self, schema: str | None = None) -> list[TableInfo]:
        return await asyncio.to_thread(self.list_tables, schema)

    def list_columns(self, table: str, schema: str | None = None) -> list[dict[str, Any]]:
        from sqlalchemy import inspect

        engine = self._require_engine()
        target_schema = schema or (self.settings.schema if self.settings.dialect != "sqlite" else None)
        inspector = inspect(engine)
        return [dict(column) for column in inspector.get_columns(table, target_schema)]

    async def list_columns_async(self, table: str, schema: str | None = None) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.list_columns, table, schema)

    # -- execution -----------------------------------------------------------
    def execute(self, sql: str, *, params: dict[str, Any] | None = None) -> QueryResult:
        """Run one statement. SELECTs return rows, the rest return a row count."""

        from sqlalchemy import text

        engine = self._require_engine()
        statement = text(sql)
        started = time.monotonic()
        try:
            with engine.connect() as connection:
                cursor = connection.execute(statement, params or {})
                columns = list(cursor.keys()) if cursor.returns_rows else []
                rows = [tuple(row) for row in cursor.fetchall()] if cursor.returns_rows else []
                rowcount = int(cursor.rowcount or 0)
                if not cursor.returns_rows:
                    connection.commit()
        except Exception as exc:
            duration = (time.monotonic() - started) * 1000
            message = str(exc).split("\n")[0]
            return QueryResult(sql=sql, duration_ms=duration, error=message)
        duration = (time.monotonic() - started) * 1000
        return QueryResult(
            sql=sql,
            columns=columns,
            rows=rows,
            rowcount=rowcount if not columns else len(rows),
            duration_ms=duration,
            is_select=bool(columns),
        )

    async def execute_async(self, sql: str, *, params: dict[str, Any] | None = None) -> QueryResult:
        return await asyncio.to_thread(lambda: self.execute(sql, params=params))

    async def preview_table(self, table: str, schema: str | None = None, limit: int = 200) -> QueryResult:
        from sqlalchemy import inspect

        engine = self._require_engine()
        target_schema = schema or (self.settings.schema if self.settings.dialect != "sqlite" else None)
        inspector = inspect(engine)
        if not inspector.has_table(table, target_schema):
            return QueryResult(sql=f"select * from {table}", error=f"таблица {table} не найдена")
        qualified = f'"{target_schema}"."{table}"' if target_schema and self.settings.dialect == "postgresql" else (
            f"{target_schema}.{table}" if target_schema else table
        )
        sql = f"select * from {qualified} limit {int(limit)}"
        return await self.execute_async(sql)

    def update_row(
        self,
        table: str,
        primary_key: Sequence[str],
        key_values: Sequence[Any],
        column: str,
        value: Any,
        schema: str | None = None,
    ) -> QueryResult:
        """Update a single cell, addressed by the table primary key."""

        from sqlalchemy import text

        if len(primary_key) != len(key_values):
            return QueryResult(sql="", error="ключ и значения не совпадают по длине")
        target_schema = schema or (self.settings.schema if self.settings.dialect != "sqlite" else None)
        qualified = f"{target_schema}.{table}" if target_schema else table
        assignment = f'"{column}" = :__value'
        conditions = " and ".join(f'"{key}" = :__key_{index}' for index, key in enumerate(primary_key))
        sql = f"update {qualified} set {assignment} where {conditions}"
        params: dict[str, Any] = {"__value": value}
        params.update({f"__key_{index}": value for index, value in enumerate(key_values)})
        return self.execute(sql, params=params)

    async def update_row_async(self, *args: Any, **kwargs: Any) -> QueryResult:
        return await asyncio.to_thread(self.update_row, *args, **kwargs)


class DatabaseError(RuntimeError):
    """Raised when the database client cannot be configured or connected."""
