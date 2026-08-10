"""Deterministic contract checks for transformation output."""

from collections import Counter

from graphfixture.models import (
    ContextSnapshot,
    ExecutionResult,
    FixtureSet,
    Row,
    VerificationResult,
)


def verify_active_customers(
    context: ContextSnapshot,
    fixtures: FixtureSet,
    execution: ExecutionResult,
) -> VerificationResult:
    """Require exactly one output row for every active customer and no others."""

    contract = context.contract
    expected = tuple(
        sorted(
            str(row[contract.key_field])
            for row in fixtures.rows("customers")
            if row[contract.status_field] == contract.active_value
        )
    )
    missing_key_rows = tuple(
        index for index, row in enumerate(execution.rows) if contract.key_field not in row
    )
    if missing_key_rows:
        return VerificationResult(
            passed=False,
            contract_id=contract.contract_id,
            title=contract.title,
            source_urn=contract.source_urn,
            expected_ids=expected,
            actual_ids=(),
            missing_ids=expected,
            unexpected_ids=(),
            duplicate_ids=(),
            reproducer=_minimal_reproducer(fixtures, expected),
            error=(
                f"output is missing contract key '{contract.key_field}' "
                f"in row(s): {', '.join(str(index) for index in missing_key_rows)}"
            ),
        )
    actual = tuple(sorted(str(row[contract.key_field]) for row in execution.rows))
    counts = Counter(actual)
    missing = tuple(sorted(set(expected) - set(actual)))
    unexpected = tuple(sorted(set(actual) - set(expected)))
    duplicates = tuple(sorted(key for key, count in counts.items() if count > 1))
    return VerificationResult(
        passed=not missing and not unexpected and not duplicates,
        contract_id=contract.contract_id,
        title=contract.title,
        source_urn=contract.source_urn,
        expected_ids=expected,
        actual_ids=actual,
        missing_ids=missing,
        unexpected_ids=unexpected,
        duplicate_ids=duplicates,
        reproducer=_minimal_reproducer(fixtures, missing),
    )


def _minimal_reproducer(
    fixtures: FixtureSet,
    missing_customer_ids: tuple[str, ...],
) -> dict[str, tuple[Row, ...]]:
    missing = set(missing_customer_ids)
    customers = tuple(
        row for row in fixtures.rows("customers") if str(row["customer_id"]) in missing
    )
    orders = tuple(row for row in fixtures.rows("orders") if str(row["customer_id"]) in missing)
    order_ids = {str(row["order_id"]) for row in orders}
    items = tuple(row for row in fixtures.rows("order_items") if str(row["order_id"]) in order_ids)
    return {"customers": customers, "orders": orders, "order_items": items}
