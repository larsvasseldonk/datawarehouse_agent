from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import streamlit as st

try:
    import sqlparse
except Exception:  # pragma: no cover - optional dependency
    sqlparse = None


EVALS_DIR = Path(__file__).resolve().parent
RESULTS_PATH = EVALS_DIR / "results.json"
LABELS_PATH = EVALS_DIR / "human_labels.json"
DB_PATH = Path(__file__).resolve().parents[3] / "db" / "db.duckdb"

FAILURE_CATEGORIES = [
    "hallucination",
    "wrong-scope",
    "incomplete",
    "sql-error",
    "formatting",
    "other",
]


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def normalize_runs(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def refinement_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        if "clarification" in payload and len(payload) == 1:
            return str(payload["clarification"])
        return json.dumps(payload, indent=2, ensure_ascii=False)
    return str(payload)


def sql_text(payload: Any) -> str:
    if isinstance(payload, dict):
        answer = str(payload.get("answer", "")).strip()
        explanation = str(payload.get("explanation", "")).strip()
        answer_found = payload.get("answer_found")
        success = payload.get("success")
        lines = []
        if answer:
            lines.append(answer)
        if explanation:
            lines.append("")
            lines.append("Explanation:")
            lines.append(explanation)
        if answer_found is not None or success is not None:
            lines.append("")
            lines.append(f"answer_found={answer_found}, success={success}")
        if lines:
            return "\n".join(lines)
        return json.dumps(payload, indent=2, ensure_ascii=False)
    return str(payload)


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
    conn = get_conn()
    relation = conn.execute(query)
    rows = relation.fetchmany(200)
    cols = [desc[0] for desc in relation.description]
    return cols, rows


def build_response_items(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for q_idx, row in enumerate(results):
        question = row.get("input", {}).get("question", f"Question {q_idx + 1}")

        for run_idx, ref in enumerate(normalize_runs(row.get("refinement"))):
            response_id = f"q{q_idx}:refinement:{run_idx}"
            items.append(
                {
                    "id": response_id,
                    "question_index": q_idx,
                    "question": question,
                    "agent": "refinement",
                    "run_index": run_idx,
                    "response": refinement_text(ref),
                    "raw": ref,
                    "sql_query": None,
                }
            )

        for run_idx, sql in enumerate(normalize_runs(row.get("sql"))):
            if sql is None:
                continue
            sql_query = sql.get("sql_query") if isinstance(sql, dict) else None
            response_id = f"q{q_idx}:sql:{run_idx}"
            items.append(
                {
                    "id": response_id,
                    "question_index": q_idx,
                    "question": question,
                    "agent": "sql",
                    "run_index": run_idx,
                    "response": sql_text(sql),
                    "raw": sql,
                    "sql_query": sql_query,
                }
            )

    return items


def default_record(item: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    """Build a label record for an item, seeded from any existing saved label."""
    if item["agent"] == "sql":
        existing_sql = existing.get("edited_sql_query")
        original_sql = item.get("sql_query") or ""
        edited_sql = str(existing_sql or format_sql(str(original_sql)))
    else:
        edited_sql = ""

    return {
        "question_index": item["question_index"],
        "question": item["question"],
        "agent": item["agent"],
        "run_index": item["run_index"],
        "label": existing.get("label", "unlabeled"),
        "failure_category": existing.get("failure_category", ""),
        "notes": existing.get("notes", ""),
        "edited_sql_query": edited_sql,
    }


def init_label_store(items: list[dict[str, Any]], labels: dict[str, Any]) -> None:
    """
    Hydrate a single persistent dict (``labels_data``) once per session.

    This dict is keyed by response id and is NOT a widget key, so Streamlit
    never garbage-collects it on rerun/navigation. All reads/writes go through
    it, which makes saving reliable.
    """
    if "labels_data" in st.session_state:
        return

    labels_by_id = labels.get("labels", {})
    store: dict[str, Any] = {}
    for item in items:
        rid = item["id"]
        store[rid] = default_record(item, labels_by_id.get(rid, {}))
    st.session_state["labels_data"] = store


def build_payload(items: list[dict[str, Any]]) -> dict[str, Any]:
    store: dict[str, Any] = st.session_state.get("labels_data", {})
    payload_labels: dict[str, Any] = {}

    for item in items:
        rid = item["id"]
        record = store.get(rid, default_record(item, {}))
        label = record.get("label", "unlabeled")

        payload_labels[rid] = {
            "question_index": item["question_index"],
            "question": item["question"],
            "agent": item["agent"],
            "run_index": item["run_index"],
            "label": label,
            "failure_category": record.get("failure_category", "") if label == "bad" else "",
            "notes": record.get("notes", ""),
            "edited_sql_query": record.get("edited_sql_query", "") if item["agent"] == "sql" else "",
        }

    return {
        "meta": {
            "source_results": str(RESULTS_PATH.name),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_responses": len(items),
        },
        "labels": payload_labels,
    }


def save_labels(items: list[dict[str, Any]]) -> None:
    """Write the current label store to disk."""
    payload = build_payload(items)
    try:
        dump_json(LABELS_PATH, payload)
        st.session_state["_last_saved_at"] = datetime.now(timezone.utc).isoformat()
        st.session_state["_save_error"] = ""
    except Exception as exc:  # pragma: no cover - UI/runtime IO surface
        st.session_state["_save_error"] = str(exc)


def make_on_change(rid: str, field: str, widget_key: str, items: list[dict[str, Any]]):
    """Return a callback that mirrors a widget value into the store and saves."""

    def _callback() -> None:
        st.session_state["labels_data"][rid][field] = st.session_state[widget_key]
        save_labels(items)

    return _callback


def main() -> None:
    st.set_page_config(page_title="Label Evals", layout="wide")
    st.title("Label Agent Evals")

    if not RESULTS_PATH.exists():
        st.error(f"Missing results file: {RESULTS_PATH}")
        st.stop()

    results = load_json(RESULTS_PATH, default=[])
    labels = load_json(LABELS_PATH, default={"labels": {}})
    items = build_response_items(results)

    if not items:
        st.warning("No responses found in results.json")
        st.stop()

    init_label_store(items, labels)
    store = st.session_state["labels_data"]

    question_indices = sorted({item["question_index"] for item in items})

    if "question_cursor" not in st.session_state:
        st.session_state["question_cursor"] = question_indices[0]

    st.sidebar.header("Navigation")

    only_unlabeled_questions = st.sidebar.checkbox("Only questions with unlabeled responses", value=False)

    question_has_unlabeled = {
        q_idx: any(
            store.get(item["id"], {}).get("label", "unlabeled") == "unlabeled"
            for item in items
            if item["question_index"] == q_idx
        )
        for q_idx in question_indices
    }

    visible_question_indices = (
        [q_idx for q_idx in question_indices if question_has_unlabeled[q_idx]]
        if only_unlabeled_questions
        else question_indices
    )

    if not visible_question_indices:
        st.sidebar.info("No unlabeled responses left.")
        visible_question_indices = question_indices

    if st.session_state["question_cursor"] not in visible_question_indices:
        st.session_state["question_cursor"] = visible_question_indices[0]

    def question_label(q_idx: int) -> str:
        question = next(item["question"] for item in items if item["question_index"] == q_idx)
        short = question if len(question) <= 80 else f"{question[:77]}..."
        all_labeled = all(
            store.get(item["id"], {}).get("label", "unlabeled") in {"good", "bad"}
            for item in items
            if item["question_index"] == q_idx
        )
        prefix = "✅ " if all_labeled else ""
        return f"{prefix}Q{q_idx + 1}: {short}"

    selected_q = st.sidebar.selectbox(
        "Question",
        options=visible_question_indices,
        index=visible_question_indices.index(st.session_state["question_cursor"]),
        format_func=question_label,
    )
    st.session_state["question_cursor"] = selected_q

    prev_col, next_col = st.sidebar.columns(2)
    with prev_col:
        if st.button("Previous", use_container_width=True):
            current_pos = visible_question_indices.index(st.session_state["question_cursor"])
            st.session_state["question_cursor"] = visible_question_indices[max(0, current_pos - 1)]
            st.rerun()
    with next_col:
        if st.button("Next", use_container_width=True):
            current_pos = visible_question_indices.index(st.session_state["question_cursor"])
            st.session_state["question_cursor"] = visible_question_indices[min(len(visible_question_indices) - 1, current_pos + 1)]
            st.rerun()

    labeled_count = sum(
        1
        for item in items
        if store.get(item["id"], {}).get("label", "unlabeled") in {"good", "bad"}
    )
    st.sidebar.metric("Labeled responses", f"{labeled_count}/{len(items)}")
    if st.session_state.get("_save_error"):
        st.sidebar.error(f"Save failed: {st.session_state['_save_error']}")
    elif st.session_state.get("_last_saved_at"):
        st.sidebar.caption(f"Last saved: {st.session_state['_last_saved_at']}")

    question_items = [item for item in items if item["question_index"] == st.session_state["question_cursor"]]
    st.subheader(f"Question {st.session_state['question_cursor'] + 1}")
    st.write(question_items[0]["question"])

    for item in question_items:
        rid = item["id"]
        record = store[rid]
        label_key = f"label::{rid}"
        failure_key = f"failure::{rid}"
        note_key = f"note::{rid}"
        sql_edit_key = f"sql_edit::{rid}"

        # Seed widget keys from the persistent store on first render of this widget.
        if label_key not in st.session_state:
            st.session_state[label_key] = record.get("label", "unlabeled")
        if note_key not in st.session_state:
            st.session_state[note_key] = record.get("notes", "")
        if item["agent"] == "sql" and sql_edit_key not in st.session_state:
            st.session_state[sql_edit_key] = record.get("edited_sql_query", "")

        st.markdown("---")
        st.markdown(
            f"**Agent: {item['agent']}**"
            + (f" (run {item['run_index'] + 1})" if item["run_index"] > 0 else "")
        )
        st.text_area(
            "Response",
            value=item["response"],
            height=240,
            disabled=True,
            key=f"response::{item['id']}",
        )

        if item["agent"] == "sql" and item.get("sql_query"):
            st.caption("SQL query")

            original_sql = str(item.get("sql_query") or "")
            st.code(format_sql(original_sql) or original_sql, language="sql")

            st.text_area(
                "SQL query (editable for testing)",
                key=sql_edit_key,
                height=180,
                on_change=make_on_change(rid, "edited_sql_query", sql_edit_key, items),
            )
            if st.button("Run SQL test", key=f"runsql::{item['id']}"):
                try:
                    query_to_run = st.session_state.get(sql_edit_key, "").strip()
                    if not query_to_run:
                        raise ValueError("SQL query is empty")
                    cols, rows = run_sql_test(query_to_run)
                    st.success(f"Query executed successfully. Returned {len(rows)} rows (showing up to 200).")
                    if rows:
                        table_rows = [dict(zip(cols, row)) for row in rows]
                        st.dataframe(table_rows, use_container_width=True)
                    else:
                        st.info("Query returned 0 rows.")
                except Exception as exc:
                    st.error(f"SQL execution failed: {exc}")

        label = st.radio(
            "Label",
            options=["unlabeled", "good", "bad"],
            horizontal=True,
            key=label_key,
            on_change=make_on_change(rid, "label", label_key, items),
        )

        failure_options = [""] + FAILURE_CATEGORIES
        if failure_key not in st.session_state:
            current_failure = record.get("failure_category", "")
            st.session_state[failure_key] = current_failure if current_failure in failure_options else ""
        st.selectbox(
            "Failure category (for bad labels)",
            options=failure_options,
            disabled=(label != "bad"),
            key=failure_key,
            on_change=make_on_change(rid, "failure_category", failure_key, items),
        )

        st.text_input(
            "Notes (optional)",
            key=note_key,
            on_change=make_on_change(rid, "notes", note_key, items),
        )

        with st.expander("Show raw payload"):
            st.json(item["raw"])

    if st.button("Save now", type="primary"):
        save_labels(items)
        payload = build_payload(items)

        good_count = sum(1 for lbl in payload["labels"].values() if lbl["label"] == "good")
        bad_count = sum(1 for lbl in payload["labels"].values() if lbl["label"] == "bad")
        unlabeled_count = sum(1 for lbl in payload["labels"].values() if lbl["label"] == "unlabeled")

        if st.session_state.get("_save_error"):
            st.error(f"Save failed: {st.session_state['_save_error']}")
        else:
            st.success(
                f"Labels saved successfully! (Total: {len(payload['labels'])}, "
                f"Good: {good_count}, Bad: {bad_count}, Unlabeled: {unlabeled_count})"
            )

    st.caption(f"Labels are saved to {LABELS_PATH}")


if __name__ == "__main__":
    main()
