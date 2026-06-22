"""Run the two agents on a dataset, judge the outputs, and print a report.

Writes two files next to this module:
    results.json   agent outputs
    judged.json    agent outputs + LLM-judge labels

Usage:
    python -m src.agent.evals.evals --dataset questions_sql.csv --target sql
    python -m src.agent.evals.evals --dataset questions_manual.csv --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from src.agent.refinement_agent import (
    Deps as RefinementDeps,
    QuestionRefinementResponse,
    refinement_agent,
)
from src.agent.sql_agent import Deps as SQLDeps, sql_agent
from src.agent.evals.judges import (
    create_refinement_judge,
    create_sql_judge,
    format_refinement_prompt,
    format_sql_prompt,
)

load_dotenv()

EVALS_DIR = Path(__file__).resolve().parent
DATASETS_DIR = EVALS_DIR / "datasets"
RESULTS_PATH = EVALS_DIR / "results.json"
JUDGED_PATH = EVALS_DIR / "judged.json"

# Per-1M-token prices (USD) and EUR conversion, matching the app.
PRICES_USD = {"gpt-4o-mini": (0.15, 0.60), "gpt-4o": (2.50, 10.00)}
USD_TO_EUR = 0.87


def cost_eur(input_tokens: int, output_tokens: int, model: str = "gpt-4o-mini") -> float:
    inp, out = PRICES_USD.get(model, PRICES_USD["gpt-4o-mini"])
    return ((input_tokens / 1e6) * inp + (output_tokens / 1e6) * out) * USD_TO_EUR


def _tool_calls(result) -> list[dict]:
    return [
        {"name": p.tool_name, "args": p.args}
        for m in result.new_messages()
        for p in m.parts
        if p.part_kind == "tool-call" and p.tool_name != "final_result"
    ]


def load_rows(dataset: str, limit: int | None) -> list[tuple[str, str, str]]:
    """Load (question, category, type) rows from a dataset CSV in datasets/."""
    path = DATASETS_DIR / Path(dataset).name
    df = pd.read_csv(path)
    category_col = "category" if "category" in df.columns else "group"
    rows = list(zip(df["question"], df[category_col], df["type"]))
    if limit:
        rows = random.sample(rows, min(limit, len(rows)))
    return rows


async def run_agents(rows: list[tuple[str, str, str]]) -> list[dict]:
    """Run the refinement (+ SQL) agents on every question."""
    ref_deps, sql_deps = RefinementDeps(), SQLDeps()
    results = []
    for i, (question, category, q_type) in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {category} | {q_type} | {question}")
        record = {
            "input": {"question": question},
            "category": category,
            "type": q_type,
            "refinement": None,
            "sql": None,
            "tools_refinement": [],
            "tools_sql": [],
            "input_tokens": 0,
            "output_tokens": 0,
        }
        try:
            ref = await refinement_agent.run(question, deps=ref_deps)
            refined = isinstance(ref.output, QuestionRefinementResponse)
            record["refinement"] = (
                ref.output.model_dump() if refined else {"clarification": str(ref.output)}
            )
            record["tools_refinement"] = _tool_calls(ref)
            record["input_tokens"] += ref.usage.input_tokens or 0
            record["output_tokens"] += ref.usage.output_tokens or 0

            if refined:
                sql = await sql_agent.run(ref.output.refined_question, deps=sql_deps)
                record["sql"] = sql.output.model_dump()
                record["tools_sql"] = _tool_calls(sql)
                record["input_tokens"] += sql.usage.input_tokens or 0
                record["output_tokens"] += sql.usage.output_tokens or 0
        except Exception as exc:  # keep going; record the failure
            print(f"    ERROR: {exc}")
            record["error"] = str(exc)
        results.append(record)
    return results


async def judge(results: list[dict], target: str) -> tuple[int, int]:
    """Add a judge label to each record in place; return (input, output) judge tokens."""
    ref_judge = create_refinement_judge() if target in ("refinement", "both") else None
    sql_judge = create_sql_judge() if target in ("sql", "both") else None

    j_in = j_out = 0
    for i, r in enumerate(results, 1):
        r["refinement_judge"] = None
        r["sql_judge"] = None
        if ref_judge and r.get("refinement"):
            e = await ref_judge.run(format_refinement_prompt(r))
            r["refinement_judge"] = {"label": e.output.label, "reasoning": e.output.reasoning}
            j_in += e.usage.input_tokens or 0
            j_out += e.usage.output_tokens or 0
        if sql_judge and isinstance(r.get("sql"), dict):
            e = await sql_judge.run(format_sql_prompt(r))
            r["sql_judge"] = {"label": e.output.label, "reasoning": e.output.reasoning}
            j_in += e.usage.input_tokens or 0
            j_out += e.usage.output_tokens or 0
        ref_label = (r["refinement_judge"] or {}).get("label", "--")
        sql_label = (r["sql_judge"] or {}).get("label", "--")
        print(f"[{i}/{len(results)}] refinement={ref_label:5} sql={sql_label:5}")
    return j_in, j_out


def _good_rate(results: list[dict], key: str) -> tuple[int, int]:
    labels = [r[key]["label"] for r in results if r.get(key)]
    return labels.count("good"), len(labels)


def report(results: list[dict], agent_cost: float, judge_cost: float) -> None:
    print("\n=== Evaluation results ===")
    for name, key in (("Refinement", "refinement_judge"), ("SQL", "sql_judge")):
        good, total = _good_rate(results, key)
        if total:
            print(f"{name:11} {good}/{total} good ({good / total * 100:.0f}%)")
    print(
        f"Cost: agents EUR{agent_cost:.4f} + judges EUR{judge_cost:.4f} "
        f"= EUR{agent_cost + judge_cost:.4f}"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run and judge the two-agent pipeline.")
    parser.add_argument("--dataset", default="questions_sql.csv", help="Dataset CSV in datasets/.")
    parser.add_argument("--target", choices=["refinement", "sql", "both"], default="both")
    parser.add_argument("--limit", type=int, default=None, help="Run a random subset of N questions.")
    args = parser.parse_args()

    rows = load_rows(args.dataset, args.limit)
    print(f"Loaded {len(rows)} questions from {args.dataset}\n")

    results = await run_agents(rows)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))

    print("\n--- Judging ---")
    j_in, j_out = await judge(results, args.target)
    JUDGED_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))

    agent_cost = cost_eur(
        sum(r["input_tokens"] for r in results),
        sum(r["output_tokens"] for r in results),
    )
    report(results, agent_cost, cost_eur(j_in, j_out))
    print(f"\nSaved {RESULTS_PATH.name} and {JUDGED_PATH.name} to {EVALS_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
