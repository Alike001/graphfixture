"""Network-free reconstruction and replay of GraphFixture evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from graphfixture.evidence import (
    EvidenceBundle,
    EvidenceFormatError,
    JsonValue,
    to_json_value,
    verify_evidence,
)
from graphfixture.executor import DuckDBExecutor
from graphfixture.models import (
    ColumnSpec,
    ContextSnapshot,
    ContractSpec,
    FixtureSet,
    LineageEdge,
    Row,
    TableSpec,
)
from graphfixture.verifier import verify_active_customers


@dataclass(frozen=True)
class ReplayResult:
    execution_matches: bool
    verification_matches: bool
    reproduced_verdict: bool

    @property
    def passed(self) -> bool:
        return self.execution_matches and self.verification_matches


def replay_evidence(bundle: EvidenceBundle) -> ReplayResult:
    """Verify the digest, re-execute SQL, and compare stored outcomes."""

    verify_evidence(bundle)
    payload = bundle.payload
    if payload.get("schema_version") != "1.0":
        raise EvidenceFormatError("unsupported evidence schema version")
    sql = _string(payload.get("sql"), "sql")
    context = _context(_object(payload.get("context"), "context"))
    fixtures = _fixtures(_object(payload.get("fixtures"), "fixtures"), context)
    execution = DuckDBExecutor().run(sql, context, fixtures)
    verification = verify_active_customers(context, fixtures, execution)
    stored_execution = _object(payload.get("execution"), "execution")
    stored_verification = _object(payload.get("verification"), "verification")
    return ReplayResult(
        execution_matches=to_json_value(execution) == stored_execution,
        verification_matches=to_json_value(verification) == stored_verification,
        reproduced_verdict=verification.passed,
    )


def _context(raw: dict[str, JsonValue]) -> ContextSnapshot:
    tables = tuple(_table(_object(item, "table")) for item in _array(raw.get("tables"), "tables"))
    lineage = tuple(
        LineageEdge(
            upstream=_string(_object(item, "lineage").get("upstream"), "upstream"),
            downstream=_string(_object(item, "lineage").get("downstream"), "downstream"),
        )
        for item in _array(raw.get("lineage"), "lineage")
    )
    contract = _object(raw.get("contract"), "contract")
    return ContextSnapshot(
        captured_at=_string(raw.get("captured_at"), "captured_at"),
        source_mode=_string(raw.get("source_mode"), "source_mode"),
        tables=tables,
        lineage=lineage,
        contract=ContractSpec(
            contract_id=_string(contract.get("contract_id"), "contract_id"),
            title=_string(contract.get("title"), "title"),
            source_urn=_string(contract.get("source_urn"), "source_urn"),
            target_table=_string(contract.get("target_table"), "target_table"),
            key_field=_string(contract.get("key_field"), "key_field"),
            status_field=_string(contract.get("status_field"), "status_field"),
            active_value=_string(contract.get("active_value"), "active_value"),
        ),
        mcp_response_digest=_optional_string(raw.get("mcp_response_digest")),
    )


def _table(raw: dict[str, JsonValue]) -> TableSpec:
    columns = tuple(
        ColumnSpec(
            name=_string(column.get("name"), "column name"),
            data_type=_string(column.get("data_type"), "column type"),
            nullable=_boolean(column.get("nullable"), "column nullable"),
        )
        for item in _array(raw.get("columns"), "columns")
        for column in [_object(item, "column")]
    )
    return TableSpec(
        name=_string(raw.get("name"), "table name"),
        urn=_string(raw.get("urn"), "table urn"),
        columns=columns,
    )


def _fixtures(raw: dict[str, JsonValue], context: ContextSnapshot) -> FixtureSet:
    raw_tables = _object(raw.get("tables"), "fixture tables")
    tables: dict[str, tuple[Row, ...]] = {}
    for table in context.tables:
        rows = _array(raw_tables.get(table.name), f"fixture {table.name}")
        column_types = {column.name: column.data_type for column in table.columns}
        tables[table.name] = tuple(
            _fixture_row(_object(item, "fixture row"), column_types) for item in rows
        )
    seed = raw.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise EvidenceFormatError("evidence seed must be an integer")
    return FixtureSet(seed=seed, tables=tables)


def _fixture_row(raw: dict[str, JsonValue], column_types: dict[str, str]) -> Row:
    unknown = sorted(raw.keys() - column_types.keys())
    missing = sorted(column_types.keys() - raw.keys())
    if unknown:
        raise EvidenceFormatError(f"unknown fixture columns: {', '.join(unknown)}")
    if missing:
        raise EvidenceFormatError(f"missing fixture columns: {', '.join(missing)}")
    return {key: _scalar(value, column_types[key]) for key, value in raw.items()}


def _scalar(value: JsonValue, data_type: str) -> str | int | float | bool | date | Decimal | None:
    if value is None:
        return None
    if data_type == "date" and isinstance(value, str):
        return date.fromisoformat(value)
    if data_type == "decimal" and isinstance(value, str):
        return Decimal(value)
    if data_type == "string" and isinstance(value, str):
        return value
    if data_type == "integer" and isinstance(value, int) and not isinstance(value, bool):
        return value
    if data_type == "boolean" and isinstance(value, bool):
        return value
    raise EvidenceFormatError(f"invalid {data_type} fixture value: {value!r}")


def _object(value: JsonValue | None, field: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise EvidenceFormatError(f"evidence {field} must be an object")
    return value


def _array(value: JsonValue | None, field: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise EvidenceFormatError(f"evidence {field} must be an array")
    return value


def _string(value: JsonValue | None, field: str) -> str:
    if not isinstance(value, str):
        raise EvidenceFormatError(f"evidence {field} must be a string")
    return value


def _boolean(value: JsonValue | None, field: str) -> bool:
    if not isinstance(value, bool):
        raise EvidenceFormatError(f"evidence {field} must be a boolean")
    return value


def _optional_string(value: JsonValue | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EvidenceFormatError("evidence mcp_response_digest must be a string")
    return value
