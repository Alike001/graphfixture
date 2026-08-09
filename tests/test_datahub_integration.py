from pathlib import Path

import pytest
from datahub.sdk.dataset import Dataset
from datahub.sdk.document import Document
from datahub.sdk.lineage_client import LineageResult
from datahub.sdk.main_client import DataHubClient

from graphfixture.datahub_demo import seed_demo_catalog
from graphfixture.datahub_integration import (
    DataHubContextError,
    DataHubContextReader,
    _data_type,
    datahub_client,
)
from graphfixture.datahub_writeback import (
    DataHubReceiptWriter,
    WritebackVerificationError,
)
from graphfixture.evidence import EvidenceBundle, create_evidence
from graphfixture.models import CoreRun
from graphfixture.scenario import fiction_retail_context
from graphfixture.workflow import GraphFixtureEngine
from tests.fakes import FakeClient

SQL_DIR = Path(__file__).parents[1] / "examples" / "sql"


def _seeded_client() -> FakeClient:
    fake = FakeClient()
    urns = seed_demo_catalog(fake.as_datahub())
    source_urns = urns[:3]
    fake.lineage.results = [LineageResult(urn, "dataset", 1, "upstream") for urn in source_urns]
    return fake


def _run_bundle() -> tuple[CoreRun, EvidenceBundle]:
    sql = (SQL_DIR / "customer_order_summary_fixed.sql").read_text(encoding="utf-8")
    run = GraphFixtureEngine().run(sql, fiction_retail_context(), seed=42)
    return run, create_evidence(run, sql)


def test_seed_and_read_live_datahub_context() -> None:
    fake = _seeded_client()

    context = DataHubContextReader(fake.as_datahub()).read("graphfixture-active-customers")

    assert context.source_mode == "datahub-live"
    assert {table.name for table in context.tables} == {
        "customers",
        "orders",
        "order_items",
    }
    assert context.table("order_items").columns[-1].data_type == "decimal"
    assert len(context.lineage) == 3
    assert context.contract.active_value == "active"
    assert context.captured_at == fiction_retail_context().captured_at


def test_identical_live_context_produces_identical_evidence() -> None:
    fake = _seeded_client()
    reader = DataHubContextReader(fake.as_datahub())
    sql = (SQL_DIR / "customer_order_summary_fixed.sql").read_text(encoding="utf-8")

    first = create_evidence(
        GraphFixtureEngine().run(sql, reader.read("graphfixture-active-customers")), sql
    )
    second = create_evidence(
        GraphFixtureEngine().run(sql, reader.read("graphfixture-active-customers")), sql
    )

    assert first == second


def test_reader_fails_when_contract_or_lineage_is_incomplete() -> None:
    fake = _seeded_client()
    contract = fake.entities.store["urn:li:document:graphfixture-active-customers"]
    assert isinstance(contract, Document)
    assert contract.custom_properties is not None
    contract.custom_properties.pop("key_field")

    with pytest.raises(DataHubContextError, match="key_field"):
        DataHubContextReader(fake.as_datahub()).read("graphfixture-active-customers")

    fake = _seeded_client()
    fake.lineage.results.pop()
    with pytest.raises(DataHubContextError, match="lineage is missing"):
        DataHubContextReader(fake.as_datahub()).read("graphfixture-active-customers")


def test_reader_rejects_wrong_entity_empty_schema_and_type() -> None:
    fake = _seeded_client()
    contract = fake.entities.store["urn:li:document:graphfixture-active-customers"]
    assert isinstance(contract, Document)
    assert contract.related_assets is not None
    source = contract.related_assets[0]
    fake.entities.store[source] = Document.create_document(id="wrong", title="Wrong", text="")

    with pytest.raises(DataHubContextError, match="not a Dataset"):
        DataHubContextReader(fake.as_datahub()).read("graphfixture-active-customers")

    empty = Dataset(platform="postgres", name="fiction_retail.customers")
    fake.entities.store[source] = empty
    with pytest.raises(DataHubContextError, match="has no schema"):
        DataHubContextReader(fake.as_datahub()).read("graphfixture-active-customers")

    unsupported = Dataset(platform="postgres", name="x", schema=[("field", "geography", "")])
    with pytest.raises(DataHubContextError, match="unsupported DataHub type"):
        _data_type(unsupported.schema[0])


def test_receipt_is_idempotent_linked_and_read_back() -> None:
    fake = FakeClient()
    run, bundle = _run_bundle()

    first = DataHubReceiptWriter(fake.as_datahub()).write_and_verify(run, bundle)
    second = DataHubReceiptWriter(fake.as_datahub()).write_and_verify(run, bundle)

    assert first == second
    assert first.verified is True
    receipt = fake.entities.store[first.document_urn]
    assert isinstance(receipt, Document)
    assert receipt.related_assets == [table.urn for table in run.context.tables]
    assert receipt.show_in_global_context is False
    assert receipt.text is not None
    assert bundle.digest in receipt.text


@pytest.mark.parametrize("corruption", ["entity", "digest", "text"])
def test_receipt_requires_exact_readback(corruption: str) -> None:
    fake = FakeClient()
    fake.entities.corrupt_readback = corruption
    run, bundle = _run_bundle()

    with pytest.raises(WritebackVerificationError):
        DataHubReceiptWriter(fake.as_datahub()).write_and_verify(run, bundle)


def test_client_factory_uses_datahub_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeClient().as_datahub()
    monkeypatch.setattr(DataHubClient, "from_env", lambda: fake)

    assert datahub_client() is fake
