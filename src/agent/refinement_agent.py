from dataclasses import dataclass
from pydantic_ai import Agent, RunContext

from src.agent.llm import LLMProvider
from src.agent.models import RefinementResponse
from src.agent.tools import SQLTools


db_tools = SQLTools()
model_provider = LLMProvider()
model = model_provider.get_chatns_model()


DEFAULT_INSTRUCTIONS = """
# Role: Question Refinement Agent
You are the first stage in a two-agent pipeline.
Your only job is to refine the user question into a structured handoff payload.

## Output contract
Always return a `RefinementResponse` object.

If clarification is needed:
- `ready_for_sql` = false
- ask exactly one concise follow-up in `clarification_question`
- still fill `refined_question` and `query_specs` with the best-known values so far

If ready for SQL handoff:
- `ready_for_sql` = true
- `clarification_question` = null
- provide a clean `refined_question`
- provide `query_specs` with all extracted details

## Rules
- Never generate SQL.
- Never call any tool except `verify_station_identifier` when station naming is ambiguous.
- Keep the refinement simple and deterministic.
- If the user asks something outside this database domain, mark `ready_for_sql` as false and ask one short clarification to steer back to incidents data.
""".strip()


@dataclass
class RefinementAgentConfig:
    name: str = "RefinementAgent"
    instructions: str = DEFAULT_INSTRUCTIONS


agent_config = RefinementAgentConfig()
refinement_agent = Agent(
    name=agent_config.name,
    model=model,
    system_prompt=agent_config.instructions,
    output_type=RefinementResponse,
)


@refinement_agent.tool
def verify_station_identifier(ctx: RunContext[None], partial_name: str) -> str:
    """
    Performs an active pattern-matching text search across the dimdienstregelpunt table. 
    Use this when a user names a station loosely to guarantee structural alignment.
    """
    matched_codes = db_tools.search_station_name(partial_name)
    if not matched_codes:
        return f"No matching station records found for string expression: '{partial_name}'"
    return f"Valid database shortcode matches found inside schema: {matched_codes}"