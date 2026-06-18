from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage

from src.react_agent.models import RefinementResponse
from src.react_agent.tools import PyTools, SQLTools


db_tools = SQLTools()
py_tools = PyTools()


def _build_station_context() -> str:
    """Build a formatted context of all available stations and regions."""
    stations = db_tools.get_all_stations()

    regions = {}
    for station in stations:
        region = station.get("regio_rsv", "Unknown")
        if region not in regions:
            regions[region] = []
        regions[region].append({
            "code": station["code"],
            "naam": station["naam"],
        })

    context_lines = ["## Available Stations by Region (RSV):\n"]
    for region in sorted(regions.keys()):
        context_lines.append(f"### {region}")
        for station in sorted(regions[region], key=lambda x: x["naam"]):
            context_lines.append(f"- {station['naam']} ({station['code']})")
        context_lines.append("")

    return "\n".join(context_lines)


CLARIFIER_INSTRUCTIONS = f"""
# Role: ReAct Clarifier Agent
You refine user questions for incident analytics in a conversational way.

## Goal
Collect enough information to hand off to SQL:
- A valid date range (from_date and to_date)
- Valid station names when stations are mentioned
- Any additional filters that user clearly asks for

## Behavior
- Ask exactly one concise follow-up question per turn when information is missing.
- For relative dates (last week, yesterday, etc.), call `get_current_datetime` first and convert to explicit dates.
- Validate complete dates with `validate_date_range` before finalizing.
- Validate station names with `validate_station_name` when a station is mentioned.
- Never generate SQL.
- Keep wording short and practical.

## Completion Signal
When the request is ready for structured extraction, end your response with the exact token: [READY]

{_build_station_context()}
""".strip()


EXTRACTOR_INSTRUCTIONS = """
# Role: Refinement Extractor
Extract a structured RefinementResponse from conversation history.

Rules:
- Use only details established in the conversation.
- Keep `ready_for_sql=true` only if both dates are present and validated.
- If dates are still missing, set `ready_for_sql=false` and provide one concise clarification_question.
- Do not invent station names.
""".strip()


def create_clarifier_agent(model) -> Agent:
    agent = Agent(
        name="ReactClarifierAgent",
        model=model,
        system_prompt=CLARIFIER_INSTRUCTIONS,
        output_type=str,
    )

    @agent.tool
    def validate_station_name(ctx: RunContext[None], station_name: str) -> str:
        """Validates that a station name exists exactly in the database."""
        is_valid, message = db_tools.validate_station_name(station_name)
        return message

    @agent.tool
    def get_current_datetime(ctx: RunContext[None]) -> str:
        """Returns current Amsterdam datetime context for resolving relative dates."""
        current = py_tools.get_current_datetime()
        return (
            f"Current datetime: {current['current_datetime_iso']} | "
            f"date={current['current_date']} | "
            f"time={current['current_time']} | "
            f"weekday={current['weekday']} | "
            f"timezone={current['timezone']}"
        )

    @agent.tool
    def validate_date_range(ctx: RunContext[None], from_date: str, to_date: str) -> str:
        """Validates whether the requested date range is within available incident data."""
        is_valid, min_date, max_date, message = db_tools.validate_date_range(from_date, to_date)
        return message

    return agent


def extract_refinement_response(model, message_history: list[ModelMessage]) -> RefinementResponse:
    extractor = Agent(
        name="ReactRefinementExtractor",
        model=model,
        system_prompt=EXTRACTOR_INSTRUCTIONS,
        output_type=RefinementResponse,
    )

    result = extractor.run_sync(
        "Extract RefinementResponse from the conversation above.",
        message_history=message_history,
    )
    return result.output
