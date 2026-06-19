from dataclasses import dataclass
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel, Field
from pathlib import Path
import json
import os
import duckdb
import logfire


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT_DIR / "db/db.duckdb"

@dataclass
class RefinementAgentConfig:
    """Configuration settings for the QuestionRefinementAgent."""
    name: str = "QuestionRefinementAgent"
    model: str = "gpt-4o-mini"

@dataclass
class Deps:
    """Runtime dependencies shared across tool executions and prompts."""
    conn: duckdb.DuckDBPyConnection = duckdb.connect(DB_PATH, read_only=True)
    cache_path: Path = ROOT_DIR / ".cache/db_metadata.json"


class QuestionRefinementResponse(BaseModel):
    """
    This model represents the output of the question refinement stage, which includes
    the refined question and any additional specifications that may be needed for the SQL query.
    """

    refined_question: str = Field(
        description="The refined version of the user's original question, clarified and structured for SQL generation")
    date_range: dict = Field(
        description="A dictionary containing 'from_date' and 'to_date' keys with corresponding date values (YYYY-MM-DD format) representing the validated date range for querying the database"
    )
    stations: list[str] = Field(
        description="A list of validated station names (dienstregelpuntnaam) to filter the data, if applicable"
    )
    additional_specs: dict = Field(
        description="Any additional specifications or constraints extracted during question refinement that may be relevant for SQL query generation, represented as a dictionary"
    )
    ready_for_sql: bool = Field(
        description="A handoff boolean indicating whether the question is ready for SQL query generation"
    )


refinement_config = RefinementAgentConfig()
refinement_agent = Agent(
    name=refinement_config.name,
    model="openai-chat:" + refinement_config.model,
    deps_type=Deps,
    output_type=[str, QuestionRefinementResponse],
) # type: ignore


def get_sql_tables_str(cache_path: Path) -> str:
    """Returns a formatted string of available database 
    tables and their descriptions for the agent.
    """
    try:
        with open(cache_path, "r") as f:
            db_metadata = json.load(f)
            tables_str = ""
            for table in db_metadata.values():
                tables_str += f"Table: {table['name']}\nDescription: {table['comment']}\n\n"
            return tables_str.strip()
    except Exception as e:
        raise Exception(f"Error reading database metadata: {e}")


@refinement_agent.instructions
def provide_instructions(ctx: RunContext[Deps]) -> str:
    """Assembles dynamic evaluation instructions mixed with active data availability layout."""
    
    table_availability_str = get_sql_tables_str(ctx.deps.cache_path)
    return f"""
You are a question refinement agent. Your task is to evaluate the user's 
question and determine whether it can be answered by the SQL agent based 
on the available data. 

You will assess the question for clarity, completeness, and data availability.
If you can't extract all necessary information from the user's question, 
ask clarifying or follow-up questions.

### AVAILABLE DATABASE TABLES:
{table_availability_str.strip()}
""".strip()


if __name__ == "__main__":
    logfire.configure(send_to_logfire="if-token-present")
    logfire.instrument_pydantic_ai()

    deps = Deps()
    refinement_history = []

    with logfire.span('refinement_agent_session'):
        while True:
            try:
                user_prompt = input("User 👤: ").strip()
                if not user_prompt:
                    continue
                if user_prompt.lower() in ['exit', 'quit']:
                    print("Closing system session. Goodbye!")
                    break
                
                refinement_result = refinement_agent.run_sync(
                    user_prompt, 
                    message_history=refinement_history,
                    deps=deps
                )

                refinement_history = refinement_result.all_messages()
                print(f"\nRefinement Agent 🤖: {refinement_result.output}\n")

            except (KeyboardInterrupt, EOFError):
                print("\nTerminal interrupt encountered. Closing cleanly.")
                break