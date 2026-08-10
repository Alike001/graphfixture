from dataclasses import replace

from graphfixture.generator import RelationalFixtureGenerator
from graphfixture.models import ExecutionResult
from graphfixture.scenario import fiction_retail_context
from graphfixture.verifier import verify_active_customers


def _result(customer_ids: tuple[str, ...]) -> ExecutionResult:
    return ExecutionResult(
        columns=("customer_id",),
        rows=tuple({"customer_id": customer_id} for customer_id in customer_ids),
        sql_digest="0" * 64,
    )


def test_verifier_reports_duplicate_and_unexpected_rows() -> None:
    context = fiction_retail_context()
    fixtures = RelationalFixtureGenerator().generate(context, 42)

    verification = verify_active_customers(
        context,
        fixtures,
        _result(("C-001", "C-001", "C-003", "C-004", "C-999")),
    )

    assert verification.passed is False
    assert verification.missing_ids == ()
    assert verification.unexpected_ids == ("C-999",)
    assert verification.duplicate_ids == ("C-001",)


def test_context_table_lookup_is_explicit() -> None:
    context = fiction_retail_context()

    assert context.table("customers").name == "customers"

    try:
        context.table("missing")
    except KeyError as exc:
        assert exc.args == ("missing",)
    else:
        raise AssertionError("missing context table should raise KeyError")


def test_contract_fields_drive_verification() -> None:
    context = fiction_retail_context()
    fixtures = RelationalFixtureGenerator().generate(context, 42)
    inactive_contract = replace(context.contract, active_value="inactive")
    inactive_context = replace(context, contract=inactive_contract)

    verification = verify_active_customers(
        inactive_context,
        fixtures,
        _result(("C-002",)),
    )

    assert verification.passed is True
    assert verification.expected_ids == ("C-002",)


def test_verifier_reports_missing_contract_key_instead_of_crashing() -> None:
    context = fiction_retail_context()
    fixtures = RelationalFixtureGenerator().generate(context, 42)

    verification = verify_active_customers(
        context,
        fixtures,
        ExecutionResult(columns=("name",), rows=({"name": "Alice"},), sql_digest="0" * 64),
    )

    assert verification.passed is False
    assert verification.error == "output is missing contract key 'customer_id' in row(s): 0"
