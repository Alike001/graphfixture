import json
from copy import deepcopy
from pathlib import Path

import pytest
from datahub.sdk.document import Document
from datahub.sdk.lineage_client import LineageResult

from graphfixture.cli import main
from graphfixture.evidence import create_evidence, digest_payload, write_evidence
from graphfixture.mcp_integration import DataHubMcpClient, McpLineageAttestation
from graphfixture.scenario import fiction_retail_context
from graphfixture.workflow import GraphFixtureEngine
from tests.fakes import FakeClient

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


def test_cli_seeds_and_runs_live_datahub_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graphfixture import cli

    class FakeMcp(DataHubMcpClient):
        def __init__(self) -> None:
            pass

        def attest_lineage(
            self, target_urn: str, source_urns: tuple[str, ...]
        ) -> McpLineageAttestation:
            return McpLineageAttestation("get_lineage", source_urns, "test-digest")

    fake = FakeClient()
    monkeypatch.setattr(cli, "datahub_client", fake.as_datahub)
    monkeypatch.setattr(cli, "DataHubMcpClient", FakeMcp)
    assert main(["datahub-seed"]) == 0
    contract = fake.entities.store["urn:li:document:graphfixture-active-customers"]
    assert isinstance(contract, Document)
    assert contract.related_assets is not None
    fake.lineage.results = [
        LineageResult(urn, "dataset", 1, "upstream") for urn in contract.related_assets[:-1]
    ]
    output = tmp_path / "live.json"

    code = main(
        [
            "datahub-run",
            "--sql",
            str(SQL_DIR / "customer_order_summary_fixed.sql"),
            "--output",
            str(output),
        ]
    )

    assert code == 0
    assert output.exists()
    captured = capsys.readouterr().out
    assert '"writeback_verified": true' in captured


def test_cli_starts_web_interface(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    called: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: called.update(app=app, **options))

    assert main(["serve", "--host", "0.0.0.0", "--port", "9000"]) == 0
    assert called == {"app": "graphfixture.web:app", "host": "0.0.0.0", "port": 9000}
