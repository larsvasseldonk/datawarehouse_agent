from pydantic_ai import Agent
from pydantic import BaseModel, Field

from pathlib import Path
import json

DB_METADATA_CACHE_FILEPATH = Path(".cache/db_metadata.json")

DEFAULT_INSTRUCTIONS = """
You are a question refinement agent. Your task is to evaluate the user's 
question and determine whether it can be answered by the SQL agent based 
on the available data. 

You will assess the question for clarity, completeness, and data availability.

If you can't extract all necessary information from the user's question, 
ask follow-up questions.
""".strip()


def get_data_availability_instructions() -> str:
    """
    Returns a string containing instructions for the question refinement agent to assess data availability.
    """

    script_dir = Path(__file__).resolve().parent
    cache_file = script_dir / "../../" / DB_METADATA_CACHE_FILEPATH

    try:
        with open(cache_file, "r") as f:
            db_metadata = json.load(f)
            table_availability_str = ""
            for table in db_metadata.values():
                table_availability_str += f"Table: {table['name']}\nDescription: {table['comment']}\n"
            return table_availability_str
    except Exception as e:
        raise Exception(f"Error while reading Database metadata cache: {e}")
        
        
TABLE_AVAILABILITY_INSTRUCTIONS = f"""
The following tables are available in the database, along with their descriptions:
{get_data_availability_instructions()}
""".strip()


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

def create_refinement_agent() -> Agent:
    """
    Creates and returns a question refinement agent that evaluates the user's question
    and determines whether it can be answered by the SQL agent based on the available data.
    """
    return Agent(
        name="QuestionRefinementAgent",
        model="openai-chat:gpt-4o-mini",
        output_type=[str, QuestionRefinementResponse],
        instructions=DEFAULT_INSTRUCTIONS + "\n\n" + TABLE_AVAILABILITY_INSTRUCTIONS,
    ) # type: ignore

if __name__ == "__main__":

    refinement_agent = create_refinement_agent()
    print(get_data_availability_instructions())
    refinement_history = []
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
                message_history=refinement_history
            )

            refinement_history = refinement_result.all_messages()
            print(f"\nRefinement Agent 🤖: {refinement_result.output}\n")

                
        except (KeyboardInterrupt, EOFError):
            print("\nTerminal interrupt encountered. Closing cleanly.")
            break