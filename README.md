# GraphFixture

GraphFixture turns DataHub context into executable relational test data that catches SQL transformation bugs before merge.

The first product slice proves one contract: every active customer must appear in `customer_order_summary`, including customers with no orders. GraphFixture generates related `customers`, `orders`, and `order_items` rows, executes the transformation in isolated DuckDB, and reports the smallest fixture that reproduces a failure.

## Current proof

```bash
uv sync --all-groups
uv run pytest
```

The repository is under active hackathon development. Live DataHub context, canonical offline evidence, and the Proof Pipeline interface are tracked in the public issues.

## License

Apache License 2.0.
