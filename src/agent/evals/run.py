"""Run the two agents on a dataset, judge the outputs, and print a per-agent score.

Writes the agent outputs and judge labels to data/results.json. Agent and judge token
usage/cost is captured by Logfire (when a token is configured).

Usage:
    python -m src.agent.evals.run --dataset questions_sql.csv --target sql
    python -m src.agent.evals.run --dataset questions_refinement.csv --target refinement --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from pathlib import Path

import logfire
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

DATA_DIR = Path(__file__).resolve().parent / "data"
RESULTS_PATH = DATA_DIR / "results.json"


def _tool_calls(result) -> list[dict]:
    return [
        {"name": p.tool_name, "args": p.args}
        for m in result.new_messages()
        for p in m.parts
        if p.part_kind == "tool-call" and p.tool_name != "final_result"
    ]


def load_rows(dataset: str, limit: int | None) -> list[tuple[str, str, str]]:
    """Load (question, category, type) rows from a dataset CSV in data/."""
    df = pd.read_csv(DATA_DIR / Path(dataset).name)
    rows = list(zip(df["question"], df["category"], df["type"]))
    if limit:
        rows = random.sample(rows, min(limit, len(rows)))
    return rows


async def run_agents(rows: list[tuple[str, str, str]], target: str) -> list[dict]:
    """Run the agents on every question.

    target='refinement' runs the refinement agent only, target='sql' runs the SQL agent
    directly on the question, and target='both' runs refinement then SQL on handoff.
    """
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
        }
        try:
            if target == "sql":
                sql = await sql_agent.run(question, deps=sql_deps)
                record["sql"] = sql.output.model_dump()
                record["tools_sql"] = _tool_calls(sql)
            else:
                ref = await refinement_agent.run(question, deps=ref_deps)
                refined = isinstance(ref.output, QuestionRefinementResponse)
                record["refinement"] = (
                    ref.output.model_dump() if refined else {"clarification": str(ref.output)}
                )
                record["tools_refinement"] = _tool_calls(ref)

                if target == "both" and refined:
                    sql = await sql_agent.run(ref.output.refined_question, deps=sql_deps)
                    record["sql"] = sql.output.model_dump()
                    record["tools_sql"] = _tool_calls(sql)
        except Exception as exc:  # keep going; record the failure
            print(f"    ERROR: {exc}")
            record["error"] = str(exc)
        results.append(record)
    return results


async def judge(results: list[dict], target: str, provider: str) -> None:
    """Add a judge label to each record in place."""
    ref_judge = create_refinement_judge(provider) if target in ("refinement", "both") else None
    sql_judge = create_sql_judge(provider) if target in ("sql", "both") else None

    for i, r in enumerate(results, 1):
        r["refinement_judge"] = None
        r["sql_judge"] = None
        if ref_judge and r.get("refinement"):
            e = await ref_judge.run(format_refinement_prompt(r))
            r["refinement_judge"] = {"label": e.output.label, "reasoning": e.output.reasoning}
        if sql_judge and isinstance(r.get("sql"), dict):
            e = await sql_judge.run(format_sql_prompt(r))
            r["sql_judge"] = {"label": e.output.label, "reasoning": e.output.reasoning}
        ref_label = (r["refinement_judge"] or {}).get("label", "--")
        sql_label = (r["sql_judge"] or {}).get("label", "--")
        print(f"[{i}/{len(results)}] refinement={ref_label:5} sql={sql_label:5}")


def report(results: list[dict]) -> None:
    """Print the per-agent performance score (share of 'good' labels)."""
    print("\n=== Evaluation results ===")
    for name, key in (("Refinement", "refinement_judge"), ("SQL", "sql_judge")):
        labels = [r[key]["label"] for r in results if r.get(key)]
        if labels:
            good = labels.count("good")
            print(f"{name:11} {good}/{len(labels)} good ({good / len(labels) * 100:.0f}%)")


def merge_results(new_records: list[dict]) -> list[dict]:
    """Merge new records into the existing results.json, keyed by question.

    This keeps results from earlier runs (e.g. the other judge's dataset) instead of
    overwriting them; records for the same question are replaced.
    """
    by_question: dict[str, dict] = {}
    if RESULTS_PATH.exists():
        for r in json.loads(RESULTS_PATH.read_text()):
            by_question[r["input"]["question"]] = r
    for r in new_records:
        by_question[r["input"]["question"]] = r
    return list(by_question.values())


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run and judge the two-agent pipeline.")
    parser.add_argument("--dataset", default="questions_sql.csv", help="Dataset CSV in data/.")
    parser.add_argument("--target", choices=["refinement", "sql", "both"], default="both")
    parser.add_argument(
        "--provider",
        choices=["openai", "chatns"],
        default="openai",
        help="LLM provider for the judges.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Run a random subset of N questions.")
    args = parser.parse_args()

    logfire.configure(send_to_logfire="if-token-present", console=False)
    logfire.instrument_pydantic_ai()

    rows = load_rows(args.dataset, args.limit)
    print(f"Loaded {len(rows)} questions from {args.dataset}\n")

    results = await run_agents(rows, args.target)
    print("\n--- Judging ---")
    await judge(results, args.target, args.provider)

    merged = merge_results(results)
    RESULTS_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False, default=str))
    report(results)
    print(f"\nSaved {RESULTS_PATH.name} to {DATA_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
