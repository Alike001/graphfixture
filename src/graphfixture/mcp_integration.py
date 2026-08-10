"""Small stdio client for the official DataHub MCP Server.

GraphFixture keeps the Python SDK for typed schema reads and Document write-back.
This client adds a real, read-only MCP Server call to the live proof path so the
hackathon integration is exercised instead of merely declared in configuration.
"""

from __future__ import annotations

import hashlib
import json
import os
import select
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any


class DataHubMcpError(RuntimeError):
    """Raised when the official DataHub MCP Server cannot attest lineage."""


@dataclass(frozen=True)
class McpLineageAttestation:
    """Evidence returned by the read-only MCP lineage call."""

    tool_name: str
    source_urns: tuple[str, ...]
    response_digest: str


class DataHubMcpClient:
    """Call the official DataHub MCP Server over its documented stdio transport."""

    def __init__(
        self,
        command: tuple[str, ...] | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        configured = os.getenv("GRAPHFIXTURE_MCP_COMMAND")
        self.command = command or tuple(
            shlex.split(configured)
            if configured
            else ("uvx", "mcp-server-datahub@latest")
        )
        self.timeout_seconds = timeout_seconds or float(
            os.getenv("GRAPHFIXTURE_MCP_TIMEOUT_SECONDS", "30")
        )
        if not self.command:
            raise DataHubMcpError("GRAPHFIXTURE_MCP_COMMAND cannot be empty")

    def attest_lineage(
        self, target_urn: str, source_urns: tuple[str, ...]
    ) -> McpLineageAttestation:
        """Ask MCP ``get_lineage`` for upstreams and verify every source is present."""

        arguments = {
            "urn": target_urn,
            "upstream": True,
            "max_hops": 1,
            "max_results": max(30, len(source_urns)),
        }
        with self._server() as process:
            self._request(
                process,
                1,
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "graphfixture", "version": "0.1.0"},
                },
            )
            self._notify(process, "notifications/initialized")
            response = self._request(
                process,
                2,
                "tools/call",
                {"name": "get_lineage", "arguments": arguments},
            )

        if response.get("isError") is True:
            raise DataHubMcpError(f"MCP get_lineage failed: {response}")
        payload = _tool_payload(response)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        missing = tuple(urn for urn in source_urns if urn not in encoded)
        if missing:
            raise DataHubMcpError(
                "MCP lineage is missing sources: " + ", ".join(missing)
            )
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        return McpLineageAttestation("get_lineage", source_urns, digest)

    def _server(self) -> _McpServerProcess:
        return _McpServerProcess(self.command, self.timeout_seconds)

    def _request(
        self,
        process: _McpServerProcess,
        request_id: int,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        process.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            message = process.receive()
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise DataHubMcpError(f"MCP {method} failed: {message['error']}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise DataHubMcpError(f"MCP {method} returned an invalid result")
            return result

    @staticmethod
    def _notify(process: _McpServerProcess, method: str) -> None:
        process.send({"jsonrpc": "2.0", "method": method})


class _McpServerProcess:
    def __init__(self, command: tuple[str, ...], timeout_seconds: float) -> None:
        env = os.environ.copy()
        env.setdefault("TOOLS_IS_MUTATION_ENABLED", "false")
        env.setdefault("TOOLS_IS_USER_ENABLED", "false")
        try:
            self.process: subprocess.Popen[bytes] = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=env,
            )
        except OSError as exc:
            raise DataHubMcpError(f"could not start MCP Server: {exc}") from exc
        self.timeout_seconds = timeout_seconds

    def __enter__(self) -> _McpServerProcess:
        return self

    def __exit__(self, *_: object) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

    def send(self, message: dict[str, Any]) -> None:
        if self.process.stdin is None:
            raise DataHubMcpError("MCP Server stdin is unavailable")
        raw = json.dumps(message, separators=(",", ":")).encode("utf-8")
        # The official Python server uses MCP's newline-delimited stdio transport.
        self.process.stdin.write(raw + b"\n")
        self.process.stdin.flush()

    def receive(self) -> dict[str, Any]:
        if self.process.stdout is None:
            raise DataHubMcpError("MCP Server stdout is unavailable")
        ready, _, _ = select.select([self.process.stdout], [], [], self.timeout_seconds)
        if not ready:
            raise DataHubMcpError("timed out waiting for MCP Server")
        first = self.process.stdout.readline()
        if not first:
            raise DataHubMcpError("MCP Server closed stdout")
        if first.lower().startswith(b"content-length:"):
            headers = {first.split(b":", 1)[0].strip().lower(): first.split(b":", 1)[1].strip()}
            while True:
                line = self.process.stdout.readline()
                if not line or line in (b"\r\n", b"\n"):
                    break
                if b":" in line:
                    key, value = line.split(b":", 1)
                    headers[key.strip().lower()] = value.strip()
            try:
                size = int(headers[b"content-length"])
                body = self.process.stdout.read(size)
            except (KeyError, ValueError) as exc:
                raise DataHubMcpError("MCP Server sent an invalid content length") from exc
            if len(body) != size:
                raise DataHubMcpError("MCP Server sent a truncated response")
            raw = body
        else:
            raw = first.strip()
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DataHubMcpError("MCP Server sent invalid JSON") from exc
        if not isinstance(message, dict):
            raise DataHubMcpError("MCP Server sent a non-object JSON message")
        return message


def _tool_payload(response: dict[str, Any]) -> Any:
    structured = response.get("structuredContent")
    if structured is not None:
        return structured
    content = response.get("content")
    if not isinstance(content, list):
        raise DataHubMcpError("MCP tool response has no content")
    parsed: list[Any] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            try:
                parsed.append(json.loads(text))
            except json.JSONDecodeError:
                parsed.append(text)
    if not parsed:
        raise DataHubMcpError("MCP tool response has no readable content")
    return parsed[0] if len(parsed) == 1 else parsed
