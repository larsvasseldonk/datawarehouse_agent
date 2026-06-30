"""Streamlit app to review judge labels and give feedback on them.

Reads data/results.json (written by run.py), shows each agent output alongside the
judge's label + reasoning, and lets you agree/disagree with the judge plus a note.
Feedback is written back into results.json and logged to Logfire.

Usage:
    uv run streamlit run src/agent/evals/app.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import logfire
import streamlit as st

try:
    import sqlparse
except Exception:  # pragma: no cover - optional dependency
    sqlparse = None


DATA_DIR = Path(__file__).resolve().parent / "data"
RESULTS_PATH = DATA_DIR / "results.json"
DB_PATH = Path(__file__).resolve().parents[3] / "db" / "db.duckdb"

logfire.configure(send_to_logfire="if-token-present", console=False)


def load_results() -> list[dict[str, Any]]:
    return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))


def save_results(results: list[dict[str, Any]]) -> None:
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )


def refinement_text(payload: Any) -> str:
    if isinstance(payload, dict):
        if "clarification" in payload and len(payload) == 1:
            return str(payload["clarification"])
        return json.dumps(payload, indent=2, ensure_ascii=False)
    return str(payload)


def sql_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return str(payload)
    lines = []
    if str(payload.get("answer", "")).strip():
        lines.append(str(payload["answer"]).strip())
    if str(payload.get("explanation", "")).strip():
        lines += ["", "Explanation:", str(payload["explanation"]).strip()]
    lines += ["", f"answer_found={payload.get('answer_found')}, success={payload.get('success')}"]
    return "\n".join(lines).strip() or json.dumps(payload, indent=2, ensure_ascii=False)


def format_sql(query: str) -> str:
    if not query:
        return ""
    if sqlparse is None:
        return query.strip()
    return sqlparse.format(query, reindent=True, keyword_case="upper").strip()


@st.cache_resource
def get_conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


def run_sql_test(query: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    relation = get_conn().execute(query)
    rows = relation.fetchmany(200)
    cols = [desc[0] for desc in relation.description]
    return cols, rows


def build_items(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One item per (question, agent) that has a judge label."""
    items: list[dict[str, Any]] = []
    for idx, row in enumerate(results):
        question = row.get("input", {}).get("question", f"Question {idx + 1}")
        for agent, output_key, judge_key, text_fn in (
            ("refinement", "refinement", "refinement_judge", refinement_text),
            ("sql", "sql", "sql_judge", sql_text),
        ):
            judge = row.get(judge_key)
            if not judge:
                continue
            output = row.get(output_key)
            items.append({
                "record_index": idx,
                "agent": agent,
                "question": question,
                "response": text_fn(output),
                "raw": output,
                "sql_query": output.get("sql_query") if isinstance(output, dict) else None,
                "judge_label": judge.get("label"),
                "judge_reasoning": judge.get("reasoning", ""),
            })
    return items


def save_feedback(results: list[dict[str, Any]], item: dict[str, Any], agree: bool, note: str) -> None:
    record = results[item["record_index"]]
    record[f"{item['agent']}_feedback"] = {"agree": agree, "note": note}
    save_results(results)
    logfire.info(
        "judge_feedback",
        agent=item["agent"],
        question=item["question"],
        judge_label=item["judge_label"],
        agree=agree,
        note=note or None,
    )


def main() -> None:
    st.set_page_config(page_title="Review Judge Evals", layout="wide")
    st.title("Review Judge Evals")

    if not RESULTS_PATH.exists():
        st.error(f"Missing results file: {RESULTS_PATH}. Run the eval first (python -m src.agent.evals.run).")
        st.stop()

    results = load_results()
    items = build_items(results)
    if not items:
        st.warning("No judged responses found in results.json.")
        st.stop()

    # Toggle between the refinement and SQL judge (each has its own questions).
    available = [a for a in ("refinement", "sql") if any(it["agent"] == a for it in items)]
    st.sidebar.header("Judge")
    agent = st.sidebar.radio("Show judge", options=available, format_func=str.capitalize)
    items = [it for it in items if it["agent"] == agent]

    # Score for the selected judge.
    good = sum(1 for it in items if it["judge_label"] == "good")
    st.sidebar.metric(agent.capitalize(), f"{good}/{len(items)} good")

    questions = list(dict.fromkeys(it["question"] for it in items))

    def question_label(i: int) -> str:
        icons = "".join(
            "✅" if it["judge_label"] == "good" else "❌"
            for it in items
            if it["question"] == questions[i]
        )
        return f"{icons} Q{i + 1}: {questions[i][:70]}"

    selected = st.sidebar.selectbox(
        "Question",
        options=range(len(questions)),
        format_func=question_label,
    )
    question = questions[selected]
    st.subheader(question)

    for item in [it for it in items if it["question"] == question]:
        record = results[item["record_index"]]
        feedback = record.get(f"{item['agent']}_feedback") or {}
        key = f"{item['record_index']}::{item['agent']}"

        st.markdown("---")
        st.markdown(f"**Agent: {item['agent']}**")
        st.text_area("Response", value=item["response"], height=200, disabled=True, key=f"resp::{key}")

        label = item["judge_label"]
        st.markdown(f"**Judge label:** `{label}`")
        st.caption(item["judge_reasoning"])

        if item["agent"] == "sql" and item.get("sql_query"):
            original_sql = str(item["sql_query"])
            st.code(format_sql(original_sql) or original_sql, language="sql")
            edited = st.text_area("SQL query (editable for testing)", value=original_sql, height=160, key=f"sql::{key}")
            if st.button("Run SQL test", key=f"run::{key}"):
                try:
                    if not edited.strip():
                        raise ValueError("SQL query is empty")
                    cols, rows = run_sql_test(edited)
                    st.success(f"Query executed. Returned {len(rows)} rows (showing up to 200).")
                    if rows:
                        st.dataframe([dict(zip(cols, row)) for row in rows], use_container_width=True)
                    else:
                        st.info("Query returned 0 rows.")
                except Exception as exc:
                    st.error(f"SQL execution failed: {exc}")

        options = ["Agree", "Disagree"]
        current = feedback.get("agree")
        index = 0 if current is True else 1 if current is False else None
        choice = st.radio(
            "Do you agree with the judge?",
            options=options,
            index=index,
            horizontal=True,
            key=f"agree::{key}",
        )
        note = st.text_input("Note (optional)", value=feedback.get("note", ""), key=f"note::{key}")
        if st.button("Save feedback", type="primary", key=f"save::{key}"):
            if choice is None:
                st.warning("Select Agree or Disagree first.")
            else:
                save_feedback(results, item, choice == "Agree", note)
                st.success("Feedback saved.")

        with st.expander("Show raw output"):
            st.json(item["raw"])


if __name__ == "__main__":
    main()
