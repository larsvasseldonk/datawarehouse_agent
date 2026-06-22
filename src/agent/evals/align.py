"""Compare the LLM judges against human labels (no LLM calls).

Reads ``judged.json`` (from evals.py) and ``human_labels.json`` (from the
Streamlit labeler), matches them by ``"{agent}::{question}"``, and prints
accuracy / precision / recall with ``bad`` as the positive class.

Usage:
    python -m src.agent.evals.align
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

EVALS_DIR = Path(__file__).resolve().parent
JUDGED_PATH = EVALS_DIR / "judged.json"
LABELS_PATH = EVALS_DIR / "human_labels.json"


def _rows(judged: list[dict], human: dict, agent: str) -> pd.DataFrame:
    rows = []
    for r in judged:
        judge = r.get(f"{agent}_judge")
        question = r.get("input", {}).get("question", "")
        h = human.get(f"{agent}::{question}")
        if not judge or not h or h.get("label") not in ("good", "bad"):
            continue
        rows.append({
            "question": question,
            "human": h["label"],
            "llm": judge["label"],
            "notes": h.get("notes", ""),
        })
    return pd.DataFrame(rows)


def report(name: str, df: pd.DataFrame) -> None:
    print(f"\n=== {name} judge vs human ({len(df)} samples) ===")
    if df.empty:
        print("No matched labels.")
        return
    tp = int(((df.human == "bad") & (df.llm == "bad")).sum())
    tn = int(((df.human == "good") & (df.llm == "good")).sum())
    fp = int(((df.human == "good") & (df.llm == "bad")).sum())
    fn = int(((df.human == "bad") & (df.llm == "good")).sum())
    acc = (tp + tn) / len(df)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    print(f"Accuracy {acc:.0%} | Precision {prec:.0%} | Recall {rec:.0%} (positive='bad')")
    for _, row in df[df.human != df.llm].iterrows():
        print(f"  DISAGREE: {row.question}")
        print(f"    human={row.human} ({row.notes}) | llm={row.llm}")


def main() -> None:
    if not JUDGED_PATH.exists():
        raise FileNotFoundError(f"No {JUDGED_PATH.name} found. Run evals.py first.")
    judged = json.loads(JUDGED_PATH.read_text())
    human = (json.loads(LABELS_PATH.read_text()) if LABELS_PATH.exists() else {}).get("labels", {})
    print(f"Aligning {len(judged)} judged records against {len(human)} human labels...")
    report("Refinement", _rows(judged, human, "refinement"))
    report("SQL", _rows(judged, human, "sql"))


if __name__ == "__main__":
    main()
