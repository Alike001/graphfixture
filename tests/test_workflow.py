from pathlib import Path

from graphfixture.scenario import fiction_retail_context
from graphfixture.workflow import GraphFixtureEngine

SQL_DIR = Path(__file__).parents[1] / "examples" / "sql"


def _sql(name: str) -> str:
    return (SQL_DIR / name).read_text()


def test_broken_inner_join_exposes_zero_order_customer() -> None:
    run = GraphFixtureEngine().run(
        _sql("customer_order_summary_broken.sql"),
        fiction_retail_context(),
        seed=42,
    )

    assert run.verification.passed is False
    assert run.verification.missing_ids == ("C-003",)
    assert run.verification.reproducer["customers"][0]["customer_id"] == "C-003"
    assert run.verification.reproducer["orders"] == ()
    assert run.stages["verification"] == "failed"
    assert run.stages["datahub_writeback"] == "pending"


def test_fixed_left_join_passes_same_fixture() -> None:
    run = GraphFixtureEngine().run(
        _sql("customer_order_summary_fixed.sql"),
        fiction_retail_context(),
        seed=42,
    )

    assert run.verification.passed is True
    assert run.verification.expected_ids == ("C-001", "C-003", "C-004")
    assert run.verification.actual_ids == run.verification.expected_ids
    assert run.verification.missing_ids == ()
    assert run.stages["verification"] == "passed"
