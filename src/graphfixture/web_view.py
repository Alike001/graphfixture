"""JSON-safe view model for the Proof Pipeline interface."""

from __future__ import annotations

from graphfixture.evidence import to_json_value
from graphfixture.web_service import ProofOutcome

STAGE_LABELS = (
    ("datahub_context", "DataHub Context"),
    ("constraints", "Constraints"),
    ("fixtures", "Fixtures"),
    ("duckdb", "DuckDB"),
    ("verification", "Verification"),
    ("datahub_writeback", "DataHub Write-back"),
)


def proof_view(outcome: ProofOutcome) -> dict[str, object]:
    run = outcome.run
    verification = run.verification
    stages = []
    for key, label in STAGE_LABELS:
        status = run.stages[key].value
        if key == "datahub_writeback":
            status = "passed" if outcome.writeback else "unavailable"
        stages.append({"key": key, "label": label, "status": status})
    missing = len(verification.missing_ids)
    if verification.passed:
        summary = f"Contract passed: all {len(verification.expected_ids)} active customers appear"
    else:
        noun = "customer" if missing == 1 else "customers"
        summary = f"1 contract failed: {missing} active {noun} missing from the output"
    expected_rows = []
    customers = run.fixtures.rows("customers")
    actual_by_id = {str(row[run.context.contract.key_field]): row for row in run.execution.rows}
    for customer_id in verification.expected_ids:
        customer = next(
            row for row in customers if str(row[run.context.contract.key_field]) == customer_id
        )
        actual = actual_by_id.get(customer_id)
        expected_rows.append(
            {
                "customer_id": customer_id,
                "name": customer.get("name"),
                "order_count": actual.get("order_count") if actual else 0,
            }
        )
    writeback = None
    if outcome.writeback:
        writeback = {
            "document_urn": outcome.writeback.document_urn,
            "evidence_digest": outcome.writeback.evidence_digest,
            "verified": outcome.writeback.verified,
        }
    return {
        "run_id": outcome.bundle.digest[:8].upper(),
        "seed": run.fixtures.seed,
        "captured_at": run.context.captured_at,
        "passed": verification.passed,
        "variant": outcome.variant,
        "source": outcome.source,
        "source_mode": run.context.source_mode,
        "summary": summary,
        "stages": stages,
        "contract": to_json_value(run.context.contract),
        "tables": to_json_value(run.context.tables),
        "lineage": to_json_value(run.context.lineage),
        "fixtures": to_json_value(run.fixtures.tables),
        "reproducer": to_json_value(verification.reproducer),
        "execution": to_json_value(run.execution),
        "expected_rows": to_json_value(expected_rows),
        "missing_ids": list(verification.missing_ids),
        "sql": outcome.bundle.payload["sql"],
        "digest": outcome.bundle.digest,
        "writeback": writeback,
        "evidence": outcome.bundle.as_json(),
    }
