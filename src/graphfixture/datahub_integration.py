"""Live DataHub context reads and verified receipt write-back."""

from __future__ import annotations

from datahub.errors import ItemNotFoundError
from datahub.metadata.urns import DatasetUrn, DocumentUrn
from datahub.sdk.dataset import Dataset, SchemaField
from datahub.sdk.document import Document
from datahub.sdk.main_client import DataHubClient

from graphfixture.mcp_integration import DataHubMcpClient
from graphfixture.models import (
    ColumnSpec,
    ContextSnapshot,
    ContractSpec,
    LineageEdge,
    TableSpec,
)


class DataHubContextError(RuntimeError):
    """Raised when live DataHub context is missing or incompatible."""


class DataHubContextReader:
    """Build GraphFixture context from a DataHub contract Document and graph."""

    def __init__(self, client: DataHubClient, mcp_client: DataHubMcpClient | None = None) -> None:
        self.client = client
        self.mcp_client = mcp_client

    def read(self, contract_document_id: str) -> ContextSnapshot:
        contract_doc = self.client.entities.get(DocumentUrn(contract_document_id))
        if not isinstance(contract_doc, Document):
            raise DataHubContextError("DataHub contract entity is not a Document")
        properties = contract_doc.custom_properties or {}
        if not contract_doc.title:
            raise DataHubContextError("DataHub contract title is missing")
        target_urn = _property(properties, "target_urn")
        source_urns = tuple(
            sorted(asset for asset in contract_doc.related_assets or [] if asset != target_urn)
        )
        if not source_urns:
            raise DataHubContextError("DataHub contract has no related source datasets")

        mcp_response_digest = None
        if self.mcp_client is not None:
            try:
                mcp_response_digest = self.mcp_client.attest_lineage(
                    target_urn, source_urns
                ).response_digest
            except Exception as exc:
                raise DataHubContextError(f"DataHub MCP lineage attestation failed: {exc}") from exc

        tables = tuple(self._read_table(urn) for urn in source_urns)
        upstreams = {
            result.urn
            for result in self.client.lineage.get_lineage(
                source_urn=target_urn,
                direction="upstream",
                max_hops=1,
            )
        }
        missing_lineage = sorted(set(source_urns) - upstreams)
        if missing_lineage:
            raise DataHubContextError(
                f"DataHub lineage is missing sources: {', '.join(missing_lineage)}"
            )
        return ContextSnapshot(
            captured_at=_property(properties, "context_captured_at"),
            source_mode="datahub-live+mcp" if self.mcp_client is not None else "datahub-live",
            tables=tables,
            lineage=tuple(LineageEdge(urn, target_urn) for urn in source_urns),
            contract=ContractSpec(
                contract_id=_property(properties, "contract_id"),
                title=contract_doc.title,
                source_urn=str(contract_doc.urn),
                target_table=_property(properties, "target_table"),
                key_field=_property(properties, "key_field"),
                status_field=_property(properties, "status_field"),
                active_value=_property(properties, "active_value"),
            ),
            mcp_response_digest=mcp_response_digest,
        )

    def _read_table(self, urn: str) -> TableSpec:
        dataset = self.client.entities.get(DatasetUrn.from_string(urn))
        if not isinstance(dataset, Dataset):
            raise DataHubContextError(f"DataHub source is not a Dataset: {urn}")
        try:
            fields = dataset.schema
        except ItemNotFoundError as exc:
            raise DataHubContextError(f"DataHub dataset has no schema: {urn}") from exc
        columns = tuple(
            ColumnSpec(
                name=field.field_path,
                data_type=_data_type(field),
                nullable=_nullable(field),
            )
            for field in fields
        )
        if not columns:
            raise DataHubContextError(f"DataHub dataset has no schema: {urn}")
        return TableSpec(
            name=dataset.urn.name.split(".")[-1],
            urn=str(dataset.urn),
            columns=columns,
        )


def datahub_client() -> DataHubClient:
    """Use standard DataHub environment and CLI configuration."""

    return DataHubClient.from_env()


def _data_type(field: SchemaField) -> str:
    native = field.native_type.lower()
    native_rules = (
        (("bool",), "boolean"),
        (("date",), "date"),
        (("int",), "integer"),
        (("decimal", "numeric", "number", "float", "double", "real"), "decimal"),
        (("char", "text", "string", "varchar"), "string"),
    )
    for needles, normalized in native_rules:
        if any(needle in native for needle in needles):
            return normalized
    mapped = type(field.mapped_type.type).__name__
    mapped_types = {
        "BooleanTypeClass": "boolean",
        "DateTypeClass": "date",
        "NumberTypeClass": "decimal",
        "StringTypeClass": "string",
    }
    try:
        return mapped_types[mapped]
    except KeyError as exc:
        raise DataHubContextError(
            f"unsupported DataHub type for {field.field_path}: {field.native_type}"
        ) from exc


def _nullable(field: SchemaField) -> bool:
    """SDK 1.7.0 has not exposed nullability on SchemaField yet."""

    return field._base_schema_field().nullable


def _property(properties: dict[str, str], name: str) -> str:
    value = properties.get(name)
    if not value:
        raise DataHubContextError(f"DataHub contract property is missing: {name}")
    return value
