"""End-to-end eval orchestrator: generate -> judge -> report.

Runs the two-agent pipeline on a dataset, applies the relevant LLM judge(s),
prints a good/bad + cost/time report, and saves all artifacts in one run
directory. Optionally fails (exit code 1) when the good-rate drops below a
threshold, so it can be used as a CI quality gate.

Usage:
    python -m src.agent.evals.run_evals --dataset questions_sql.csv --target sql
    python -m src.agent.evals.run_evals --dataset questions_manual.csv --min-good-rate 0.7
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from dotenv import load_dotenv

from src.agent.evals.core.artifacts import new_run_dir, write_json
from src.agent.evals.core.cost import CostAccumulator
from src.agent.evals.core.metrics import count_good_bad, good_rate
from src.agent.evals.judge_runner import judge_results
from src.agent.evals.pipeline import load_dataset_rows, run_pipeline_on_all_questions

load_dotenv()


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def report(judged: list[dict], agent_cost: float, judge_cost: float,
           agent_elapsed: float, judge_elapsed: float) -> tuple[float, float]:
    ref_good, ref_bad, ref_total = count_good_bad(judged, "refinement")
    sql_good, sql_bad, sql_total = count_good_bad(judged, "sql")

    print("\n" + "=" * 55)
    print("  EVALUATION RESULTS")
    print("=" * 55)
    print(f"  Refinement judge ({ref_total} judged):")
    if ref_total:
        print(f"    Good : {ref_good:>4}  ({good_rate(ref_good, ref_total) * 100:.1f}%)")
        print(f"    Bad  : {ref_bad:>4}  ({good_rate(ref_bad, ref_total) * 100:.1f}%)")
    print(f"  SQL judge ({sql_total} judged):")
    if sql_total:
        print(f"    Good : {sql_good:>4}  ({good_rate(sql_good, sql_total) * 100:.1f}%)")
        print(f"    Bad  : {sql_bad:>4}  ({good_rate(sql_bad, sql_total) * 100:.1f}%)")
    print("=" * 55)
    print("  COST & TIME")
    print("=" * 55)
    print(f"  Agents cost : EUR{agent_cost:.4f}   time: {_fmt_time(agent_elapsed)}")
    print(f"  Judges cost : EUR{judge_cost:.4f}   time: {_fmt_time(judge_elapsed)}")
    print(f"  Total cost  : EUR{agent_cost + judge_cost:.4f}")
    print("=" * 55)

    return good_rate(ref_good, ref_total), good_rate(sql_good, sql_total)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run the two-agent pipeline and judge it.")
    parser.add_argument("--dataset", default="questions_sql.csv", help="Dataset CSV (in datasets/).")
    parser.add_argument("--target", choices=["refinement", "sql", "both"], default="both",
                        help="Which judge(s) to apply (default: both).")
    parser.add_argument("--limit", type=int, default=None, help="Run a random subset of N questions.")
    parser.add_argument("--min-good-rate", type=float, default=None,
                        help="Fail (exit 1) if the judged good-rate is below this (CI gate).")
    args = parser.parse_args()

    rows = load_dataset_rows(args.dataset, args.limit)
    print("-" * 55)
    print(f"  PHASE 1: agents on {len(rows)} questions from {args.dataset}")
    print("-" * 55)
    t0 = time.perf_counter()
    results, refinement_cost, sql_cost = await run_pipeline_on_all_questions(rows)
    agent_elapsed = time.perf_counter() - t0
    agent_cost = refinement_cost.total_cost_eur() + sql_cost.total_cost_eur()

    print("\n" + "-" * 55)
    print("  PHASE 2: LLM judges")
    print("-" * 55)
    judge_cost = CostAccumulator(model="gpt-4o-mini")
    t0 = time.perf_counter()
    judged = await judge_results(results, judge_cost, target=args.target)
    judge_elapsed = time.perf_counter() - t0

    run_dir = new_run_dir(args.dataset.replace(".csv", ""))
    write_json(run_dir / "results.json", results)
    write_json(run_dir / "judged.json", judged)
    write_json(run_dir / "meta.json", {
        "dataset": args.dataset,
        "target": args.target,
        "n_questions": len(rows),
        "agent_cost_eur": agent_cost,
        "judge_cost_eur": judge_cost.total_cost_eur(),
    })

    ref_rate, sql_rate = report(
        judged, agent_cost, judge_cost.total_cost_eur(), agent_elapsed, judge_elapsed
    )
    print(f"\nArtifacts saved to {run_dir}")

    if args.min_good_rate is not None:
        rates = []
        _, _, ref_total = count_good_bad(judged, "refinement")
        _, _, sql_total = count_good_bad(judged, "sql")
        if ref_total:
            rates.append(ref_rate)
        if sql_total:
            rates.append(sql_rate)
        worst = min(rates) if rates else 1.0
        if worst < args.min_good_rate:
            print(f"\nFAIL: good-rate {worst:.3f} < threshold {args.min_good_rate:.3f}")
            sys.exit(1)
        print(f"\nPASS: good-rate {worst:.3f} >= threshold {args.min_good_rate:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
