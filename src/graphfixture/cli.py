"""Command-line proof and offline replay for GraphFixture."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from graphfixture.evidence import (
    EvidenceFormatError,
    EvidenceIntegrityError,
    create_evidence,
    load_evidence,
    write_evidence,
)
from graphfixture.replay import replay_evidence
from graphfixture.scenario import fiction_retail_context
from graphfixture.workflow import GraphFixtureEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graphfixture")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run SQL and write canonical evidence")
    run.add_argument("--sql", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--seed", type=int, default=42)
    replay = commands.add_parser("replay", help="verify and replay evidence offline")
    replay.add_argument("evidence", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            return _run(args.sql, args.output, args.seed)
        return _replay(args.evidence)
    except (OSError, EvidenceFormatError, EvidenceIntegrityError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


def _run(sql_path: Path, output: Path, seed: int) -> int:
    sql = sql_path.read_text(encoding="utf-8")
    run = GraphFixtureEngine().run(sql, fiction_retail_context(), seed=seed)
    bundle = create_evidence(run, sql)
    write_evidence(output, bundle)
    print(
        json.dumps(
            {
                "digest": bundle.digest,
                "evidence": str(output),
                "missing_ids": run.verification.missing_ids,
                "passed": run.verification.passed,
            },
            sort_keys=True,
        )
    )
    return 0 if run.verification.passed else 1


def _replay(path: Path) -> int:
    bundle = load_evidence(path)
    result = replay_evidence(bundle)
    print(
        json.dumps(
            {
                "digest": bundle.digest,
                "execution_matches": result.execution_matches,
                "reproduced_verdict": result.reproduced_verdict,
                "verification_matches": result.verification_matches,
            },
            sort_keys=True,
        )
    )
    if not result.passed:
        return 2
    return 0 if result.reproduced_verdict else 1
