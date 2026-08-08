import json
from copy import deepcopy
from pathlib import Path

import pytest

from graphfixture.cli import main
from graphfixture.evidence import create_evidence, digest_payload, write_evidence
from graphfixture.scenario import fiction_retail_context
from graphfixture.workflow import GraphFixtureEngine

SQL_DIR = Path(__file__).parents[1] / "examples" / "sql"


def test_cli_runs_and_replays_passing_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "fixed.json"
    run_code = main(
        [
            "run",
            "--sql",
            str(SQL_DIR / "customer_order_summary_fixed.sql"),
            "--output",
            str(output),
        ]
    )
    replay_code = main(["replay", str(output)])

    assert run_code == 0
    assert replay_code == 0
    assert output.exists()
    assert '"reproduced_verdict": true' in capsys.readouterr().out


def test_cli_returns_failure_for_reproduced_bug(tmp_path: Path) -> None:
    output = tmp_path / "broken.json"

    run_code = main(
        [
            "run",
            "--sql",
            str(SQL_DIR / "customer_order_summary_broken.sql"),
            "--output",
            str(output),
        ]
    )
    replay_code = main(["replay", str(output)])

    assert run_code == 1
    assert replay_code == 1


def test_cli_reports_tampering_as_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"algorithm": "sha256"}), encoding="utf-8")

    assert main(["replay", str(path)]) == 2
    assert "must be a string" in capsys.readouterr().err


def test_cli_replay_detects_recomputed_but_false_execution(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sql = (SQL_DIR / "customer_order_summary_fixed.sql").read_text(encoding="utf-8")
    run = GraphFixtureEngine().run(sql, fiction_retail_context(), seed=42)
    bundle = create_evidence(run, sql)
    payload = deepcopy(bundle.payload)
    execution = payload["execution"]
    assert isinstance(execution, dict)
    rows = execution["rows"]
    assert isinstance(rows, list)
    first = rows[0]
    assert isinstance(first, dict)
    first["customer_id"] = "C-FALSE"
    false_bundle = type(bundle)(payload, digest_payload(payload))
    path = tmp_path / "false-execution.json"
    write_evidence(path, false_bundle)

    assert main(["replay", str(path)]) == 2
    assert '"execution_matches": false' in capsys.readouterr().out
