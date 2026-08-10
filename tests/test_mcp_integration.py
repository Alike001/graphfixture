from __future__ import annotations

import json
from typing import Any

import pytest

from graphfixture.mcp_integration import (
    DataHubMcpClient,
    DataHubMcpError,
    _tool_payload,
)

TARGET = "urn:li:dataset:(urn:li:dataPlatform:postgres,fiction_retail.customer_summary,PROD)"
SOURCE = "urn:li:dataset:(urn:li:dataPlatform:postgres,fiction_retail.customers,PROD)"


class FakeProcess:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.sent: list[dict[str, Any]] = []

    def __enter__(self) -> FakeProcess:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def send(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    def receive(self) -> dict[str, Any]:
        if self.sent[-1]["method"] == "initialize":
            return {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18"}}
        return {"jsonrpc": "2.0", "id": 2, "result": self.response}


def _client(response: dict[str, Any]) -> tuple[DataHubMcpClient, FakeProcess]:
    process = FakeProcess(response)
    client = DataHubMcpClient(command=("fake-mcp",), timeout_seconds=1)
    client._server = lambda: process  # type: ignore[assignment,return-value]
    return client, process


def test_mcp_lineage_attestation_uses_read_only_tool() -> None:
    client, process = _client(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"upstreams": {"searchResults": [{"entity": {"urn": SOURCE}}]}}
                    ),
                }
            ]
        }
    )

    result = client.attest_lineage(TARGET, (SOURCE,))

    assert result.tool_name == "get_lineage"
    assert result.source_urns == (SOURCE,)
    call = process.sent[-1]
    assert call["method"] == "tools/call"
    assert call["params"]["name"] == "get_lineage"
    assert call["params"]["arguments"] == {
        "urn": TARGET,
        "upstream": True,
        "max_hops": 1,
        "max_results": 30,
    }


def test_mcp_lineage_attestation_rejects_missing_source() -> None:
    client, _ = _client({"content": [{"type": "text", "text": '{"upstreams": []}'}]})

    with pytest.raises(DataHubMcpError, match="missing sources"):
        client.attest_lineage(TARGET, (SOURCE,))


def test_mcp_lineage_does_not_accept_urns_hidden_in_unrelated_text() -> None:
    client, _ = _client(
        {"content": [{"type": "text", "text": f"unrelated text mentions {SOURCE}"}]}
    )

    with pytest.raises(DataHubMcpError, match="missing sources"):
        client.attest_lineage(TARGET, (SOURCE,))


def test_mcp_lineage_attestation_surfaces_tool_error() -> None:
    client, process = _client({"content": []})

    def error_response() -> dict[str, Any]:
        if process.sent[-1]["method"] == "initialize":
            return {"jsonrpc": "2.0", "id": 1, "result": {}}
        return {"jsonrpc": "2.0", "id": 2, "result": {"isError": True}}

    process.receive = error_response  # type: ignore[method-assign]
    with pytest.raises(DataHubMcpError, match="get_lineage failed"):
        client.attest_lineage(TARGET, (SOURCE,))


def test_tool_payload_supports_structured_and_text_results() -> None:
    structured: dict[str, Any] = {"upstreams": []}
    assert _tool_payload({"structuredContent": structured}) == structured
    assert _tool_payload({"content": [{"text": '{"upstreams": []}'}]}) == structured

    with pytest.raises(DataHubMcpError, match="no readable content"):
        _tool_payload({"content": [{"type": "image"}]})
