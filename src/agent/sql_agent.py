import json
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext

from src.agent.llm import LLMProvider
from src.agent.models import QuerySpecs, RAGResponse
from src.agent.tools import SQLTools


db_tools = SQLTools()

model_provider = LLMProvider()
model = model_provider.get_chatns_model()


DEFAULT_INSTRUCTIONS = """
# Role: SQL Generation & Execution Agent
You are stage two of a two-agent pipeline.
You receive a refined question and best-known `QuerySpecs`, then generate and execute exactly one SQL query.
You do not ask the user follow-up questions.

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
- Always echo the received `QuerySpecs` back in `query_specs`.

## Discipline Rules
- No multi-execution loops.
- No user interaction.
- No repeated metadata/example retrieval loops.
""".strip()


@dataclass
class SQLAgentConfig:
    name: str = "SQLAgent"
    instructions: str = DEFAULT_INSTRUCTIONS


agent_config = SQLAgentConfig()
sql_agent = Agent(
    name=agent_config.name,
    model=model,
    deps_type=QuerySpecs,
    output_type=RAGResponse,
    system_prompt=agent_config.instructions,
)


_metadata_cache: dict | None = None


@sql_agent.tool
def get_db_metadata(ctx: RunContext[QuerySpecs]) -> str:
    """Returns schema metadata with session-level caching."""
    global _metadata_cache
    if _metadata_cache is None:
        _metadata_cache = db_tools.get_db_metadata()
    return json.dumps(_metadata_cache)


@sql_agent.tool
def fetch_few_shot_examples(ctx: RunContext[QuerySpecs]) -> str:
    """
    Fetches genuine reference SQL configurations to guide generation logic rules.
    Guaranteed safety rule: Can only be evaluated maximum 1 time per pipeline invocation.
    """
    examples = db_tools.get_example_queries()
    return json.dumps(examples, indent=2)


@sql_agent.tool
def execute_database_query(ctx: RunContext[QuerySpecs], sql_string: str) -> str:
    """
    Executes raw query syntax safely inside the target database environment.
    """
    return json.dumps(db_tools.run_sql_structured(sql_string), default=str)


def run_sql_pipeline(specs: QuerySpecs, refined_question: str) -> RAGResponse:
    """
    Synchronous pipeline thread gateway processing verified specifications blocks.
    """
    result = sql_agent.run_sync(
        user_prompt=(
            "Use the refined question and specs to generate SQL once, execute once, and return RAGResponse.\n"
            f"Refined question: {refined_question}"
        ),
        deps=specs
    )
    return result.output