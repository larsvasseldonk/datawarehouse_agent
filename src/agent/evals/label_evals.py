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


def build_response_items(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One item per (question, agent). The id is stable across runs."""
    items: list[dict[str, Any]] = []
    for q_idx, row in enumerate(results):
        question = row.get("input", {}).get("question", f"Question {q_idx + 1}")

        ref = row.get("refinement")
        if ref is not None:
            items.append({
                "id": f"refinement::{question}",
                "question_index": q_idx,
                "question": question,
                "agent": "refinement",
                "response": refinement_text(ref),
                "raw": ref,
                "sql_query": None,
            })

        sql = row.get("sql")
        if sql is not None:
            items.append({
                "id": f"sql::{question}",
                "question_index": q_idx,
                "question": question,
                "agent": "sql",
                "response": sql_text(sql),
                "raw": sql,
                "sql_query": sql.get("sql_query") if isinstance(sql, dict) else None,
            })
    return items


def default_record(item: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    """Build a label record for an item, seeded from any existing saved label."""
    if item["agent"] == "sql":
        edited_sql = str(existing.get("edited_sql_query") or format_sql(str(item.get("sql_query") or "")))
    else:
        edited_sql = ""
    return {
        "question_index": item["question_index"],
        "question": item["question"],
        "agent": item["agent"],
        "label": existing.get("label", "unlabeled"),
        "failure_category": existing.get("failure_category", ""),
        "notes": existing.get("notes", ""),
        "edited_sql_query": edited_sql,
    }


def init_label_store(items: list[dict[str, Any]], labels: dict[str, Any]) -> None:
    """Hydrate a single persistent dict (keyed by item id) once per session."""
    if "labels_data" in st.session_state:
        return
    labels_by_id = labels.get("labels", {})
    st.session_state["labels_data"] = {
        item["id"]: default_record(item, labels_by_id.get(item["id"], {})) for item in items
    }


def build_payload(items: list[dict[str, Any]]) -> dict[str, Any]:
    store: dict[str, Any] = st.session_state.get("labels_data", {})
    payload_labels: dict[str, Any] = {}
    for item in items:
        record = store.get(item["id"], default_record(item, {}))
        label = record.get("label", "unlabeled")
        payload_labels[item["id"]] = {
            "question_index": item["question_index"],
            "question": item["question"],
            "agent": item["agent"],
            "label": label,
            "failure_category": record.get("failure_category", "") if label == "bad" else "",
            "notes": record.get("notes", ""),
            "edited_sql_query": record.get("edited_sql_query", "") if item["agent"] == "sql" else "",
        }
    return {
        "meta": {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_responses": len(items),
        },
        "labels": payload_labels,
    }


def save_labels(items: list[dict[str, Any]]) -> None:
    try:
        dump_json(LABELS_PATH, build_payload(items))
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
        st.error(f"Missing results file: {RESULTS_PATH}. Run evals.py first.")
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
    only_unlabeled = st.sidebar.checkbox("Only questions with unlabeled responses", value=False)

    def has_unlabeled(q_idx: int) -> bool:
        return any(
            store.get(item["id"], {}).get("label", "unlabeled") == "unlabeled"
            for item in items
            if item["question_index"] == q_idx
        )

    visible = [q for q in question_indices if has_unlabeled(q)] if only_unlabeled else question_indices
    if not visible:
        st.sidebar.info("No unlabeled responses left.")
        visible = question_indices
    if st.session_state["question_cursor"] not in visible:
        st.session_state["question_cursor"] = visible[0]

    def question_label(q_idx: int) -> str:
        question = next(it["question"] for it in items if it["question_index"] == q_idx)
        short = question if len(question) <= 80 else f"{question[:77]}..."
        all_labeled = all(
            store.get(it["id"], {}).get("label", "unlabeled") in {"good", "bad"}
            for it in items
            if it["question_index"] == q_idx
        )
        return f"{'✅ ' if all_labeled else ''}Q{q_idx + 1}: {short}"

    selected_q = st.sidebar.selectbox(
        "Question",
        options=visible,
        index=visible.index(st.session_state["question_cursor"]),
        format_func=question_label,
    )
    st.session_state["question_cursor"] = selected_q

    prev_col, next_col = st.sidebar.columns(2)
    with prev_col:
        if st.button("Previous", use_container_width=True):
            pos = visible.index(st.session_state["question_cursor"])
            st.session_state["question_cursor"] = visible[max(0, pos - 1)]
            st.rerun()
    with next_col:
        if st.button("Next", use_container_width=True):
            pos = visible.index(st.session_state["question_cursor"])
            st.session_state["question_cursor"] = visible[min(len(visible) - 1, pos + 1)]
            st.rerun()

    labeled_count = sum(
        1 for item in items if store.get(item["id"], {}).get("label", "unlabeled") in {"good", "bad"}
    )
    st.sidebar.metric("Labeled responses", f"{labeled_count}/{len(items)}")
    if st.session_state.get("_save_error"):
        st.sidebar.error(f"Save failed: {st.session_state['_save_error']}")
    elif st.session_state.get("_last_saved_at"):
        st.sidebar.caption(f"Last saved: {st.session_state['_last_saved_at']}")

    cursor = st.session_state["question_cursor"]
    question_items = [item for item in items if item["question_index"] == cursor]
    st.subheader(f"Question {cursor + 1}")
    st.write(question_items[0]["question"])

    for item in question_items:
        rid = item["id"]
        record = store[rid]
        label_key = f"label::{rid}"
        failure_key = f"failure::{rid}"
        note_key = f"note::{rid}"
        sql_edit_key = f"sql_edit::{rid}"

        # Seed widget keys from the persistent store on first render.
        st.session_state.setdefault(label_key, record.get("label", "unlabeled"))
        st.session_state.setdefault(note_key, record.get("notes", ""))
        if item["agent"] == "sql":
            st.session_state.setdefault(sql_edit_key, record.get("edited_sql_query", ""))

        st.markdown("---")
        st.markdown(f"**Agent: {item['agent']}**")
        st.text_area("Response", value=item["response"], height=240, disabled=True, key=f"response::{rid}")

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
            if st.button("Run SQL test", key=f"runsql::{rid}"):
                try:
                    query_to_run = st.session_state.get(sql_edit_key, "").strip()
                    if not query_to_run:
                        raise ValueError("SQL query is empty")
                    cols, rows = run_sql_test(query_to_run)
                    st.success(f"Query executed. Returned {len(rows)} rows (showing up to 200).")
                    if rows:
                        st.dataframe([dict(zip(cols, row)) for row in rows], use_container_width=True)
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
            current = record.get("failure_category", "")
            st.session_state[failure_key] = current if current in failure_options else ""
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
        good = sum(1 for lbl in payload["labels"].values() if lbl["label"] == "good")
        bad = sum(1 for lbl in payload["labels"].values() if lbl["label"] == "bad")
        unlabeled = sum(1 for lbl in payload["labels"].values() if lbl["label"] == "unlabeled")
        if st.session_state.get("_save_error"):
            st.error(f"Save failed: {st.session_state['_save_error']}")
        else:
            st.success(
                f"Labels saved! (Total: {len(payload['labels'])}, "
                f"Good: {good}, Bad: {bad}, Unlabeled: {unlabeled})"
            )

    st.caption(f"Labels are saved to {LABELS_PATH}")


if __name__ == "__main__":
    main()
