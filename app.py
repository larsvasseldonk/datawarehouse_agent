from dataclasses import dataclass
from typing import Any

import streamlit as st
from pydantic_ai.messages import ModelMessage

from src.agent.models import RAGResponse, RefinementResponse
from src.agent.refinement_agent import refinement_agent
from src.agent.sql_agent import run_sql_pipeline
from src.agent.tools import SQLTools


@dataclass
class PipelineResult:
    content: str
    activity: list[str]
    activity_status: str
    confidence: float | None
    query_success: bool | None
    row_count: int | None
    followups: list[str]


@st.cache_resource(show_spinner=False)
def get_sql_tools() -> SQLTools:
    return SQLTools()


def ensure_session_state() -> None:
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "refinement_history" not in st.session_state:
        st.session_state.refinement_history = []
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
    st.session_state.refinement_history = []
    st.session_state.pending_followups = []
    st.session_state.pending_base_question = ""
    st.session_state.followup_token += 1


def render_metadata_row(
    metadata_placeholder: Any,
    confidence: float | None,
    query_success: bool | None,
    row_count: int | None,
) -> None:
    if confidence is None and query_success is None and row_count is None:
        metadata_placeholder.empty()
        return

    confidence_pct = "N/A"
    if confidence is not None:
        confidence_pct = f"{max(0.0, min(1.0, confidence)) * 100:.0f}%"

    query_text = "N/A" if query_success is None else ("Yes" if query_success else "No")
    row_count_text = "N/A" if row_count is None else str(row_count)

    with metadata_placeholder.container():
        col1, col2, col3 = st.columns(3)
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
                "<div style='font-size:0.72rem;opacity:0.72;'>QUERY EXECUTED</div>"
                f"<div style='font-size:1.05rem;font-weight:700;'>{query_text}</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        col3.markdown(
            (
                "<div style='padding:0.35rem 0.6rem;border:1px solid rgba(128,128,128,0.35);"
                "border-radius:10px;'>"
                "<div style='font-size:0.72rem;opacity:0.72;'>ROW COUNT</div>"
                f"<div style='font-size:1.05rem;font-weight:700;'>{row_count_text}</div>"
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


def run_two_stage_pipeline(user_prompt: str) -> tuple[PipelineResult, list[ModelMessage], bool]:
    actions: list[str] = ["Refinement agent: analyzing question"]

    refinement_result = refinement_agent.run_sync(
        user_prompt,
        message_history=st.session_state.refinement_history,
    )
    refinement_output: RefinementResponse = refinement_result.output
    refinement_history = refinement_result.all_messages()

    date_range = refinement_output.date_range
    if date_range.from_date or date_range.to_date:
        actions.append(
            "Date range identified: "
            f"{date_range.from_date or 'missing'} to {date_range.to_date or 'missing'}"
        )

    if not refinement_output.ready_for_sql:
        clarification = (
            refinement_output.clarification_question
            or "Please provide a concrete from and to date so I can run SQL."
        )
        actions.append("Refinement requires one clarification before SQL")
        return (
            PipelineResult(
                content=(
                    "I need one clarification before I execute SQL:\n\n"
                    f"{clarification}"
                ),
                activity=actions,
                activity_status="Waiting for clarification",
                confidence=None,
                query_success=None,
                row_count=None,
                followups=[clarification],
            ),
            refinement_history,
            False,
        )

    actions.append("Refinement complete: handing off to SQL agent")
    sql_output: RAGResponse = run_sql_pipeline(
        specs=refinement_output.query_specs,
        refined_question=refinement_output.refined_question,
    )

    actions.append("SQL agent completed query execution")
    actions.append(f"Fact table: {sql_output.query_specs.fact_table}")
    if sql_output.query_specs.dimension_tables:
        for table_name in sql_output.query_specs.dimension_tables:
            actions.append(f"Joined dimension: {table_name}")

    return (
        PipelineResult(
            content=sql_output.answer,
            activity=actions,
            activity_status="Done",
            confidence=float(sql_output.confidence),
            query_success=bool(sql_output.query_executed_successfully),
            row_count=int(sql_output.row_count),
            followups=list(sql_output.followup_questions or []),
        ),
        refinement_history,
        True,
    )


def render_chat_history() -> None:
    for message in st.session_state.chat_messages:
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
                    message.get("query_success"),
                    message.get("row_count"),
                )

                suggestions = message.get("followups") or []
                if suggestions:
                    st.caption("Suggested follow-up questions")
                    for question in suggestions:
                        st.write(f"- {question}")


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


def process_user_prompt(user_prompt: str, display_user_text: str | None = None) -> None:
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

        render_activity_panel(activity_placeholder, [], "Thinking...")

        try:
            pipeline_result, new_history, sql_executed = run_two_stage_pipeline(user_prompt)
            answer_placeholder.markdown(pipeline_result.content)
            render_activity_panel(
                activity_placeholder,
                pipeline_result.activity,
                pipeline_result.activity_status,
            )
            render_metadata_row(
                metadata_placeholder,
                pipeline_result.confidence,
                pipeline_result.query_success,
                pipeline_result.row_count,
            )
        except Exception as exc:
            answer_placeholder.error(f"Pipeline failed: {exc}")
            pipeline_result = PipelineResult(
                content=(
                    "I could not process your request because an internal error occurred. "
                    "Please check your API/database configuration and try again."
                ),
                activity=["Pipeline error during refinement or SQL stage"],
                activity_status="Error",
                confidence=None,
                query_success=None,
                row_count=None,
                followups=[],
            )
            new_history = st.session_state.refinement_history
            sql_executed = False

            render_activity_panel(
                activity_placeholder,
                pipeline_result.activity,
                pipeline_result.activity_status,
            )
            render_metadata_row(metadata_placeholder, None, None, None)

    assistant_message = {
        "role": "assistant",
        "content": pipeline_result.content,
        "activity": pipeline_result.activity,
        "activity_status": pipeline_result.activity_status,
        "confidence": pipeline_result.confidence,
        "query_success": pipeline_result.query_success,
        "row_count": pipeline_result.row_count,
        "followups": pipeline_result.followups,
    }
    st.session_state.chat_messages.append(assistant_message)
    st.session_state.refinement_history = new_history

    if sql_executed:
        st.session_state.pending_followups = []
        st.session_state.pending_base_question = ""
    else:
        st.session_state.pending_followups = assistant_message.get("followups", [])
        st.session_state.pending_base_question = user_prompt

    st.session_state.followup_token += 1
    st.rerun()


def main() -> None:
    st.set_page_config(page_title="SQL Agent Chat", layout="wide")
    st.title("SQL Agent Chat")

    ensure_session_state()

    sql_tools = get_sql_tools()
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
        process_user_prompt(clarified_prompt, clarification_display_text)
    elif typed_prompt:
        process_user_prompt(typed_prompt)


if __name__ == "__main__":
    main()
