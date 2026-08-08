"""Typed boundaries shared by the GraphFixture core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

type Scalar = str | int | float | bool | date | Decimal | None
type Row = dict[str, Scalar]


class StageStatus(StrEnum):
    """A stage state displayed by every GraphFixture surface."""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    data_type: str
    nullable: bool = True


@dataclass(frozen=True)
class TableSpec:
    name: str
    urn: str
    columns: tuple[ColumnSpec, ...]


@dataclass(frozen=True)
class LineageEdge:
    upstream: str
    downstream: str


@dataclass(frozen=True)
class ContractSpec:
    contract_id: str
    title: str
    source_urn: str
    target_table: str
    key_field: str
    status_field: str
    active_value: str


@dataclass(frozen=True)
class ContextSnapshot:
    captured_at: str
    source_mode: str
    tables: tuple[TableSpec, ...]
    lineage: tuple[LineageEdge, ...]
    contract: ContractSpec

    def table(self, name: str) -> TableSpec:
        for table in self.tables:
            if table.name == name:
                return table
        raise KeyError(name)


@dataclass(frozen=True)
class FixtureSet:
    seed: int
    tables: dict[str, tuple[Row, ...]]

    def rows(self, table_name: str) -> tuple[Row, ...]:
        try:
            return self.tables[table_name]
        except KeyError as exc:
            raise KeyError(f"fixture table is missing: {table_name}") from exc


@dataclass(frozen=True)
class ExecutionResult:
    columns: tuple[str, ...]
    rows: tuple[Row, ...]
    sql_digest: str


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    contract_id: str
    title: str
    source_urn: str
    expected_ids: tuple[str, ...]
    actual_ids: tuple[str, ...]
    missing_ids: tuple[str, ...]
    unexpected_ids: tuple[str, ...]
    duplicate_ids: tuple[str, ...]
    reproducer: dict[str, tuple[Row, ...]]


@dataclass(frozen=True)
class CoreRun:
    context: ContextSnapshot
    fixtures: FixtureSet
    execution: ExecutionResult
    verification: VerificationResult
    stages: dict[str, StageStatus]
