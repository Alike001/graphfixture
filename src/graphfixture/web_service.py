"""Application service shared by the GraphFixture web routes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from graphfixture.datahub_integration import DataHubContextReader, datahub_client
from graphfixture.datahub_writeback import DataHubReceiptWriter, WritebackResult
from graphfixture.evidence import EvidenceBundle, create_evidence
from graphfixture.mcp_integration import DataHubMcpClient
from graphfixture.models import CoreRun
from graphfixture.scenario import fiction_retail_context
from graphfixture.workflow import GraphFixtureEngine

type SqlVariant = Literal["broken", "fixed"]
type ContextSource = Literal["offline", "live"]


class LiveDataHubError(RuntimeError):
    """Raised when a requested live proof cannot reach or use DataHub."""


def datahub_mcp_client() -> DataHubMcpClient:
    """Build the qualifying official MCP Server client for a live proof."""

    return DataHubMcpClient()


@dataclass(frozen=True)
class ProofOutcome:
    run: CoreRun
    bundle: EvidenceBundle
    variant: SqlVariant
    source: ContextSource
    writeback: WritebackResult | None


class ProofService:
    """Execute one honest proof using captured or live DataHub context."""

    def __init__(self, sql_dir: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.sql_dir = sql_dir or root / "examples" / "sql"

    def execute(self, variant: SqlVariant, source: ContextSource, seed: int = 42) -> ProofOutcome:
        sql = self._sql(variant)
        writeback = None
        if source == "live":
            try:
                client = datahub_client()
                client.test_connection()
                context = DataHubContextReader(client, datahub_mcp_client()).read(
                    "graphfixture-active-customers"
                )
            except Exception as exc:
                raise LiveDataHubError(f"live DataHub context failed: {exc}") from exc
        else:
            client = None
            context = fiction_retail_context()
        run = GraphFixtureEngine().run(sql, context, seed=seed)
        bundle = create_evidence(run, sql)
        if client is not None:
            try:
                writeback = DataHubReceiptWriter(client).write_and_verify(run, bundle)
            except Exception as exc:
                raise LiveDataHubError(f"DataHub write-back failed: {exc}") from exc
        return ProofOutcome(run, bundle, variant, source, writeback)

    def _sql(self, variant: SqlVariant) -> str:
        path = self.sql_dir / f"customer_order_summary_{variant}.sql"
        return path.read_text(encoding="utf-8")
