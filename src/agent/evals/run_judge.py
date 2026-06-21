"""
Run both LLM judges over results.json (produced by run_questions.py).

- The refinement judge scores every interaction's routing decision.
- The SQL judge scores only interactions where the SQL agent actually ran.

Labels and reasoning are saved to judge_results.json.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

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


async def main() -> None:
    evals_dir = Path(__file__).parent
    results_path = evals_dir / "results.json"

    if not results_path.exists():
        raise FileNotFoundError(
            f"Results file not found: {results_path}. Run run_questions.py first."
        )

    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    refinement_judge = create_refinement_judge()
    sql_judge = create_sql_judge()

    print("=" * 70)
    print(f"Judging {len(results)} interactions from {results_path.name}...")
    print("=" * 70)

    judged = []
    ref_good = ref_bad = sql_good = sql_bad = 0

    for i, entry in enumerate(results, 1):
        question = entry.get("input", {}).get("question", f"Question {i}")

        ref_eval = await refinement_judge.run(format_refinement_prompt(entry))
        ref_label = ref_eval.output.label
        ref_good += ref_label == "good"
        ref_bad += ref_label == "bad"

        record = {
            "input": entry.get("input"),
            "category": entry.get("category"),
            "type": entry.get("type"),
            "refinement": {"label": ref_label, "reasoning": ref_eval.output.reasoning},
            "sql": None,
        }

        if isinstance(entry.get("sql"), dict):
            sql_eval = await sql_judge.run(format_sql_prompt(entry))
            sql_label = sql_eval.output.label
            sql_good += sql_label == "good"
            sql_bad += sql_label == "bad"
            record["sql"] = {"label": sql_label, "reasoning": sql_eval.output.reasoning}
            print(f"[{i}/{len(results)}] refinement={ref_label:4} sql={sql_label:4} | {question}")
        else:
            print(f"[{i}/{len(results)}] refinement={ref_label:4} sql=----  | {question}")

        judged.append(record)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = evals_dir / f"judge_results_{timestamp}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(judged, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("JUDGE SUMMARY")
    print("=" * 70)
    print(f"Refinement : good={ref_good}  bad={ref_bad}")
    print(f"SQL        : good={sql_good}  bad={sql_bad}")
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
