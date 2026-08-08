"""Isolated DuckDB execution for repository-controlled transformations."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

import duckdb

from graphfixture.models import ContextSnapshot, ExecutionResult, FixtureSet, Row, TableSpec

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DUCKDB_TYPES = {
    "string": "VARCHAR",
    "integer": "INTEGER",
    "decimal": "DECIMAL(18, 2)",
    "date": "DATE",
    "boolean": "BOOLEAN",
}


class UnsafeTransformationError(ValueError):
    """Raised when a transformation is outside the repository SQL boundary."""


class DuckDBExecutor:
    """Execute one read-only transformation in an ephemeral database."""

    def run(
        self,
        sql: str,
        context: ContextSnapshot,
        fixtures: FixtureSet,
    ) -> ExecutionResult:
        normalized = self._validate_sql(sql)
        connection = duckdb.connect(
            database=":memory:",
            config={
                "enable_external_access": "false",
                "memory_limit": "256MB",
                "threads": "1",
            },
        )
        try:
            for table in context.tables:
                self._load_table(connection, table, fixtures.rows(table.name))
            cursor = connection.execute(normalized)
            columns = tuple(item[0] for item in cursor.description)
            rows = tuple(dict(zip(columns, values, strict=True)) for values in cursor.fetchall())
        finally:
            connection.close()
        return ExecutionResult(
            columns=columns,
            rows=rows,
            sql_digest=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        )

    @staticmethod
    def _validate_sql(sql: str) -> str:
        normalized = sql.strip()
        if not normalized:
            raise UnsafeTransformationError("transformation SQL is empty")
        body = normalized[:-1].rstrip() if normalized.endswith(";") else normalized
        if ";" in body:
            raise UnsafeTransformationError("only one SQL statement is allowed")
        without_comments = re.sub(r"^\s*(?:(?:--[^\n]*\n)|(?:/\*.*?\*/\s*))*", "", body, flags=re.S)
        tokens = without_comments.lstrip().split(maxsplit=1)
        if not tokens:
            raise UnsafeTransformationError("transformation SQL contains only comments")
        first_word = tokens[0].upper()
        if first_word not in {"SELECT", "WITH"}:
            raise UnsafeTransformationError("transformation must be a SELECT or WITH query")
        return body

    def _load_table(
        self,
        connection: duckdb.DuckDBPyConnection,
        table: TableSpec,
        rows: Iterable[Row],
    ) -> None:
        table_name = self._identifier(table.name)
        definitions = []
        column_names = []
        for column in table.columns:
            name = self._identifier(column.name)
            try:
                data_type = DUCKDB_TYPES[column.data_type]
            except KeyError as exc:
                raise UnsafeTransformationError(
                    f"unsupported DataHub type for {table.name}.{column.name}: {column.data_type}"
                ) from exc
            nullability = "" if column.nullable else " NOT NULL"
            definitions.append(f'"{name}" {data_type}{nullability}')
            column_names.append(name)
        connection.execute(f'CREATE TABLE "{table_name}" ({", ".join(definitions)})')
        values = [tuple(row[name] for name in column_names) for row in rows]
        if values:
            placeholders = ", ".join("?" for _ in column_names)
            connection.executemany(
                f'INSERT INTO "{table_name}" VALUES ({placeholders})',
                values,
            )

    @staticmethod
    def _identifier(value: str) -> str:
        if not IDENTIFIER.fullmatch(value):
            raise UnsafeTransformationError(f"unsafe SQL identifier: {value}")
        return value
