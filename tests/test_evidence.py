import json
from copy import deepcopy
from enum import Enum
from pathlib import Path

import pytest

from graphfixture.evidence import (
    EvidenceBundle,
    EvidenceFormatError,
    EvidenceIntegrityError,
    JsonValue,
    create_evidence,
    digest_payload,
    load_evidence,
    to_json_value,
    verify_evidence,
    write_evidence,
)
from graphfixture.replay import replay_evidence
from graphfixture.scenario import fiction_retail_context
from graphfixture.workflow import GraphFixtureEngine

SQL_DIR = Path(__file__).parents[1] / "examples" / "sql"
EVIDENCE_DIR = Path(__file__).parents[1] / "examples" / "evidence"


def _bundle(name: str = "customer_order_summary_broken.sql") -> EvidenceBundle:
    sql = (SQL_DIR / name).read_text(encoding="utf-8")
    run = GraphFixtureEngine().run(sql, fiction_retail_context(), seed=42)
    return create_evidence(run, sql)


def test_evidence_is_canonical_and_stable() -> None:
    first = _bundle()
    second = _bundle()

    assert first == second
    assert len(first.digest) == 64
    assert first.payload["schema_version"] == "1.0"
    verify_evidence(first)


def test_evidence_round_trip_and_offline_replay(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    write_evidence(path, _bundle())

    loaded = load_evidence(path)
    replay = replay_evidence(loaded)

    assert replay.passed is True
    assert replay.reproduced_verdict is False


def test_fixed_evidence_replays_as_passing() -> None:
    replay = replay_evidence(_bundle("customer_order_summary_fixed.sql"))

    assert replay.passed is True
    assert replay.reproduced_verdict is True


@pytest.mark.parametrize(
    ("name", "expected_verdict"),
    [("broken.json", False), ("fixed.json", True)],
)
def test_checked_in_evidence_is_valid_and_replayable(name: str, expected_verdict: bool) -> None:
    replay = replay_evidence(load_evidence(EVIDENCE_DIR / name))

    assert replay.passed is True
    assert replay.reproduced_verdict is expected_verdict


def test_tampering_is_detected_before_replay(tmp_path: Path) -> None:
    path = tmp_path / "tampered.json"
    write_evidence(path, _bundle())
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["payload"]["fixtures"]["seed"] = 7
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(EvidenceIntegrityError, match="digest mismatch"):
        load_evidence(path)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("not json", "cannot read evidence"),
        ("[]", "must be an object"),
        ('{"algorithm": 4}', "algorithm must be a string"),
    ],
)
def test_malformed_evidence_fails_clearly(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(EvidenceFormatError, match=message):
        load_evidence(path)


def test_unknown_algorithm_and_value_are_rejected() -> None:
    bundle = _bundle()

    with pytest.raises(EvidenceFormatError, match="unsupported evidence algorithm"):
        verify_evidence(EvidenceBundle(bundle.payload, bundle.digest, "md5"))
    with pytest.raises(TypeError, match="cannot serialize"):
        to_json_value(object())


def test_plain_enum_is_serialized_by_value() -> None:
    class PlainState(Enum):
        READY = "ready"

    assert to_json_value(PlainState.READY) == "ready"


def test_replay_rejects_unsupported_schema_version() -> None:
    bundle = _bundle()
    payload = deepcopy(bundle.payload)
    payload["schema_version"] = "9.0"
    changed = EvidenceBundle(payload, digest_payload(payload))

    with pytest.raises(EvidenceFormatError, match="schema version"):
        replay_evidence(changed)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("fixtures", "seed"), "42", "seed must be an integer"),
        (("context", "tables"), {}, "tables must be an array"),
        (("context",), [], "context must be an object"),
        (("sql",), 4, "sql must be a string"),
    ],
)
def test_replay_rejects_invalid_field_shapes(
    path: tuple[str, ...], value: JsonValue, message: str
) -> None:
    bundle = _bundle()
    payload = deepcopy(bundle.payload)
    target = payload
    for key in path[:-1]:
        nested = target[key]
        assert isinstance(nested, dict)
        target = nested
    target[path[-1]] = value
    changed = EvidenceBundle(payload, digest_payload(payload))

    with pytest.raises(EvidenceFormatError, match=message):
        replay_evidence(changed)


def test_replay_rejects_unknown_missing_and_invalid_fixture_values() -> None:
    bundle = _bundle()
    for mutation, message in (
        ("unknown", "unknown fixture columns"),
        ("missing", "missing fixture columns"),
        ("invalid", "invalid integer fixture value"),
    ):
        payload = deepcopy(bundle.payload)
        fixtures = payload["fixtures"]
        assert isinstance(fixtures, dict)
        tables = fixtures["tables"]
        assert isinstance(tables, dict)
        items = tables["order_items"]
        assert isinstance(items, list)
        first = items[0]
        assert isinstance(first, dict)
        if mutation == "unknown":
            first["unknown"] = "value"
        elif mutation == "missing":
            first.pop("item_id")
        else:
            first["quantity"] = "one"
        changed = EvidenceBundle(payload, digest_payload(payload))

        with pytest.raises(EvidenceFormatError, match=message):
            replay_evidence(changed)
