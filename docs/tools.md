# Short list of tools for Data Assistant Agent:

retrieve_context
Description: Finds relevant warehouse metadata plus similar previously verified NL→SQL pairs before any SQL drafting.
When to call: First step for every user question.
Inputs: user_question
Returns: schema_context, verified_query_examples, retrieval_confidence

draft_sql_candidate
Description: Generates a candidate SQL query (and short rationale for analyst) using retrieved context.
When to call: After context retrieval, for new or partially matched questions.
Inputs: user_question, schema_context, verified_query_examples
Returns: sql_candidate, reasoning_summary, generation_confidence

review_gate_and_queue
Description: Decides whether SQL is safe and already trusted enough to run now, otherwise stores it for daily analyst review.
When to call: After SQL drafting, always.
Inputs: user_question, sql_candidate, confidences, guardrail_policy
Returns: decision run_now_or_queue, review_ticket_id_optional, analyst_payload

run_verified_query
Description: Executes only approved or previously verified read-only SQL against DuckDB and returns structured results.
When to call: Only if review gate returns run_now.
Inputs: sql_verified, row_limit, timeout_seconds
Returns: rows, row_count, column_names, execution_status, execution_error_optional

compose_whatsapp_answer
Description: Converts results into short end-user text without exposing SQL, and handles pending-review responses when needed.
When to call: Final step for every request.
Inputs: user_question, query_results_or_pending_status, trust_summary
Returns: user_message_text