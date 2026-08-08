"""Sponsor-safe fiction-retail context used by the first product slice."""

from graphfixture.models import (
    ColumnSpec,
    ContextSnapshot,
    ContractSpec,
    LineageEdge,
    TableSpec,
)


def _dataset_urn(name: str) -> str:
    return f"urn:li:dataset:(urn:li:dataPlatform:postgres,fiction_retail.{name},PROD)"


def fiction_retail_context() -> ContextSnapshot:
    """Return a captured context with the same shape as the live DataHub adapter."""

    customers = TableSpec(
        name="customers",
        urn=_dataset_urn("customers"),
        columns=(
            ColumnSpec("customer_id", "string", nullable=False),
            ColumnSpec("name", "string", nullable=False),
            ColumnSpec("status", "string", nullable=False),
            ColumnSpec("created_at", "date", nullable=False),
        ),
    )
    orders = TableSpec(
        name="orders",
        urn=_dataset_urn("orders"),
        columns=(
            ColumnSpec("order_id", "string", nullable=False),
            ColumnSpec("customer_id", "string", nullable=False),
            ColumnSpec("order_date", "date", nullable=False),
            ColumnSpec("status", "string", nullable=False),
        ),
    )
    order_items = TableSpec(
        name="order_items",
        urn=_dataset_urn("order_items"),
        columns=(
            ColumnSpec("order_id", "string", nullable=False),
            ColumnSpec("item_id", "string", nullable=False),
            ColumnSpec("quantity", "integer", nullable=False),
            ColumnSpec("unit_price", "decimal", nullable=False),
        ),
    )
    target_urn = _dataset_urn("customer_order_summary")
    return ContextSnapshot(
        captured_at="2026-08-08T12:00:00Z",
        source_mode="captured",
        tables=(customers, orders, order_items),
        lineage=tuple(
            LineageEdge(table.urn, target_urn) for table in (customers, orders, order_items)
        ),
        contract=ContractSpec(
            contract_id="active-customers-present",
            title="Every active customer must appear",
            source_urn="urn:li:document:graphfixture-active-customers",
            target_table="customer_order_summary",
            key_field="customer_id",
            status_field="status",
            active_value="active",
        ),
    )
