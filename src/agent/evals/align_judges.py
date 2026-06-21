"""
Align the LLM judges with manual labels saved in human_labels.json.

For each interaction in results.json the refinement judge (and, when the SQL
agent ran, the SQL judge) produces a 'good'/'bad' label. Those are compared
against the human labels in human_labels.json, which are keyed by
``q{index}:refinement:0`` and ``q{index}:sql:0``.

Metrics (accuracy / precision / recall with 'bad' as the positive class),
confusion matrices, and disagreements are reported SEPARATELY per judge.
"""

import os
import json
import asyncio
import argparse
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

from src.agent.evals.refinement_judge import (
    create_refinement_judge,
    format_refinement_prompt,
)
from src.agent.evals.sql_judge import (
    create_sql_judge,
    format_sql_prompt,
)


load_dotenv()

EVALS_DIR = os.path.dirname(__file__)


async def judge_label(judge, prompt: str) -> dict:
    """Run a judge on a prompt, returning its label and reasoning."""
    try:
        result = await judge.run(prompt)
        return {"label": result.output.label, "reasoning": result.output.reasoning}
    except Exception as e:  # fall back to 'bad' so failures are visible
        return {"label": "bad", "reasoning": f"Evaluation failed with error: {e}"}


def report(name: str, df: pd.DataFrame) -> None:
    """Print metrics, confusion matrix, and disagreements for one judge."""
    print("\n" + "=" * 60)
    print(f"--- {name} judge vs. human labels ---")
    print("=" * 60)

    if df.empty:
        print("No labeled samples found.")
        return

    y_true_bad = df["human_label"] == "bad"
    y_pred_bad = df["llm_label"] == "bad"

    tp = int((y_true_bad & y_pred_bad).sum())
    fp = int((~y_true_bad & y_pred_bad).sum())
    fn = int((y_true_bad & ~y_pred_bad).sum())
    tn = int((~y_true_bad & ~y_pred_bad).sum())

    accuracy = (tp + tn) / len(df)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    print(f"Total samples: {len(df)}")
    print(f"Accuracy:                {accuracy:.3f} ({accuracy * 100:.1f}%)")
    print(f"Precision (class='bad'): {precision:.3f} ({precision * 100:.1f}%)")
    print(f"Recall    (class='bad'): {recall:.3f} ({recall * 100:.1f}%)")

    print("\nConfusion Matrix:")
    print(f"                 Predicted 'good'   Predicted 'bad'")
    print(f"Actual 'good'    {tn:<19}{fp}")
    print(f"Actual 'bad'     {fn:<19}{tp}")

    df_disagreement = df[df["human_label"] != df["llm_label"]]
    if not df_disagreement.empty:
        print("\n--- Disagreements ---")
        for _, row in df_disagreement.iterrows():
            print(f"Q: {row['question']}")
            print(f"  Human: {row['human_label']} (Notes: {row['human_notes']})")
            print(f"  LLM:   {row['llm_label']} (Reasoning: {row['llm_reasoning'][:150]}...)")
            print("-" * 30)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Align LLM judges with manual labels")
    parser.add_argument("--results", default="results.json", help="Path to results file")
    parser.add_argument("--labels", default="human_labels.json", help="Path to manual labels file")
    args = parser.parse_args()

    results_path = args.results if os.path.isabs(args.results) else os.path.join(EVALS_DIR, args.results)
    labels_path = args.labels if os.path.isabs(args.labels) else os.path.join(EVALS_DIR, args.labels)

    print(f"Loading results from {results_path}...")
    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    print(f"Loading manual labels from {labels_path}...")
    with open(labels_path, "r", encoding="utf-8") as f:
        labels = json.load(f).get("labels", {})

    refinement_judge = create_refinement_judge()
    sql_judge = create_sql_judge()

    print(f"Aligning judges over {len(results)} interactions...\n")

    refinement_rows = []
    sql_rows = []

    for i, entry in enumerate(results):
        question = entry.get("input", {}).get("question", f"Question {i}")

        # --- Refinement judge ---
        human = labels.get(f"q{i}:refinement:0")
        if human is not None:
            llm = await judge_label(refinement_judge, format_refinement_prompt(entry))
            refinement_rows.append({
                "question": question,
                "human_label": human.get("label"),
                "human_notes": human.get("notes", ""),
                "llm_label": llm["label"],
                "llm_reasoning": llm["reasoning"],
            })

        # --- SQL judge (only when the SQL agent ran) ---
        human = labels.get(f"q{i}:sql:0")
        if human is not None and isinstance(entry.get("sql"), dict):
            llm = await judge_label(sql_judge, format_sql_prompt(entry))
            sql_rows.append({
                "question": question,
                "human_label": human.get("label"),
                "human_notes": human.get("notes", ""),
                "llm_label": llm["label"],
                "llm_reasoning": llm["reasoning"],
            })

        print(f"[{i + 1}/{len(results)}] judged | {question}")

    refinement_df = pd.DataFrame(refinement_rows)
    sql_df = pd.DataFrame(sql_rows)

    report("Refinement", refinement_df)
    report("SQL", sql_df)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    refinement_out = os.path.join(EVALS_DIR, f"alignment_refinement_{timestamp}.csv")
    sql_out = os.path.join(EVALS_DIR, f"alignment_sql_{timestamp}.csv")
    refinement_df.to_csv(refinement_out, index=False)
    sql_df.to_csv(sql_out, index=False)
    print(f"\nRefinement alignment saved to {refinement_out}")
    print(f"SQL alignment saved to {sql_out}")


if __name__ == "__main__":
    asyncio.run(main())