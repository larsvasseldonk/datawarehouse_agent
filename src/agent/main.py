from dotenv import load_dotenv
from pydantic_ai.messages import ModelMessage
from src.agent.refinement_agent import refinement_agent
from src.agent.sql_agent import run_sql_pipeline
from src.agent.models import RefinementResponse

import logfire

load_dotenv()

logfire.configure(send_to_logfire="if-token-present", console=False)
logfire.instrument_pydantic_ai()

def main():
    print("=====================================================================")
    print("NS Social Safety Interactive Agent CLI Terminal Dashboard")
    print("=====================================================================")
    print("Ask an analytical question regarding safety incident metrics logs.")
    print("Type 'exit' or 'quit' to close execution panels safely.\n")

    refinement_history: list[ModelMessage] = []

    while True:
        try:
            user_line = input("User 👤: ").strip()
            if not user_line:
                continue
            if user_line.lower() in ['exit', 'quit']:
                print("Closing system session. Goodbye!")
                break
            
            refinement_result = refinement_agent.run_sync(
                user_line, 
                message_history=refinement_history
            )

            refinement_history = refinement_result.all_messages()
            refinement_output: RefinementResponse = refinement_result.output

            if not refinement_output.ready_for_sql:
                follow_up = refinement_output.clarification_question or (
                    "Can you clarify what date range or scope you want for the incidents query?"
                )
                print(f"\nRefinement Agent 🤖: {follow_up}\n")
                continue

            print("\n[System] Refinement complete. Handing off to SQL agent...\n")

            sql_output = run_sql_pipeline(
                specs=refinement_output.query_specs,
                refined_question=refinement_output.refined_question,
            )

            print(f"SQL Agent 🤖: {sql_output.answer}\n")
            print(f"Rows: {sql_output.row_count}")
            print(f"Query success: {sql_output.query_executed_successfully}")
            print(f"SQL:\n{sql_output.sql_query}\n")

            if sql_output.followup_questions:
                print("Follow-up ideas:")
                for idx, question in enumerate(sql_output.followup_questions, start=1):
                    print(f"{idx}. {question}")
                print()
                
        except (KeyboardInterrupt, EOFError):
            print("\nTerminal interrupt encountered. Closing cleanly.")
            break

if __name__ == "__main__":
    main()