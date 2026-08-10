# GraphFixture

GraphFixture turns DataHub context into executable relational test data that catches SQL transformation bugs before merge.

The first product slice proves one contract: every active customer must appear in `customer_order_summary`, including customers with no orders. GraphFixture generates related `customers`, `orders`, and `order_items` rows, executes the transformation in isolated DuckDB, and reports the smallest fixture that reproduces a failure.

## See the proof

```bash
uv sync --all-groups
uv run graphfixture replay examples/evidence/broken.json
```

The replay needs no DataHub server, API key, or network. It verifies the evidence hash, rebuilds the typed fixture, reruns the saved SQL in DuckDB, and confirms the recorded failure. Exit code `1` means the replay is authentic and the saved contract failure reproduced. The broken query drops active customer `C-003` because that customer has zero orders.

Compare it with the fixed transformation:

```bash
uv run graphfixture replay examples/evidence/fixed.json
```

That command exits `0` and proves the same fixture passes after changing the inner join to a left join.

For the visual Proof Pipeline:

```bash
uv run graphfixture serve
```

Open `http://127.0.0.1:8000`. The first screen is already loaded with the failing proof. Choose the fixed SQL version and rerun to see the same contract pass without changing the fixture seed.

## Deploy the hosted proof

GraphFixture can run as an offline-first Render web service. The hosted screen
opens on the captured proof and needs no DataHub server, API key, or network
call for the main demo.

1. Create a new Render Blueprint from this repository and select `render.yaml`.
2. Wait for the health check at `/healthz` to pass.
3. Open the generated URL, run the broken proof, then choose the fixed SQL and
   rerun it.

The Live DataHub selector is optional. It only works when `DATAHUB_GMS_URL`
points to a reachable DataHub GMS service and its authentication is configured
through the deployment environment. A local `http://localhost:8080` endpoint
cannot be reached from the hosted service. If no live endpoint is configured,
the app keeps the captured-evidence path visible and does not claim a live
write-back.

## Run your own proof

```bash
uv run graphfixture run \
  --sql examples/sql/customer_order_summary_broken.sql \
  --output evidence.json
```

The canonical JSON bundle includes the captured DataHub context, generated relational rows, SQL digest, output rows, deterministic contract result, and minimal reproducer. SHA-256 detects content changes, while offline replay checks that saved claims still match fresh execution. The bundle is not signed, so its hash is an integrity check rather than proof of who created it.

## Prove it with DataHub

Start the official local DataHub stack, then seed the small fiction-retail graph used by the proof:

```bash
uv run datahub docker quickstart --version stable
DATAHUB_GMS_URL=http://localhost:8080 uv run graphfixture datahub-seed
```

Run the broken transformation using schemas, lineage, and the contract read from DataHub:

```bash
DATAHUB_GMS_URL=http://localhost:8080 uv run graphfixture datahub-run \
  --sql examples/sql/customer_order_summary_broken.sql \
  --output live-evidence.json
```

The live proof starts the official DataHub MCP Server with `uvx
mcp-server-datahub@latest` and calls its read-only `get_lineage` tool before the
typed SDK read. Set `DATAHUB_GMS_TOKEN` too when your DataHub requires
authentication. This MCP attestation is a hard gate, so an SDK-only or
unreachable proof cannot claim a live result. GraphFixture then writes a linked
verification receipt back to DataHub and immediately reads it again. The
command only reports `writeback_verified: true` when the stored evidence digest
matches exactly. The seed and receipt IDs are stable, so rerunning either
command updates the same graph entities instead of creating duplicates.

The MCP command can be replaced for a pinned local install or a test harness:

```bash
GRAPHFIXTURE_MCP_COMMAND="uvx mcp-server-datahub@latest" \
DATAHUB_GMS_URL=http://localhost:8080 \
uv run graphfixture datahub-run \
  --sql examples/sql/customer_order_summary_fixed.sql \
  --output live-evidence.json
```

## Quality gates

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv build
```

The public issue history records each meaningful feature and architectural decision.

## License

Apache License 2.0.
