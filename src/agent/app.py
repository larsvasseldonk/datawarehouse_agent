from __future__ import annotations

import asyncio
import os
from pathlib import Path

import duckdb
import streamlit as st
from dotenv import load_dotenv
from pydantic_ai import FunctionToolCallEvent

from refinement_agent import QuestionRefinementResponse, refinement_agent
from sql_agent import Deps, sql_agent

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT_DIR / "db/db.duckdb"
CACHE_PATH = ROOT_DIR / ".cache/db_metadata.json"


def init_session_state() -> None:
    if "refinement_history" not in st.session_state:
        st.session_state.refinement_history = []
    if "sql_history" not in st.session_state:
        st.session_state.sql_history = []
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []


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


def render_chat_history() -> None:
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def build_assistant_response(user_prompt: str, deps: Deps) -> str:
    response_lines: list[str] = []

    st.markdown("### Refinement Agent")
    st.markdown("**Tool calls (live):**")
    refinement_placeholder = st.empty()

    with st.spinner("Refinement agent is thinking..."):
        refinement_result, _ = run_agent_with_live_tools(
            refinement_agent,
            user_prompt,
            st.session_state.refinement_history,
            deps,
            refinement_placeholder,
        )

    st.session_state.refinement_history = refinement_result.all_messages()

    if not isinstance(refinement_result.output, QuestionRefinementResponse):
        clarification = str(refinement_result.output)
        st.markdown(clarification)

        response_lines.append("### Refinement Agent")
        response_lines.append(clarification)
        return "\n\n".join(response_lines)

    refinement_data = refinement_result.output

    st.markdown(f"- Refined Question: {refinement_data.refined_question}")
    st.markdown(f"- Ready for SQL: {refinement_data.ready_for_sql}")

    response_lines.append("### Refinement Agent")
    response_lines.append(f"- Refined Question: {refinement_data.refined_question}")
    response_lines.append(f"- Ready for SQL: {refinement_data.ready_for_sql}")

    st.markdown("### SQL Agent")
    st.markdown("**Tool calls (live):**")
    sql_placeholder = st.empty()

    with st.spinner("SQL agent is thinking..."):
        sql_result, _ = run_agent_with_live_tools(
            sql_agent,
            refinement_data.refined_question,
            st.session_state.sql_history,
            deps,
            sql_placeholder,
        )

    st.session_state.sql_history = sql_result.all_messages()

    sql_output = sql_result.output

    st.markdown(sql_output.answer)
    st.markdown(f"- Answer found: {sql_output.answer_found}")
    st.markdown(f"- Query success: {sql_output.success}")
    st.markdown(f"- Query explanation: {sql_output.explanation}")
    st.code(sql_output.sql_query, language="sql")

    response_lines.append("### SQL Agent")
    response_lines.append(sql_output.answer)
    response_lines.append(f"- Answer found: {sql_output.answer_found}")
    response_lines.append(f"- Query success: {sql_output.success}")
    response_lines.append(f"- Query explanation: {sql_output.explanation}")
    response_lines.append(f"```sql\n{sql_output.sql_query}\n```")

    return "\n\n".join(response_lines)


def main() -> None:
    load_dotenv()

    st.set_page_config(page_title="Relational RAG Multi-Agent", page_icon="🤖", layout="wide")
    st.title("Relational RAG Multi-Agent")
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

    st.session_state.chat_messages.append({"role": "user", "content": user_prompt})

    with st.chat_message("user"):
        st.markdown(user_prompt)

    deps = get_deps()

    with st.chat_message("assistant"):
        try:
            assistant_content = build_assistant_response(user_prompt, deps)
        except Exception as exc:
            assistant_content = f"Error while running agents: {exc}"
            st.error(assistant_content)

    st.session_state.chat_messages.append({"role": "assistant", "content": assistant_content})


if __name__ == "__main__":
    main()
