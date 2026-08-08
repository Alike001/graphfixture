"""Deterministic relational fixture generation."""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from graphfixture.models import ContextSnapshot, FixtureSet, Row

REQUIRED_SCHEMA = {
    "customers": {
        "customer_id": "string",
        "name": "string",
        "status": "string",
        "created_at": "date",
    },
    "orders": {
        "order_id": "string",
        "customer_id": "string",
        "order_date": "date",
        "status": "string",
    },
    "order_items": {
        "order_id": "string",
        "item_id": "string",
        "quantity": "integer",
        "unit_price": "decimal",
    },
}


class ContextError(ValueError):
    """Raised when DataHub context cannot support the requested fixture."""


class RelationalFixtureGenerator:
    """Generate a small relational fixture from validated catalog context."""

    def generate(self, context: ContextSnapshot, seed: int) -> FixtureSet:
        self._validate_context(context)
        rng = random.Random(seed)
        names = ["Alice", "Bob", "Carol", "Dan"]
        rng.shuffle(names)
        base_date = date(2024, 1, 1) + timedelta(days=rng.randint(0, 20))

        customers: tuple[Row, ...] = (
            self._customer("C-001", names[0], "active", base_date),
            self._customer("C-002", names[1], "inactive", base_date + timedelta(days=1)),
            self._customer("C-003", names[2], "active", base_date + timedelta(days=2)),
            self._customer("C-004", names[3], "active", base_date + timedelta(days=3)),
        )
        orders: tuple[Row, ...] = (
            self._order("O-1001", "C-001", base_date + timedelta(days=9)),
            self._order("O-1002", "C-001", base_date + timedelta(days=14)),
            self._order("O-1003", "C-004", base_date + timedelta(days=10)),
        )
        order_items: tuple[Row, ...] = (
            self._item("O-1001", "I-001", 1, "19.99"),
            self._item("O-1001", "I-002", 2, "9.99"),
            self._item("O-1002", "I-003", 1, "14.99"),
            self._item("O-1003", "I-004", 3, "4.99"),
        )
        fixtures = FixtureSet(
            seed=seed,
            tables={
                "customers": customers,
                "orders": orders,
                "order_items": order_items,
            },
        )
        validate_fixture_relationships(fixtures)
        return fixtures

    @staticmethod
    def _validate_context(context: ContextSnapshot) -> None:
        table_names = {table.name for table in context.tables}
        missing_tables = sorted(REQUIRED_SCHEMA.keys() - table_names)
        if missing_tables:
            raise ContextError(f"required DataHub tables are missing: {', '.join(missing_tables)}")
        for table in context.tables:
            names = [column.name for column in table.columns]
            if len(names) != len(set(names)):
                raise ContextError(f"duplicate columns in DataHub schema: {table.name}")
            if table.name not in REQUIRED_SCHEMA:
                continue
            actual = {column.name: column.data_type for column in table.columns}
            expected = REQUIRED_SCHEMA[table.name]
            missing_columns = sorted(expected.keys() - actual.keys())
            if missing_columns:
                raise ContextError(
                    f"required DataHub columns are missing from {table.name}: "
                    f"{', '.join(missing_columns)}"
                )
            incompatible = sorted(
                name for name, data_type in expected.items() if actual[name] != data_type
            )
            if incompatible:
                details = ", ".join(
                    f"{name} expected {expected[name]}, got {actual[name]}" for name in incompatible
                )
                raise ContextError(f"incompatible DataHub columns in {table.name}: {details}")

    @staticmethod
    def _customer(customer_id: str, name: str, status: str, created_at: date) -> Row:
        return {
            "customer_id": customer_id,
            "name": name,
            "status": status,
            "created_at": created_at,
        }

    @staticmethod
    def _order(order_id: str, customer_id: str, order_date: date) -> Row:
        return {
            "order_id": order_id,
            "customer_id": customer_id,
            "order_date": order_date,
            "status": "complete",
        }

    @staticmethod
    def _item(order_id: str, item_id: str, quantity: int, unit_price: str) -> Row:
        return {
            "order_id": order_id,
            "item_id": item_id,
            "quantity": quantity,
            "unit_price": Decimal(unit_price),
        }


def validate_fixture_relationships(fixtures: FixtureSet) -> None:
    """Fail if a generated foreign key points outside its parent table."""

    customer_ids = {str(row["customer_id"]) for row in fixtures.rows("customers")}
    order_ids = {str(row["order_id"]) for row in fixtures.rows("orders")}
    orphan_orders = sorted(
        str(row["order_id"])
        for row in fixtures.rows("orders")
        if str(row["customer_id"]) not in customer_ids
    )
    orphan_items = sorted(
        str(row["item_id"])
        for row in fixtures.rows("order_items")
        if str(row["order_id"]) not in order_ids
    )
    if orphan_orders or orphan_items:
        details = []
        if orphan_orders:
            details.append(f"orders={','.join(orphan_orders)}")
        if orphan_items:
            details.append(f"items={','.join(orphan_items)}")
        raise ContextError(f"fixture referential integrity failed: {'; '.join(details)}")
