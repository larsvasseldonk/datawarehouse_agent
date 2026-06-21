"""
End-to-end evaluation pipeline.

Runs the two-agent pipeline (refinement + SQL) on a set of questions, applies
both LLM judges to each interaction, and reports how many decisions are
good/bad per agent in absolute numbers and as a percentage, with a cost/time
breakdown. Judged results are saved to a timestamped JSON file.

Usage:
    python -m src.agent.evals.run_evals                       # default questions_generated.csv
    python -m src.agent.evals.run_evals --questions my.csv    # custom questions file
    python -m src.agent.evals.run_evals --limit 10            # random subset of 10
"""

import os
import json
import time
import random
import asyncio
import argparse
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

from src.agent.evals.run_questions import (
    run_pipeline_on_all_questions,
    CostAccumulator,
    cost_eur,
    total_cost_eur,
)
from src.agent.evals.refinement_judge import (
    create_refinement_judge,
    format_refinement_prompt,
    JUDGE_MODEL as REFINEMENT_JUDGE_MODEL,
)
from src.agent.evals.sql_judge import (
    create_sql_judge,
    format_sql_prompt,
)

load_dotenv()

EVALS_DIR = os.path.dirname(__file__)


# ---------------------------------------------------------------------------
# Step 2 – apply both LLM judges
# ---------------------------------------------------------------------------

async def judge_all_results(
    agent_results: list[dict],
    judge_cost: CostAccumulator,
) -> list[dict]:
    refinement_judge = create_refinement_judge()
    sql_judge = create_sql_judge()

    judged = []
    total = len(agent_results)

    for i, entry in enumerate(agent_results, 1):
        question = entry.get("input", {}).get("question", f"Question {i}")
        record = {
            "input": entry.get("input"),
            "category": entry.get("category"),
            "type": entry.get("type"),
            "refinement": None,
            "sql": None,
        }

        try:
            ref_eval = await refinement_judge.run(format_refinement_prompt(entry))
            judge_cost.add(ref_eval.usage)
            record["refinement"] = {
                "label": ref_eval.output.label,
                "reasoning": ref_eval.output.reasoning,
            }
            ref_label = ref_eval.output.label
        except Exception as exc:
            record["refinement"] = {"label": "bad", "reasoning": f"Judge error: {exc}"}
            ref_label = "error"

        sql_label = "----"
        if isinstance(entry.get("sql"), dict):
            try:
                sql_eval = await sql_judge.run(format_sql_prompt(entry))
                judge_cost.add(sql_eval.usage)
                record["sql"] = {
                    "label": sql_eval.output.label,
                    "reasoning": sql_eval.output.reasoning,
                }
                sql_label = sql_eval.output.label
            except Exception as exc:
                record["sql"] = {"label": "bad", "reasoning": f"Judge error: {exc}"}
                sql_label = "error"

        print(f"[{i}/{total}] refinement={ref_label:5} sql={sql_label:5} | {question}")
        judged.append(record)

    return judged


# ---------------------------------------------------------------------------
# Step 3 – report
# ---------------------------------------------------------------------------

def _counts(judged: list[dict], key: str) -> tuple[int, int, int]:
    good = sum(1 for r in judged if r[key] and r[key]["label"] == "good")
    bad = sum(1 for r in judged if r[key] and r[key]["label"] == "bad")
    return good, bad, good + bad


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def report(
    judged: list[dict],
    agent_refinement_cost: CostAccumulator,
    agent_sql_cost: CostAccumulator,
    judge_cost: CostAccumulator,
    agent_elapsed: float,
    judge_elapsed: float,
) -> None:
    ref_good, ref_bad, ref_total = _counts(judged, "refinement")
    sql_good, sql_bad, sql_total = _counts(judged, "sql")

    agent_cost = total_cost_eur(agent_refinement_cost) + total_cost_eur(agent_sql_cost)
    judge_total_cost = total_cost_eur(judge_cost)
    total_cost = agent_cost + judge_total_cost
    total_elapsed = agent_elapsed + judge_elapsed

    print("\n" + "=" * 55)
    print("  EVALUATION RESULTS")
    print("=" * 55)
    print(f"  Refinement judge ({ref_total} judged):")
    if ref_total:
        print(f"    Good : {ref_good:>4}  ({ref_good / ref_total * 100:.1f}%)")
        print(f"    Bad  : {ref_bad:>4}  ({ref_bad / ref_total * 100:.1f}%)")
    print(f"  SQL judge ({sql_total} judged):")
    if sql_total:
        print(f"    Good : {sql_good:>4}  ({sql_good / sql_total * 100:.1f}%)")
        print(f"    Bad  : {sql_bad:>4}  ({sql_bad / sql_total * 100:.1f}%)")
    print("=" * 55)
    print("  COST & TIME BREAKDOWN")
    print("=" * 55)
    print(f"  Agents:")
    print(f"    Cost          : €{agent_cost:.4f}")
    print(f"    Time          : {_fmt_time(agent_elapsed)}")
    print(f"  Judges ({judge_cost.model}):")
    print(f"    Tokens in/out : {judge_cost.total_input_tokens:,} / {judge_cost.total_output_tokens:,}")
    print(f"    Cost          : €{judge_total_cost:.4f}")
    print(f"    Time          : {_fmt_time(judge_elapsed)}")
    print(f"  {'-' * 37}")
    print(f"  Total cost      : €{total_cost:.4f}")
    print(f"  Total time      : {_fmt_time(total_elapsed)}")
    print("=" * 55)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the two-agent pipeline on all questions and judge the responses."
    )
    parser.add_argument(
        "--questions",
        default="questions_generated.csv",
        help="Path to a CSV file with a 'question' column (default: questions_generated.csv)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to save the judged results as JSON (default: timestamped file).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run on a random subset of N questions instead of the full list.",
    )
    args = parser.parse_args()

    questions_path = args.questions
    if not os.path.isabs(questions_path):
        questions_path = os.path.join(EVALS_DIR, questions_path)

    print(f"Loading questions from {questions_path}...")
    df = pd.read_csv(questions_path)
    category_col = "category" if "category" in df.columns else "group"

    rows = list(zip(df["question"], df[category_col], df["type"]))
    print(f"  -> {len(rows)} questions loaded.")

    if args.limit is not None:
        k = min(args.limit, len(rows))
        rows = random.sample(rows, k)
        print(f"  -> Sampling {k} random questions (--limit {args.limit}).")

    questions = [r[0] for r in rows]
    categories = [r[1] for r in rows]
    types = [r[2] for r in rows]

    # --- Phase 1: run the two-agent pipeline ---
    print("\n" + "-" * 55)
    print("  PHASE 1: Running refinement + SQL agents")
    print("-" * 55)
    t0 = time.perf_counter()
    agent_results, refinement_cost, sql_cost = await run_pipeline_on_all_questions(
        questions, categories, types
    )
    agent_elapsed = time.perf_counter() - t0

    # --- Phase 2: judge with both judges ---
    print("\n" + "-" * 55)
    print("  PHASE 2: Applying LLM judges")
    print("-" * 55)
    judge_cost = CostAccumulator(model=REFINEMENT_JUDGE_MODEL)
    t0 = time.perf_counter()
    judged = await judge_all_results(agent_results, judge_cost)
    judge_elapsed = time.perf_counter() - t0

    # --- Save judged results ---
    if args.output:
        output_path = args.output
        if not os.path.isabs(output_path):
            output_path = os.path.join(EVALS_DIR, output_path)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(EVALS_DIR, f"evals_run_{timestamp}.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(judged, f, indent=2, ensure_ascii=False)
    print(f"\nJudged results saved to {output_path}")

    # --- Report ---
    report(judged, refinement_cost, sql_cost, judge_cost, agent_elapsed, judge_elapsed)


if __name__ == "__main__":
    asyncio.run(main())