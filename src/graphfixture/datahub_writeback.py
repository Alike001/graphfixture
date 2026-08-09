"""Verified DataHub Document write-back for GraphFixture receipts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from datahub.errors import ItemNotFoundError
from datahub.metadata.urns import DocumentUrn
from datahub.sdk.document import Document
from datahub.sdk.main_client import DataHubClient

from graphfixture.evidence import EvidenceBundle
from graphfixture.models import CoreRun


class WritebackVerificationError(RuntimeError):
    """Raised when a written receipt cannot be read back exactly."""


@dataclass(frozen=True)
class WritebackResult:
    document_urn: str
    evidence_digest: str
    verified: bool


class DataHubReceiptWriter:
    """Upsert a linked Document and require a matching read-back."""

    def __init__(self, client: DataHubClient) -> None:
        self.client = client

    def write_and_verify(
        self,
        run: CoreRun,
        bundle: EvidenceBundle,
    ) -> WritebackResult:
        document_id = _document_id(run)
        document = self._document(document_id, run, bundle)
        self.client.entities.upsert(document)
        readback = self.client.entities.get(DocumentUrn(document_id))
        if not isinstance(readback, Document):
            raise WritebackVerificationError("DataHub receipt read-back is not a Document")
        properties = readback.custom_properties or {}
        if properties.get("evidence_digest") != bundle.digest:
            raise WritebackVerificationError("DataHub receipt digest did not match read-back")
        if not readback.text or bundle.digest not in readback.text:
            raise WritebackVerificationError("DataHub receipt text did not match read-back")
        return WritebackResult(str(readback.urn), bundle.digest, verified=True)

    def _document(self, document_id: str, run: CoreRun, bundle: EvidenceBundle) -> Document:
        title = f"GraphFixture receipt: {run.verification.title}"
        text = _receipt_text(run, bundle)
        assets = [table.urn for table in run.context.tables]
        properties = {
            "evidence_digest": bundle.digest,
            "contract_id": run.verification.contract_id,
            "verdict": "passed" if run.verification.passed else "failed",
            "fixture_seed": str(run.fixtures.seed),
            "sql_digest": run.execution.sql_digest,
        }
        try:
            existing = self.client.entities.get(DocumentUrn(document_id))
        except ItemNotFoundError:
            return Document.create_document(
                id=document_id,
                title=title,
                text=text,
                subtype="GraphFixture Verification Receipt",
                show_in_global_context=False,
                related_assets=assets,
                custom_properties=properties,
            )
        if not isinstance(existing, Document):
            raise WritebackVerificationError("DataHub receipt target is not a Document")
        existing.set_title(title)
        existing.set_text(text)
        existing.set_related_assets(assets)
        existing.set_show_in_global_context(False)
        existing.set_subtype("GraphFixture Verification Receipt")
        existing.set_custom_properties(properties)
        return existing


def _document_id(run: CoreRun) -> str:
    contract = re.sub(r"[^a-z0-9-]+", "-", run.verification.contract_id.lower()).strip("-")
    return f"graphfixture-{contract}-{run.execution.sql_digest[:12]}-{run.fixtures.seed}"


def _receipt_text(run: CoreRun, bundle: EvidenceBundle) -> str:
    missing = ", ".join(run.verification.missing_ids) or "none"
    evidence = json.dumps(bundle.as_json(), ensure_ascii=False, sort_keys=True)
    return (
        "# GraphFixture Verification Receipt\n\n"
        f"- Evidence digest: `{bundle.digest}`\n"
        f"- Contract: `{run.verification.contract_id}`\n"
        f"- Verdict: `{'passed' if run.verification.passed else 'failed'}`\n"
        f"- Missing IDs: `{missing}`\n\n"
        "## Canonical evidence\n\n"
        f"```json\n{evidence}\n```\n"
    )
