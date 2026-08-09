from pathlib import Path

import pytest
from datahub.sdk.document import Document
from datahub.sdk.lineage_client import LineageResult
from httpx2 import ASGITransport, AsyncClient

from graphfixture.datahub_demo import seed_demo_catalog
from graphfixture.web import create_app
from graphfixture.web_service import (
    ContextSource,
    LiveDataHubError,
    ProofOutcome,
    ProofService,
    SqlVariant,
)
from tests.fakes import FakeClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


@pytest.mark.anyio
async def test_default_page_opens_on_real_seeded_failure() -> None:
    async with _client() as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "GraphFixture Proof Pipeline" in response.text
    assert "customer_order_summary.sql" in response.text
    assert 'id="initial-proof"' in response.text
    assert '"passed": false' in response.text


@pytest.mark.anyio
async def test_offline_api_runs_broken_and_fixed_proofs_deterministically() -> None:
    async with _client() as client:
        broken = await client.post("/api/run", json={"variant": "broken", "source": "offline"})
        fixed = await client.post("/api/run", json={"variant": "fixed", "source": "offline"})
        repeated = await client.post("/api/run", json={"variant": "fixed", "source": "offline"})

    assert broken.status_code == 200
    assert broken.json()["passed"] is False
    assert broken.json()["missing_ids"] == ["C-003"]
    assert fixed.json()["passed"] is True
    assert fixed.json()["digest"] == repeated.json()["digest"]
    assert fixed.json()["stages"][-1]["status"] == "unavailable"


@pytest.mark.parametrize(
    "body",
    [
        {"variant": "unknown", "source": "offline"},
        {"variant": "fixed", "source": "cloud"},
        {"variant": "fixed", "source": "offline", "seed": -1},
    ],
)
@pytest.mark.anyio
async def test_api_rejects_bad_run_inputs(body: dict[str, object]) -> None:
    async with _client() as client:
        response = await client.post("/api/run", json=body)

    assert response.status_code == 422


@pytest.mark.anyio
async def test_live_api_uses_datahub_context_and_verifies_writeback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graphfixture import web_service

    fake = FakeClient()
    seed_demo_catalog(fake.as_datahub())
    contract = fake.entities.store["urn:li:document:graphfixture-active-customers"]
    assert isinstance(contract, Document)
    assert contract.related_assets is not None
    fake.lineage.results = [
        LineageResult(urn, "dataset", 1, "upstream") for urn in contract.related_assets[:-1]
    ]
    monkeypatch.setattr(web_service, "datahub_client", fake.as_datahub)

    async with _client() as client:
        response = await client.post("/api/run", json={"variant": "fixed", "source": "live"})

    assert response.status_code == 200
    assert response.json()["source_mode"] == "datahub-live"
    assert response.json()["writeback"]["verified"] is True
    assert response.json()["stages"][-1]["status"] == "passed"


@pytest.mark.anyio
async def test_live_api_reports_unavailable_datahub_without_fake_success(
    tmp_path: Path,
) -> None:
    class UnavailableService(ProofService):
        def execute(
            self,
            variant: SqlVariant,
            source: ContextSource,
            seed: int = 42,
        ) -> ProofOutcome:
            raise LiveDataHubError("live DataHub context failed: connection refused")

    app = create_app(UnavailableService(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/run", json={"variant": "fixed", "source": "live"})

    assert response.status_code == 503
    assert "connection refused" in response.json()["detail"]
