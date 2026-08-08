from dataclasses import replace

import pytest

from graphfixture.generator import (
    ContextError,
    RelationalFixtureGenerator,
    validate_fixture_relationships,
)
from graphfixture.models import FixtureSet
from graphfixture.scenario import fiction_retail_context


def test_generation_is_deterministic_for_the_same_seed() -> None:
    generator = RelationalFixtureGenerator()
    context = fiction_retail_context()

    assert generator.generate(context, 42) == generator.generate(context, 42)
    assert generator.generate(context, 42) != generator.generate(context, 43)


def test_generated_fixture_preserves_relations_and_zero_order_case() -> None:
    fixtures = RelationalFixtureGenerator().generate(fiction_retail_context(), 42)

    validate_fixture_relationships(fixtures)
    order_customers = {str(row["customer_id"]) for row in fixtures.rows("orders")}
    assert "C-003" not in order_customers
    assert {str(row["order_id"]) for row in fixtures.rows("order_items")} <= {
        str(row["order_id"]) for row in fixtures.rows("orders")
    }


def test_missing_required_table_fails_closed() -> None:
    context = fiction_retail_context()
    incomplete = replace(context, tables=context.tables[:-1])

    with pytest.raises(ContextError, match="order_items"):
        RelationalFixtureGenerator().generate(incomplete, 42)


def test_missing_required_column_fails_with_table_context() -> None:
    context = fiction_retail_context()
    customers = context.tables[0]
    incomplete_customers = replace(customers, columns=customers.columns[:-1])
    incomplete = replace(context, tables=(incomplete_customers, *context.tables[1:]))

    with pytest.raises(ContextError, match="customers: created_at"):
        RelationalFixtureGenerator().generate(incomplete, 42)


def test_incompatible_required_column_type_fails_closed() -> None:
    context = fiction_retail_context()
    order_items = context.tables[2]
    bad_quantity = replace(order_items.columns[2], data_type="string")
    incompatible_items = replace(
        order_items,
        columns=(*order_items.columns[:2], bad_quantity, order_items.columns[3]),
    )
    incompatible = replace(context, tables=(*context.tables[:2], incompatible_items))

    with pytest.raises(ContextError, match="quantity expected integer, got string"):
        RelationalFixtureGenerator().generate(incompatible, 42)


def test_duplicate_datahub_columns_fail_closed() -> None:
    context = fiction_retail_context()
    orders = context.tables[1]
    duplicate_orders = replace(orders, columns=(*orders.columns, orders.columns[0]))
    duplicate_context = replace(
        context,
        tables=(context.tables[0], duplicate_orders, context.tables[2]),
    )

    with pytest.raises(ContextError, match="duplicate columns.*orders"):
        RelationalFixtureGenerator().generate(duplicate_context, 42)


def test_orphaned_item_is_rejected() -> None:
    fixtures = RelationalFixtureGenerator().generate(fiction_retail_context(), 42)
    broken = FixtureSet(
        seed=fixtures.seed,
        tables={
            **fixtures.tables,
            "order_items": (
                {
                    "order_id": "O-MISSING",
                    "item_id": "I-BROKEN",
                    "quantity": 1,
                    "unit_price": 1.0,
                },
            ),
        },
    )

    with pytest.raises(ContextError, match="I-BROKEN"):
        validate_fixture_relationships(broken)


def test_orphaned_order_is_rejected() -> None:
    fixtures = RelationalFixtureGenerator().generate(fiction_retail_context(), 42)
    broken = FixtureSet(
        seed=fixtures.seed,
        tables={
            **fixtures.tables,
            "orders": (
                {
                    "order_id": "O-BROKEN",
                    "customer_id": "C-MISSING",
                    "order_date": fixtures.rows("orders")[0]["order_date"],
                    "status": "complete",
                },
            ),
            "order_items": (),
        },
    )

    with pytest.raises(ContextError, match="O-BROKEN"):
        validate_fixture_relationships(broken)


def test_missing_fixture_table_has_clear_error() -> None:
    fixtures = FixtureSet(seed=42, tables={})

    with pytest.raises(KeyError, match="fixture table is missing: customers"):
        fixtures.rows("customers")
