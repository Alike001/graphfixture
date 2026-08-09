"""Seed the exact DataHub graph used by the GraphFixture product proof."""

from __future__ import annotations

from datahub.metadata.urns import DatasetUrn
from datahub.sdk.dataset import Dataset
from datahub.sdk.document import Document
from datahub.sdk.main_client import DataHubClient

from graphfixture.scenario import fiction_retail_context

NATIVE_TYPES = {
    "string": "varchar",
    "integer": "integer",
    "decimal": "decimal(18,2)",
    "date": "date",
    "boolean": "boolean",
}


def seed_demo_catalog(client: DataHubClient) -> tuple[str, ...]:
    """Idempotently upsert source schemas, lineage, and the business contract."""

    context = fiction_retail_context()
    source_urns: list[str] = []
    for table in context.tables:
        dataset = Dataset(
            platform="postgres",
            name=f"fiction_retail.{table.name}",
            description="Synthetic fiction-retail source for the GraphFixture proof.",
            schema=[
                (column.name, NATIVE_TYPES[column.data_type], "GraphFixture demo field")
                for column in table.columns
            ],
        )
        client.entities.upsert(dataset)
        source_urns.append(str(dataset.urn))

    target = Dataset(
        platform="postgres",
        name="fiction_retail.customer_order_summary",
        description="Active-customer order summary verified by GraphFixture.",
        schema=[
            ("customer_id", "varchar", "Customer identifier"),
            ("name", "varchar", "Customer name"),
            ("order_count", "bigint", "Distinct completed orders"),
        ],
        upstreams=[DatasetUrn.from_string(urn) for urn in source_urns],
    )
    client.entities.upsert(target)
    contract = Document.create_document(
        id="graphfixture-active-customers",
        title="Every active customer must appear",
        text=(
            "GraphFixture contract: customer_order_summary must contain exactly one row "
            "for every active customer, including customers with zero orders."
        ),
        subtype="Data Contract",
        show_in_global_context=False,
        related_assets=[*source_urns, str(target.urn)],
        custom_properties={
            "contract_id": "active-customers-present",
            "context_captured_at": context.captured_at,
            "target_urn": str(target.urn),
            "target_table": "customer_order_summary",
            "key_field": "customer_id",
            "status_field": "status",
            "active_value": "active",
        },
    )
    client.entities.upsert(contract)
    return (*source_urns, str(target.urn), str(contract.urn))
