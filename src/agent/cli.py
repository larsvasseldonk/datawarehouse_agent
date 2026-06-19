from pathlib import Path
import logfire
import duckdb

from refinement_agent import refinement_agent, QuestionRefinementResponse
from sql_agent import sql_agent, Deps

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT_DIR / "db/db.duckdb"

def main():
    # 1. Initialize shared runtime dependencies
    shared_conn = duckdb.connect(DB_PATH, read_only=True)
    deps = Deps(
        conn=shared_conn,
        cache_path=ROOT_DIR / ".cache/db_metadata.json"
    )
    
    # Track conversation histories independently to avoid cross-contamination
    refinement_history = []
    sql_history = []

    print("====================================================")
    print("🤖 Relational RAG Multi-Agent CLI Initialized 🤖")
    print("Type 'exit' or 'quit' to end the session.")
    print("====================================================\n")

    with logfire.span('multi_agent_pipeline_session'):
        # time.sleep(1)
        while True:
            try:
                # Step 1: Always start with the Refinement Agent
                user_prompt = input("User 👤: ").strip()
                if not user_prompt:
                    continue
                if user_prompt.lower() in ['exit', 'quit']:
                    print("Closing system session. Goodbye!")
                    break

                refinement_result = refinement_agent.run_sync(
                    user_prompt,
                    message_history=refinement_history,
                    deps=deps # type: ignore
                )
                refinement_history = refinement_result.all_messages()

                if not isinstance(refinement_result.output, QuestionRefinementResponse):
                    print(f"\nRefinement Agent 🤖: {refinement_result.output}\n")
                    continue
                    
                # Step 2: Handoff conditionally to the SQL Agent
        
                refinement_data: QuestionRefinementResponse = refinement_result.output
                
                print(f"Refinement Agent 🤖:")
                print(f"  - Refined Question: {refinement_data.refined_question}")
                print(f"  - Ready for SQL: {refinement_data.ready_for_sql}\n")

                print("[System] Handoff conditions met. Routing to SQLAgent...")
                
                # Pass the *refined* question down to the SQL generator instead of raw user noise
                sql_result = sql_agent.run_sync(
                    refinement_data.refined_question,
                    message_history=sql_history,
                    deps=deps
                )
                sql_history = sql_result.all_messages()
                
                print(f"SQL Agent 🤖: {sql_result.output.answer}\n")
                print(f"  - Answer found: {sql_result.output.answer_found}")
                print(f"  - Query executed: \n\n{sql_result.output.sql_query}\n")
                print(f"  - Query success: {sql_result.output.success}")
                print(f"  - Query explanation: {sql_result.output.explanation}\n")
                print("====================================================")
                print("[System] SQL Query completed. Returning control to Refinement Agent.")
                print("====================================================\n")

            except (KeyboardInterrupt, EOFError):
                print("\nTerminal interrupt encountered. Closing cleanly.")
                break
            except Exception as e:
                print(f"\n[Error encountered]: {e}\n")
                
    # Clean up the shared connection on exit
    shared_conn.close()

if __name__ == "__main__":
    logfire.configure(send_to_logfire="if-token-present", console=False)
    logfire.instrument_pydantic_ai()
    main()