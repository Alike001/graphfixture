"""Canonical, content-addressed evidence for GraphFixture runs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import cast

from graphfixture.models import CoreRun

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

SCHEMA_VERSION = "1.0"


class EvidenceIntegrityError(ValueError):
    """Raised when evidence content does not match its recorded digest."""


class EvidenceFormatError(ValueError):
    """Raised when evidence does not have the expected envelope shape."""


@dataclass(frozen=True)
class EvidenceBundle:
    payload: dict[str, JsonValue]
    digest: str
    algorithm: str = "sha256"

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "algorithm": self.algorithm,
            "digest": self.digest,
            "payload": self.payload,
        }


def create_evidence(run: CoreRun, sql: str) -> EvidenceBundle:
    """Create a deterministic evidence envelope from a completed core run."""

    payload = _require_object(
        to_json_value(
            {
                "schema_version": SCHEMA_VERSION,
                "sql": sql,
                "context": run.context,
                "fixtures": run.fixtures,
                "execution": run.execution,
                "verification": run.verification,
                "stages": run.stages,
            }
        )
    )
    return EvidenceBundle(payload=payload, digest=digest_payload(payload))


def digest_payload(payload: Mapping[str, JsonValue]) -> str:
    return hashlib.sha256(canonical_bytes(dict(payload))).hexdigest()


def canonical_bytes(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def write_evidence(path: Path, bundle: EvidenceBundle) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(bundle.as_json(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_evidence(path: Path) -> EvidenceBundle:
    try:
        raw = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceFormatError(f"cannot read evidence: {exc}") from exc
    root = _require_object(raw)
    algorithm = _require_string(root.get("algorithm"), "algorithm")
    digest = _require_string(root.get("digest"), "digest")
    payload = _require_object(root.get("payload"))
    bundle = EvidenceBundle(payload=payload, digest=digest, algorithm=algorithm)
    verify_evidence(bundle)
    return bundle


def verify_evidence(bundle: EvidenceBundle) -> None:
    if bundle.algorithm != "sha256":
        raise EvidenceFormatError(f"unsupported evidence algorithm: {bundle.algorithm}")
    actual = digest_payload(bundle.payload)
    if actual != bundle.digest:
        raise EvidenceIntegrityError(
            f"evidence digest mismatch: expected {bundle.digest}, computed {actual}"
        )


def to_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return to_json_value(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return to_json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [to_json_value(item) for item in value]
    raise TypeError(f"cannot serialize evidence value: {type(value).__name__}")


def _require_object(value: JsonValue | None) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise EvidenceFormatError("evidence field must be an object")
    return value


def _require_string(value: JsonValue | None, field: str) -> str:
    if not isinstance(value, str):
        raise EvidenceFormatError(f"evidence {field} must be a string")
    return value
