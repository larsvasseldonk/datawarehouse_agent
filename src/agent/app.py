from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import duckdb
import logfire
import plotly.io as pio
import streamlit as st
from dotenv import load_dotenv
from pydantic_ai import FunctionToolCallEvent

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT_DIR / "db/db.duckdb"

# Load environment variables (API keys) from the repo-root .env before importing
# the agents, since the app is launched from src/agent (see Makefile) so a bare
# load_dotenv() would not reliably find the .env at the project root.
load_dotenv(ROOT_DIR / ".env")

from refinement_agent import QuestionRefinementResponse, refinement_agent
from sql_agent import Deps, sql_agent

CACHE_PATH = ROOT_DIR / ".cache/db_metadata.json"
FEEDBACK_PATH = Path(__file__).resolve().parent / "evals" / "feedback.json"

# USD to EUR exchange rate, matching the evals pipeline (run_questions.py).
USD_TO_EUR = 0.87


def cost_eur(input_tokens: int, output_tokens: int) -> float:
    """Cost in EUR for a single request (gpt-4o-mini pricing), as in the evals."""
    input_cost = (input_tokens / 1_000_000) * 0.15
    output_cost = (output_tokens / 1_000_000) * 0.60
    return (input_cost + output_cost) * USD_TO_EUR


def collect_tool_calls(result) -> list[dict]:
    """Extract tool calls from a pydantic-ai RunResult, matching the evals format."""
    tools = []
    for message in result.new_messages():
        for part in message.parts:
            if part.part_kind == "tool-call" and part.tool_name != "final_result":
                tools.append({"name": part.tool_name, "args": part.args})
    return tools


def init_session_state() -> None:
    if "refinement_history" not in st.session_state:
        st.session_state.refinement_history = []
    if "sql_history" not in st.session_state:
        st.session_state.sql_history = []
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "feedback_records" not in st.session_state:
        st.session_state.feedback_records = {}



@st.cache_resource
def init_logfire() -> None:
    logfire.configure(send_to_logfire="if-token-present", console=False)
    logfire.instrument_pydantic_ai()


@st.cache_resource
def get_deps() -> Deps:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(DB_PATH, read_only=True)
    return Deps(conn=conn, cache_path=CACHE_PATH)


async def _run_agent_with_live_tools(agent, prompt: str, message_history, deps: Deps, placeholder):
    tool_calls: list[str] = []

    placeholder.markdown("_Waiting for tool calls..._")

    async def event_stream_handler(_ctx, event_stream):
        async for event in event_stream:
            if isinstance(event, FunctionToolCallEvent):
                tool_calls.append(event.part.tool_name)
                placeholder.markdown("\n".join(f"- {name}" for name in tool_calls))

    result = await agent.run(
        prompt,
        message_history=message_history,
        deps=deps,
        event_stream_handler=event_stream_handler,
    )

    if not tool_calls:
        placeholder.markdown("_No tool calls._")

    return result, tool_calls


def run_agent_with_live_tools(agent, prompt: str, message_history, deps: Deps, placeholder):
    return asyncio.run(_run_agent_with_live_tools(agent, prompt, message_history, deps, placeholder))


def persist_feedback() -> None:
    """Write all collected feedback records to feedback.json (results.json shape)."""
    records = list(st.session_state.feedback_records.values())
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK_PATH.write_text(
        json.dumps(records, indent=2, ensure_ascii=False, default=str)
    )


def submit_feedback(message: dict, idx: int, selection: int, comment: str = "") -> None:
    message["feedback"] = selection
    rating = "up" if selection == 1 else "down"

    # Store the full run record (results.json schema) plus the feedback, keyed by
    # message index so re-submissions update in place instead of duplicating.
    record = dict(message.get("record") or {})
    record["feedback"] = {"rating": rating, "comment": comment}
    st.session_state.feedback_records[idx] = record

    logfire.info(
        "user_feedback",
        feedback=rating,
        comment=comment or None,
        question=message.get("user_prompt"),
        answer=message.get("answer"),
    )
    persist_feedback()


def render_feedback(message: dict, idx: int) -> None:
    st.caption("Was this answer helpful?")
    selection = st.feedback("thumbs", key=f"feedback_{idx}")

    if selection is None:
        return

    if selection == 1:
        if message.get("feedback") != 1:
            submit_feedback(message, idx, 1)
        st.success("Thanks for your feedback!")
        return

    # Thumbs down: collect an optional free-text comment.
    with st.popover("Tell us what went wrong (optional)"):
        comment = st.text_area(
            "What was wrong with this answer?",
            key=f"feedback_comment_{idx}",
            label_visibility="collapsed",
        )
        if st.button("Submit feedback", key=f"feedback_submit_{idx}"):
            submit_feedback(message, idx, 0, comment)
            st.success("Thanks for your feedback!")


def render_message(message: dict, idx: int) -> None:
    msg_type = message.get("type")

    if msg_type == "user":
        st.markdown(message["content"])
        return

    if msg_type == "error":
        st.error(message["content"])
        return

    if msg_type == "clarification":
        st.markdown(message["clarification"])
        render_feedback(message, idx)
        return

    # Final answer is the primary content.
    st.markdown(message["answer"])

    if message.get("figure_json"):
        st.plotly_chart(pio.from_json(message["figure_json"]), use_container_width=True)

    col1, col2 = st.columns(2)
    col1.markdown("✅ Answer found" if message["answer_found"] else "⚠️ No answer")
    col2.markdown("✅ Query OK" if message["success"] else "❌ Query failed")

    with st.expander("🔍 Refinement details"):
        st.markdown(f"- **Refined question:** {message['refined_question']}")
        st.markdown(f"- **Ready for SQL:** {message['ready_for_sql']}")

    with st.expander("🛠️ SQL details"):
        st.code(message["sql_query"], language="sql")
        st.markdown(f"**Explanation:** {message['explanation']}")

    render_feedback(message, idx)


def render_chat_history() -> None:
    for idx, message in enumerate(st.session_state.chat_messages):
        with st.chat_message(message["role"]):
            render_message(message, idx)


def build_assistant_response(user_prompt: str, deps: Deps) -> dict:
    with logfire.span("multi_agent_pipeline_session"):
        record: dict = {"input": {"question": user_prompt}}

        with st.status("Refinement agent is thinking...", expanded=True) as status:
            placeholder = st.empty()
            t_ref = time.perf_counter()
            refinement_result, _ = run_agent_with_live_tools(
                refinement_agent,
                user_prompt,
                st.session_state.refinement_history,
                deps,
                placeholder,
            )
            ref_elapsed = time.perf_counter() - t_ref
            status.update(label="Refinement complete", state="complete", expanded=False)

        st.session_state.refinement_history = refinement_result.all_messages()

        is_refined = isinstance(refinement_result.output, QuestionRefinementResponse)
        ref_in = refinement_result.usage.input_tokens or 0
        ref_out = refinement_result.usage.output_tokens or 0
        ref_cost = cost_eur(ref_in, ref_out)

        record["refinement"] = (
            refinement_result.output.model_dump()
            if is_refined
            else {"clarification": str(refinement_result.output)}
        )
        record["tools_refinement"] = collect_tool_calls(refinement_result)
        record["refinement_time_s"] = ref_elapsed
        record["refinement_cost_eur"] = ref_cost
        record["refinement_tokens"] = {"input": ref_in, "output": ref_out}

        if not is_refined:
            record["sql"] = None
            record["tools_sql"] = []
            record["sql_time_s"] = 0.0
            record["sql_cost_eur"] = 0.0
            record["sql_tokens"] = {"input": 0, "output": 0}
            record["execution_time_s"] = ref_elapsed
            record["cost_eur"] = ref_cost
            record["tokens"] = dict(record["refinement_tokens"])
            return {
                "role": "assistant",
                "type": "clarification",
                "user_prompt": user_prompt,
                "clarification": str(refinement_result.output),
                "record": record,
            }

        refinement_data = refinement_result.output

        with st.status("SQL agent is thinking...", expanded=True) as status:
            placeholder = st.empty()
            t_sql = time.perf_counter()
            # Reset any chart from a previous turn so we only render a fresh one.
            deps.figure_json = None
            sql_result, _ = run_agent_with_live_tools(
                sql_agent,
                refinement_data.refined_question,
                st.session_state.sql_history,
                deps,
                placeholder,
            )
            sql_elapsed = time.perf_counter() - t_sql
            status.update(label="SQL complete", state="complete", expanded=False)

        st.session_state.sql_history = sql_result.all_messages()
        sql_output = sql_result.output

        sql_in = sql_result.usage.input_tokens or 0
        sql_out = sql_result.usage.output_tokens or 0
        sql_run_cost = cost_eur(sql_in, sql_out)

        record["sql"] = sql_output.model_dump()
        record["tools_sql"] = collect_tool_calls(sql_result)
        record["sql_time_s"] = sql_elapsed
        record["sql_cost_eur"] = sql_run_cost
        record["sql_tokens"] = {"input": sql_in, "output": sql_out}
        record["execution_time_s"] = ref_elapsed + sql_elapsed
        record["cost_eur"] = ref_cost + sql_run_cost
        record["tokens"] = {"input": ref_in + sql_in, "output": ref_out + sql_out}

        return {
            "role": "assistant",
            "type": "answer",
            "user_prompt": user_prompt,
            "refined_question": refinement_data.refined_question,
            "ready_for_sql": refinement_data.ready_for_sql,
            "answer": sql_output.answer,
            "answer_found": sql_output.answer_found,
            "success": sql_output.success,
            "explanation": sql_output.explanation,
            "sql_query": sql_output.sql_query,
            "figure_json": deps.figure_json,
            "record": record,
        }


def main() -> None:
    load_dotenv(ROOT_DIR / ".env")
    init_logfire()

    st.set_page_config(page_title="Datawarehouse Agent", page_icon="🤖", layout="wide")
    st.title("Datawarehouse Agent")
    st.caption("Refinement and SQL agents in one chat, with live tool-call visibility.")

    if not DB_PATH.exists():
        st.error(f"Database file not found at: {DB_PATH}")
        st.stop()

    if not os.getenv("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY is not set. Add it to your environment or .env file.")
        st.stop()

    init_session_state()

    with st.sidebar:
        st.subheader("Session")
        if st.button("Clear conversation"):
            st.session_state.refinement_history = []
            st.session_state.sql_history = []
            st.session_state.chat_messages = []
            st.rerun()

    render_chat_history()

    user_prompt = st.chat_input("Ask a question about incidents...")
    if not user_prompt:
        return

    st.session_state.chat_messages.append(
        {"role": "user", "type": "user", "content": user_prompt}
    )

    with st.chat_message("user"):
        st.markdown(user_prompt)

    deps = get_deps()

    with st.chat_message("assistant"):
        try:
            message = build_assistant_response(user_prompt, deps)
        except Exception as exc:
            message = {
                "role": "assistant",
                "type": "error",
                "content": f"Error while running agents: {exc}",
            }
            st.error(message["content"])

    st.session_state.chat_messages.append(message)
    st.rerun()


if __name__ == "__main__":
    main()
