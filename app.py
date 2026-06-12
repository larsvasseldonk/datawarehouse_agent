import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

import streamlit as st
from jaxn import JSONParserHandler, StreamingJSONParser
from pydantic_ai import Agent
from pydantic_ai._agent_graph import CallToolsNode, ModelRequestNode
from pydantic_ai.messages import FunctionToolCallEvent

from src.agent.agent import RAGResponse, SQLAgentConfig, create_agent
from src.agent.llm import LLMProvider
from src.agent.tools import SQLTools


@dataclass
class LivePlaceholders:
    answer: Any
    activity: Any
    metadata: Any


class StreamResultHandler(JSONParserHandler):
    """Collect streamed final_result fields and forward incremental updates."""

    def __init__(self, on_answer_chunk, on_field_end, on_array_item_end):
        self.on_answer_chunk_cb = on_answer_chunk
        self.on_field_end_cb = on_field_end
        self.on_array_item_end_cb = on_array_item_end

    def on_value_chunk(self, path: str, field_name: str, chunk: str) -> None:
        if path == "" and field_name == "answer":
            self.on_answer_chunk_cb(chunk)

    def on_field_end(
        self, path: str, field_name: str, value: str, parsed_value: Any = None
    ) -> None:
        self.on_field_end_cb(path, field_name, parsed_value)

    def on_array_item_end(self, path: str, field_name: str, item: Any = None) -> None:
        self.on_array_item_end_cb(path, field_name, item)


@st.cache_resource(show_spinner=False)
def get_agent_bundle() -> dict[str, Any]:
    sql_tools = SQLTools()
    agent = create_agent(SQLAgentConfig(), sql_tools, LLMProvider())
    return {"agent": agent, "sql_tools": sql_tools}


def ensure_session_state() -> None:
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "agent_history" not in st.session_state:
        st.session_state.agent_history = []
    if "pending_followups" not in st.session_state:
        st.session_state.pending_followups = []
    if "pending_base_question" not in st.session_state:
        st.session_state.pending_base_question = ""
    if "followup_token" not in st.session_state:
        st.session_state.followup_token = 0
    if "index_loaded" not in st.session_state:
        st.session_state.index_loaded = False


def clear_conversation() -> None:
    st.session_state.chat_messages = []
    st.session_state.agent_history = []
    st.session_state.pending_followups = []
    st.session_state.pending_base_question = ""
    st.session_state.followup_token += 1


def render_metadata_row(metadata_placeholder: Any, confidence: float | None, found_answer: bool | None) -> None:
    if confidence is None and found_answer is None:
        metadata_placeholder.empty()
        return

    confidence_pct = f"{max(0.0, min(1.0, confidence or 0.0)) * 100:.0f}%"
    found_text = "Yes" if bool(found_answer) else "No"

    with metadata_placeholder.container():
        col1, col2 = st.columns(2)
        col1.markdown(
            (
                "<div style='padding:0.35rem 0.6rem;border:1px solid rgba(128,128,128,0.35);"
                "border-radius:10px;'>"
                "<div style='font-size:0.72rem;opacity:0.72;'>CONFIDENCE</div>"
                f"<div style='font-size:1.05rem;font-weight:700;'>{confidence_pct}</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        col2.markdown(
            (
                "<div style='padding:0.35rem 0.6rem;border:1px solid rgba(128,128,128,0.35);"
                "border-radius:10px;'>"
                "<div style='font-size:0.72rem;opacity:0.72;'>FOUND IN DOCS</div>"
                f"<div style='font-size:1.05rem;font-weight:700;'>{found_text}</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )


def render_activity_panel(activity_placeholder: Any, actions: list[str], status: str) -> None:
    with activity_placeholder.container():
        with st.expander(f"Activity - {status}", expanded=True):
            if not actions:
                st.caption("Thinking...")
            else:
                for action in actions:
                    st.caption(f"- {action}")


def extract_sql_from_args(args: Any) -> str:
    if isinstance(args, dict):
        value = args.get("query")
        return value if isinstance(value, str) else ""

    if isinstance(args, str):
        try:
            payload = json.loads(args)
            if isinstance(payload, dict):
                value = payload.get("query")
                return value if isinstance(value, str) else ""
        except Exception:
            return ""

    return ""


def extract_table_names_from_sql(query: str) -> list[str]:
    if not query:
        return []
    names = re.findall(r"(?i)\b(?:from|join)\s+([a-z_][a-z0-9_]*)", query)
    deduped = []
    seen = set()
    for name in names:
        lower = name.lower()
        if lower not in seen:
            seen.add(lower)
            deduped.append(lower)
    return deduped


async def run_agent_stream(
    agent,
    prompt: str,
    message_history,
    placeholders: LivePlaceholders,
) -> tuple[dict[str, Any], list[Any]]:
    answer = ""
    confidence = None
    found_answer = None
    followups: list[str] = []
    actions: list[str] = []
    status = "Thinking..."

    def add_action(text: str) -> None:
        if text in actions:
            return
        actions.append(text)
        render_activity_panel(placeholders.activity, actions, status)

    def on_answer_chunk(chunk: str) -> None:
        nonlocal answer
        answer += chunk
        placeholders.answer.markdown(f"{answer}▌")

    def on_field_end(path: str, field_name: str, parsed_value: Any) -> None:
        nonlocal confidence, found_answer

        if path == "" and field_name == "confidence" and isinstance(parsed_value, (int, float)):
            confidence = float(parsed_value)
            render_metadata_row(placeholders.metadata, confidence, found_answer)

        if path == "" and field_name == "found_answer" and isinstance(parsed_value, bool):
            found_answer = parsed_value
            render_metadata_row(placeholders.metadata, confidence, found_answer)

        if path == "/query_specs" and field_name in {"from_period", "to_period"} and isinstance(parsed_value, str):
            add_action(f"Period {field_name}: {parsed_value}")

    def on_array_item_end(path: str, field_name: str, item: Any) -> None:
        if item is None:
            return

        if path == "" and field_name == "followup_questions" and isinstance(item, str):
            followups.append(item)

        if path == "/query_specs" and field_name == "fact_table" and isinstance(item, str):
            add_action(f"Table to query: {item}")

        if path == "/query_specs" and field_name == "dimension_tables" and isinstance(item, str):
            add_action(f"Join table: {item}")

    handler = StreamResultHandler(on_answer_chunk, on_field_end, on_array_item_end)
    parser = StreamingJSONParser(handler)

    render_activity_panel(placeholders.activity, actions, status)
    placeholders.answer.markdown("▌")

    async with agent.iter(
        prompt,
        message_history=message_history,
        output_type=RAGResponse,
    ) as agent_run:
        async for node in agent_run:
            if Agent.is_model_request_node(node):
                await process_model_request_node(node, agent_run, parser)

            if Agent.is_call_tools_node(node):
                async with node.stream(agent_run.ctx) as events:
                    async for event in events:
                        if not isinstance(event, FunctionToolCallEvent):
                            continue

                        tool_name = event.part.tool_name
                        add_action(f"Tool call: {tool_name}")

                        if tool_name == "run_sql":
                            sql_query = extract_sql_from_args(event.part.args)
                            for table_name in extract_table_names_from_sql(sql_query):
                                add_action(f"Table to query: {table_name}")

        result = agent_run.result

    status = "Done"

    rag_output = result.output
    if rag_output.answer and not answer:
        answer = rag_output.answer
    if rag_output.confidence is not None:
        confidence = float(rag_output.confidence)
    if rag_output.found_answer is not None:
        found_answer = bool(rag_output.found_answer)
    if not followups:
        followups = list(rag_output.followup_questions or [])

    placeholders.answer.markdown(answer)
    render_metadata_row(placeholders.metadata, confidence, found_answer)
    render_activity_panel(placeholders.activity, actions, status)

    assistant_message = {
        "role": "assistant",
        "content": answer,
        "activity": actions,
        "activity_status": status,
        "confidence": confidence,
        "found_answer": found_answer,
        "followups": followups,
    }
    return assistant_message, result.all_messages()


async def process_model_request_node(node: ModelRequestNode, agent_run, parser: StreamingJSONParser) -> None:
    args_so_far = ""
    async with node.stream(agent_run.ctx) as stream:
        async for response in stream.stream_responses():
            for part in response.parts:
                if part.part_kind != "tool-call":
                    continue
                if part.tool_name != "final_result":
                    continue

                args_new = part.args
                args_new_chunk = args_new[len(args_so_far) :]
                args_so_far = args_new
                parser.parse_incremental(args_new_chunk)


def render_chat_history() -> None:
    for index, message in enumerate(st.session_state.chat_messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            if message["role"] == "assistant":
                activity_placeholder = st.empty()
                metadata_placeholder = st.empty()

                render_activity_panel(
                    activity_placeholder,
                    message.get("activity", []),
                    message.get("activity_status", "Done"),
                )
                render_metadata_row(
                    metadata_placeholder,
                    message.get("confidence"),
                    message.get("found_answer"),
                )


def get_placeholder_for_followup(question: str) -> str:
    lower = question.lower()

    if any(token in lower for token in ["period", "periode", "date", "datum", "month", "maand", "jaar"]):
        return "Bijv. januari 2025 t/m februari 2025"

    if any(token in lower for token in ["station", "locatie", "plaats", "region", "regio"]):
        return "Bijv. alle stations of Utrecht Centraal"

    if any(token in lower for token in ["filter", "meldingsoort", "incident", "type"]):
        return "Bijv. meldingsoort: aanrijding"

    return "Geef extra context"


def build_clarification_prompt(
    base_question: str,
    followups: list[str],
    answers: list[str],
) -> str:
    qa_lines = []
    for question, answer in zip(followups, answers):
        clean_answer = answer.strip() if answer else ""
        if clean_answer:
            qa_lines.append(f"- {question}: {clean_answer}")

    if not qa_lines:
        return base_question

    return (
        f"Original question: {base_question}\n"
        "Additional clarifications from the user:\n"
        + "\n".join(qa_lines)
    )


def render_clarification_form() -> tuple[str | None, str | None]:
    followups = st.session_state.pending_followups
    if not followups:
        return None, None

    st.write("Provide details so I can answer your question")
    answers: list[str] = []

    form_key = f"clarification_form_{st.session_state.followup_token}"
    with st.form(key=form_key):
        for idx, question in enumerate(followups):
            answer = st.text_input(
                label=question,
                placeholder=get_placeholder_for_followup(question),
                key=f"clarification_input_{st.session_state.followup_token}_{idx}",
            )
            answers.append(answer)

        submitted = st.form_submit_button("Submit clarifications", use_container_width=True)

    if not submitted:
        return None, None

    base_question = st.session_state.pending_base_question or ""
    refined_prompt = build_clarification_prompt(base_question, followups, answers)
    answered_pairs = [
        f"{q}: {a.strip()}"
        for q, a in zip(followups, answers)
        if a and a.strip()
    ]
    display_text = "Clarifications provided" if not answered_pairs else "Clarifications: " + " | ".join(answered_pairs)
    return refined_prompt, display_text


def process_user_prompt(agent, user_prompt: str, display_user_text: str | None = None) -> None:
    st.session_state.pending_followups = []
    st.session_state.pending_base_question = ""

    shown_text = display_user_text or user_prompt

    st.session_state.chat_messages.append({"role": "user", "content": shown_text})
    with st.chat_message("user"):
        st.markdown(shown_text)

    with st.chat_message("assistant"):
        answer_placeholder = st.empty()
        activity_placeholder = st.empty()
        metadata_placeholder = st.empty()

        placeholders = LivePlaceholders(
            answer=answer_placeholder,
            activity=activity_placeholder,
            metadata=metadata_placeholder,
        )

        assistant_message, new_history = asyncio.run(
            run_agent_stream(
                agent=agent,
                prompt=user_prompt,
                message_history=st.session_state.agent_history,
                placeholders=placeholders,
            )
        )

    st.session_state.chat_messages.append(assistant_message)
    st.session_state.agent_history = new_history
    st.session_state.pending_followups = assistant_message.get("followups", [])
    st.session_state.pending_base_question = user_prompt
    st.session_state.followup_token += 1
    st.rerun()


def main() -> None:
    st.set_page_config(page_title="SQL Agent Chat", page_icon="🗄️", layout="wide")
    st.title("SQL Agent Chat")

    ensure_session_state()

    bundle = get_agent_bundle()
    agent = bundle["agent"]
    sql_tools = bundle["sql_tools"]

    if not st.session_state.index_loaded:
        with st.spinner("Loading index..."):
            sql_tools.get_db_metadata()
        st.session_state.index_loaded = True

    with st.sidebar:
        st.header("Session")
        if st.button("Clear conversation", use_container_width=True):
            clear_conversation()
            st.rerun()

    render_chat_history()

    clarified_prompt, clarification_display_text = render_clarification_form()
    typed_prompt = st.chat_input("Ask a question about the database")

    if clarified_prompt:
        process_user_prompt(agent, clarified_prompt, clarification_display_text)
    elif typed_prompt:
        process_user_prompt(agent, typed_prompt)


if __name__ == "__main__":
    main()
