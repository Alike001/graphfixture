"""One shared workflow behind CLI, web, tests, and evidence."""

from graphfixture.executor import DuckDBExecutor
from graphfixture.generator import RelationalFixtureGenerator
from graphfixture.models import ContextSnapshot, CoreRun, StageStatus
from graphfixture.verifier import verify_active_customers


class GraphFixtureEngine:
    """Run the deterministic portion of the GraphFixture product."""

    def __init__(
        self,
        generator: RelationalFixtureGenerator | None = None,
        executor: DuckDBExecutor | None = None,
    ) -> None:
        self.generator = generator or RelationalFixtureGenerator()
        self.executor = executor or DuckDBExecutor()

    def run(self, sql: str, context: ContextSnapshot, seed: int = 42) -> CoreRun:
        fixtures = self.generator.generate(context, seed)
        execution = self.executor.run(sql, context, fixtures)
        verification = verify_active_customers(context, fixtures, execution)
        verification_state = StageStatus.PASSED if verification.passed else StageStatus.FAILED
        return CoreRun(
            context=context,
            fixtures=fixtures,
            execution=execution,
            verification=verification,
            stages={
                "datahub_context": StageStatus.PASSED,
                "constraints": StageStatus.PASSED,
                "fixtures": StageStatus.PASSED,
                "duckdb": StageStatus.PASSED,
                "verification": verification_state,
                "datahub_writeback": StageStatus.PENDING,
            },
        )
