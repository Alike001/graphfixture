from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from datahub.errors import ItemNotFoundError
from datahub.sdk.dataset import Dataset
from datahub.sdk.document import Document
from datahub.sdk.entity import Entity
from datahub.sdk.lineage_client import LineageResult
from datahub.sdk.main_client import DataHubClient


@dataclass
class FakeEntities:
    store: dict[str, Entity] = field(default_factory=dict)
    corrupt_readback: str | None = None

    def upsert(self, entity: Entity, **_: object) -> None:
        self.store[str(entity.urn)] = entity

    def get(self, urn: object) -> Entity:
        try:
            entity = self.store[str(urn)]
        except KeyError as exc:
            raise ItemNotFoundError(str(urn)) from exc
        if str(urn) != "urn:li:document:graphfixture-active-customers":
            if self.corrupt_readback == "entity":
                return Dataset(platform="postgres", name="wrong")
            if isinstance(entity, Document) and self.corrupt_readback == "digest":
                assert entity.custom_properties is not None
                entity.custom_properties["evidence_digest"] = "wrong"
            if isinstance(entity, Document) and self.corrupt_readback == "text":
                entity.set_text("wrong")
        return entity


@dataclass
class FakeLineage:
    results: list[LineageResult] = field(default_factory=list)

    def get_lineage(self, **_: object) -> list[LineageResult]:
        return self.results


@dataclass
class FakeClient:
    entities: FakeEntities = field(default_factory=FakeEntities)
    lineage: FakeLineage = field(default_factory=FakeLineage)

    def test_connection(self) -> None:
        return None

    def as_datahub(self) -> DataHubClient:
        return cast(DataHubClient, self)
