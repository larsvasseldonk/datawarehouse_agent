from dotenv import load_dotenv
from pydantic_ai.messages import ModelMessage

from src.agent.llm import LLMProvider
from src.react_agent.clarifier_agent import create_clarifier_agent, extract_refinement_response
from src.react_agent.models import RefinementResponse
from src.react_agent.sql_agent import run_sql_pipeline

import logfire


READY_MARKER = "[READY]"
MAX_CLARIFICATION_TURNS = 8


load_dotenv()
logfire.configure(send_to_logfire="if-token-present", console=False)
logfire.instrument_pydantic_ai()


def run_refinement_loop(model, user_line: str) -> RefinementResponse:
    clarifier = create_clarifier_agent(model)
    history: list[ModelMessage] = []
    current_input = user_line

    for _ in range(MAX_CLARIFICATION_TURNS):
        clarification_result = clarifier.run_sync(current_input, message_history=history)
        history = clarification_result.all_messages()

        response_text = clarification_result.output.strip()

        if READY_MARKER in response_text:
            clean_text = response_text.replace(READY_MARKER, "").strip()
            if clean_text:
                print(f"\nRefinement Agent 🤖: {clean_text}\n")
            return extract_refinement_response(model, history)

        print(f"\nRefinement Agent 🤖: {response_text}\n")
        current_input = input("User 👤: ").strip()
        if not current_input:
            current_input = "Please continue with one clarification question."

    raise RuntimeError("Refinement did not complete within the maximum clarification turns.")


def main() -> None:
    print("=====================================================================")
    print("NS Social Safety ReAct Agent CLI")
    print("=====================================================================")
    print("Ask an analytical question regarding incident metrics.")
    print("Type 'exit' or 'quit' to close.\n")

    model = LLMProvider().get_openai_model()

    while True:
        try:
            user_line = input("User 👤: ").strip()
            if not user_line:
                continue
            if user_line.lower() in ["exit", "quit"]:
                print("Closing system session. Goodbye!")
                break

            refinement_output = run_refinement_loop(model, user_line)

            print("\n[System] Refinement complete. Handing off to SQL agent...\n")

            sql_output = run_sql_pipeline(
                model=model,
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

        except RuntimeError as e:
            print(f"\n[System] {e}\n")
        except (KeyboardInterrupt, EOFError):
            print("\nTerminal interrupt encountered. Closing cleanly.")
            break


if __name__ == "__main__":
    main()
