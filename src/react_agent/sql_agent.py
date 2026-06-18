import json
from pydantic_ai import Agent, RunContext

from src.react_agent.models import QuerySpecs, RAGResponse
from src.react_agent.tools import SQLTools


db_tools = SQLTools()
_metadata_cache: dict | None = None


SQL_AGENT_INSTRUCTIONS = """
# Role: SQL Generation & Execution Agent
You are stage two of a two-agent pipeline.
You receive a refined question and best-known `QuerySpecs`, then generate and execute exactly one SQL query.
You do not ask follow-up questions.

## Input Contract
You will receive:
- A refined natural language question in the user prompt.
- `QuerySpecs` as `deps` that may be partial.

## Execution Workflow
1. Call `get_db_metadata()` at most once.
2. Call `fetch_few_shot_examples()` at most once.
3. Generate exactly one SQL query that best matches the intent.
4. Call `execute_database_query()` exactly once with that SQL.
5. Build `RAGResponse`.

## Defaults for partial specs
- If no date is provided, use broad date range available in metadata.
- If no location/filter is provided, keep the query general and mention that in confidence explanation.

## Discipline Rules
- No multi-execution loops.
- No user interaction.
- No repeated metadata/example retrieval loops.
""".strip()


def create_sql_agent(model) -> Agent:
    agent = Agent(
        name="ReactSQLAgent",
        model=model,
        deps_type=QuerySpecs,
        output_type=RAGResponse,
        system_prompt=SQL_AGENT_INSTRUCTIONS,
    )

    @agent.tool
    def get_db_metadata(ctx: RunContext[QuerySpecs]) -> str:
        """Returns schema metadata with session-level caching."""
        global _metadata_cache
        if _metadata_cache is None:
            _metadata_cache = db_tools.get_db_metadata()
        return json.dumps(_metadata_cache)

    @agent.tool
    def fetch_few_shot_examples(ctx: RunContext[QuerySpecs]) -> str:
        """Fetches reference SQL examples to guide generation logic."""
        return json.dumps(db_tools.get_example_queries(), indent=2)

    @agent.tool
    def execute_database_query(ctx: RunContext[QuerySpecs], sql_string: str) -> str:
        """Executes SQL safely and returns structured result JSON."""
        return json.dumps(db_tools.run_sql_structured(sql_string), default=str)

    return agent


def run_sql_pipeline(model, specs: QuerySpecs, refined_question: str) -> RAGResponse:
    agent = create_sql_agent(model)
    result = agent.run_sync(
        user_prompt=(
            "Use the refined question and specs to generate SQL once, execute once, and return RAGResponse.\n"
            f"Refined question: {refined_question}"
        ),
        deps=specs,
    )
    return result.output
