from dataclasses import dataclass
from pydantic_ai import Agent, RunContext

from src.agent.llm import LLMProvider
from src.agent.models import RefinementResponse
from src.agent.tools import PyTools, SQLTools


db_tools = SQLTools()
py_tools = PyTools()
model_provider = LLMProvider()
model = model_provider.get_openai_model()


def _build_station_context() -> str:
    """Build a formatted context of all available stations and regions."""
    stations = db_tools.get_all_stations()
    
    # Group by region
    regions = {}
    for station in stations:
        region = station.get("regio_rsv", "Unknown")
        if region not in regions:
            regions[region] = []
        regions[region].append({
            "code": station["code"],
            "naam": station["naam"]
        })
    
    context_lines = ["## Available Stations by Region (RSV):\n"]
    for region in sorted(regions.keys()):
        context_lines.append(f"### {region}")
        for station in sorted(regions[region], key=lambda x: x["naam"]):
            context_lines.append(f"- {station['naam']} ({station['code']})")
        context_lines.append("")
    
    return "\n".join(context_lines)


DEFAULT_INSTRUCTIONS = f"""
# Role: Question Refinement Agent
You are the first stage in a two-agent pipeline.
Your only job is to refine the user question into a structured handoff payload.

## Output contract
Always return a `RefinementResponse` object.

**CRITICAL: The date_range (from_date and to_date) MUST be known before setting ready_for_sql=true.**

If clarification is needed (including missing dates or station names):
- `ready_for_sql` = false
- ask exactly one concise follow-up in `clarification_question` to get the missing information

If ready for SQL handoff (ONLY when date_range is complete and all stations are valid):
- `ready_for_sql` = true
- `clarification_question` = null
- provide a clean `refined_question`
- provide `date_range` with both from_date and to_date
- provide `query_specs` with all extracted details

## Rules
- Never set ready_for_sql=true unless BOTH from_date and to_date are filled in date_range.
- For relative date phrases (e.g. "last week", "last 2 weeks", "last month", "today", "yesterday"), always call `get_current_datetime` first and convert to explicit YYYY-MM-DD dates.
- Always validate dates using the `validate_date_range` tool before setting ready_for_sql=true.
- Always validate station names using the `validate_station_name` tool if a specific station is mentioned.
- Station names MUST match exactly from the available stations list below.
- Never generate SQL.
- Keep the refinement simple and deterministic.
- If the user asks something outside this database domain, mark `ready_for_sql` as false and ask one short clarification to steer back to incidents data.

{_build_station_context()}
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
def validate_station_name(ctx: RunContext[None], station_name: str) -> str:
    """
    Validates that a station name exists exactly in the database.
    Use this when the user mentions a specific station to ensure it's valid.
    
    Args:
        station_name: The exact station name to validate
    
    Returns:
        Validation result indicating if the station exists and its region information.
    """
    is_valid, message = db_tools.validate_station_name(station_name)
    return message


@refinement_agent.tool
def get_current_datetime(ctx: RunContext[None]) -> str:
    """
    Returns the current Amsterdam datetime context.
    Use this to resolve relative date expressions into explicit date boundaries.

    Returns:
        A formatted string with current datetime, date, weekday, and timezone.
    """
    current = py_tools.get_current_datetime()
    return (
        f"Current datetime: {current['current_datetime_iso']} | "
        f"date={current['current_date']} | "
        f"time={current['current_time']} | "
        f"weekday={current['weekday']} | "
        f"timezone={current['timezone']}"
    )


@refinement_agent.tool
def validate_date_range(ctx: RunContext[None], from_date: str, to_date: str) -> str:
    """
    Validates that the requested date range falls within the database's available incident data.
    Use this to ensure dates are valid before setting ready_for_sql=true.
    
    Args:
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format
    
    Returns:
        Validation result with database bounds and whether dates are valid.
    """
    is_valid, min_date, max_date, message = db_tools.validate_date_range(from_date, to_date)
    return message

