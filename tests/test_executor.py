from dataclasses import replace
from pathlib import Path

import pytest

from graphfixture.executor import DuckDBExecutor, UnsafeTransformationError
from graphfixture.generator import RelationalFixtureGenerator
from graphfixture.models import ColumnSpec, FixtureSet, TableSpec
from graphfixture.scenario import fiction_retail_context

SQL_DIR = Path(__file__).parents[1] / "examples" / "sql"


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "DELETE FROM customers",
        "SELECT 1; SELECT 2",
        "-- only a comment",
        "/* only a comment */",
    ],
)
def test_unsafe_transformations_are_rejected(sql: str) -> None:
    context = fiction_retail_context()
    fixtures = RelationalFixtureGenerator().generate(context, 42)

    with pytest.raises(UnsafeTransformationError):
        DuckDBExecutor().run(sql, context, fixtures)


def test_unsupported_datahub_type_is_rejected() -> None:
    context = fiction_retail_context()
    unsupported_table = TableSpec(
        name="locations",
        urn="urn:li:dataset:(urn:li:dataPlatform:postgres,fiction_retail.locations,PROD)",
        columns=(ColumnSpec("point", "geography"),),
    )
    bad_context = replace(context, tables=(*context.tables, unsupported_table))
    generated = RelationalFixtureGenerator().generate(bad_context, 42)
    fixtures = FixtureSet(
        seed=generated.seed,
        tables={**generated.tables, "locations": ()},
    )

    with pytest.raises(UnsafeTransformationError, match="geography"):
        DuckDBExecutor().run("SELECT * FROM customers", bad_context, fixtures)


def test_unsafe_identifier_is_rejected() -> None:
    context = fiction_retail_context()
    first = context.tables[0]
    bad_first = replace(
        first,
        columns=(ColumnSpec("customer-id", "string", nullable=False), *first.columns[1:]),
    )
    bad_context = replace(context, tables=(bad_first, *context.tables[1:]))
    fixtures = RelationalFixtureGenerator().generate(context, 42)

    with pytest.raises(UnsafeTransformationError, match="customer-id"):
        DuckDBExecutor().run("SELECT 1", bad_context, fixtures)


def test_single_select_executes_and_returns_typed_rows() -> None:
    context = fiction_retail_context()
    fixtures = RelationalFixtureGenerator().generate(context, 42)
    sql = (SQL_DIR / "customer_order_summary_fixed.sql").read_text()

    result = DuckDBExecutor().run(sql, context, fixtures)

    assert result.columns == ("customer_id", "name", "order_count")
    assert len(result.rows) == 3
    assert len(result.sql_digest) == 64


def test_nullable_datahub_columns_are_loaded_as_null_when_fixture_lacks_them() -> None:
    context = fiction_retail_context()
    customers = context.table("customers")
    extended = replace(
        customers,
        columns=(*customers.columns, ColumnSpec("email", "string", nullable=True)),
    )
    extended_context = replace(context, tables=(extended, *context.tables[1:]))
    fixtures = RelationalFixtureGenerator().generate(context, 42)

    result = DuckDBExecutor().run(
        "SELECT customer_id, email FROM customers", extended_context, fixtures
    )

    assert result.rows[0]["email"] is None
