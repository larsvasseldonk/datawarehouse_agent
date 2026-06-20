"""
Script to run the two-agent pipeline on all questions in a questions CSV.

Pipeline per question:
  1. Refinement agent  – clarifies and validates the question
  2. SQL agent         – generates and executes a DuckDB query

Cost and token usage are tracked per agent and saved to results.json.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from src.agent.refinement_agent import (
    refinement_agent,
    Deps as RefinementDeps,
    QuestionRefinementResponse,
)
from src.agent.sql_agent import (
    sql_agent,
    Deps as SQLDeps,
)


load_dotenv()


# ---------------------------------------------------------------------------
# Cost Tracking
# ---------------------------------------------------------------------------

# Exchange rate: USD to EUR (as of 2026)
USD_TO_EUR = 0.87

@dataclass
class CostAccumulator:
    """Accumulates token usage and calculates costs."""
    model: str
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    def add(self, usage):
        """Add usage from a single request."""
        if usage.input_tokens:
            self.total_input_tokens += usage.input_tokens
        if usage.output_tokens:
            self.total_output_tokens += usage.output_tokens

    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


def cost_eur(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Calculate cost in EUR for a single request.
    Pricing based on OpenAI GPT-4o mini (as of 2026).
    """
    # gpt-4.1-mini is typically gpt-4o mini pricing
    # Input: $0.15 per 1M tokens, Output: $0.60 per 1M tokens
    if "gpt-4" in model:
        input_cost = (input_tokens / 1_000_000) * 0.15
        output_cost = (output_tokens / 1_000_000) * 0.60
    else:
        # Fallback pricing
        input_cost = (input_tokens / 1_000_000) * 0.15
        output_cost = (output_tokens / 1_000_000) * 0.60

    return (input_cost + output_cost) * USD_TO_EUR


def total_cost_eur(cost: CostAccumulator) -> float:
    """Calculate total cost in EUR."""
    return cost_eur(cost.model, cost.total_input_tokens, cost.total_output_tokens)


# ---------------------------------------------------------------------------
# Two-agent pipeline for a single question
# ---------------------------------------------------------------------------

def _collect_tool_calls(result) -> list[dict]:
    """Extract tool calls from a pydantic-ai RunResult."""
    tools = []
    for message in result.new_messages():
        for part in message.parts:
            if part.part_kind == "tool-call" and part.tool_name != "final_result":
                tools.append({"name": part.tool_name, "args": part.args})
    return tools


async def run_pipeline_on_question(
    question: str,
    refinement_deps: RefinementDeps,
    sql_deps: SQLDeps,
    refinement_cost: CostAccumulator,
    sql_cost: CostAccumulator,
) -> dict:
    """
    Run the full two-agent pipeline on a single question.

    Returns a result dict with keys:
        input, refinement, sql (optional), tools_refinement, tools_sql,
        execution_time_s, cost_eur, tokens.
    """
    result = {"input": {"question": question}}

    # --- Step 1: Refinement agent ---
    t_ref = time.perf_counter()
    refinement_result = await refinement_agent.run(
        question,
        deps=refinement_deps,
    )
    ref_elapsed = time.perf_counter() - t_ref

    refinement_cost.add(refinement_result.usage)
    ref_cost = cost_eur(refinement_cost.model, refinement_result.usage.input_tokens or 0, refinement_result.usage.output_tokens or 0)

    result["refinement"] = (
        refinement_result.output.model_dump()
        if isinstance(refinement_result.output, QuestionRefinementResponse)
        else {"clarification": str(refinement_result.output)}
    )
    result["tools_refinement"] = _collect_tool_calls(refinement_result)
    result["refinement_time_s"] = ref_elapsed
    result["refinement_cost_eur"] = ref_cost
    result["refinement_tokens"] = {
        "input": refinement_result.usage.input_tokens or 0,
        "output": refinement_result.usage.output_tokens or 0,
    }

    # If the refinement agent returned a clarification instead of a structured
    # response, skip the SQL step.
    if not isinstance(refinement_result.output, QuestionRefinementResponse):
        result["sql"] = None
        result["tools_sql"] = []
        result["sql_time_s"] = 0.0
        result["sql_cost_eur"] = 0.0
        result["sql_tokens"] = {"input": 0, "output": 0}
        result["execution_time_s"] = ref_elapsed
        result["cost_eur"] = ref_cost
        result["tokens"] = result["refinement_tokens"]
        return result

    refined_question = refinement_result.output.refined_question

    # --- Step 2: SQL agent ---
    t_sql = time.perf_counter()
    sql_result = await sql_agent.run(
        refined_question,
        deps=sql_deps,
    )
    sql_elapsed = time.perf_counter() - t_sql

    sql_cost.add(sql_result.usage)
    s_cost = cost_eur(sql_cost.model, sql_result.usage.input_tokens or 0, sql_result.usage.output_tokens or 0)

    result["sql"] = sql_result.output.model_dump()
    result["tools_sql"] = _collect_tool_calls(sql_result)
    result["sql_time_s"] = sql_elapsed
    result["sql_cost_eur"] = s_cost
    result["sql_tokens"] = {
        "input": sql_result.usage.input_tokens or 0,
        "output": sql_result.usage.output_tokens or 0,
    }

    result["execution_time_s"] = ref_elapsed + sql_elapsed
    result["cost_eur"] = ref_cost + s_cost
    result["tokens"] = {
        "input": result["refinement_tokens"]["input"] + result["sql_tokens"]["input"],
        "output": result["refinement_tokens"]["output"] + result["sql_tokens"]["output"],
    }

    return result


# ---------------------------------------------------------------------------
# Run all questions
# ---------------------------------------------------------------------------

async def run_pipeline_on_all_questions(
    questions: list[str],
    categories: list[str],
    types: list[str],
) -> tuple[list[dict], CostAccumulator, CostAccumulator]:
    refinement_cost = CostAccumulator(model="gpt-4o-mini")
    sql_cost = CostAccumulator(model="gpt-4o-mini")

    refinement_deps = RefinementDeps()
    sql_deps = SQLDeps()

    results = []
    total = len(questions)

    for i, (question, category, q_type) in enumerate(zip(questions, categories, types), 1):
        print(f"\n[{i}/{total}] {category} | {q_type}")
        print(f"  Question: {question}")

        try:
            result = await run_pipeline_on_question(
                question, refinement_deps, sql_deps, refinement_cost, sql_cost
            )
            result["category"] = category
            result["type"] = q_type

            ref_ready = (
                result["refinement"].get("ready_for_sql")
                if isinstance(result["refinement"], dict)
                else False
            )
            print(
                f"  refinement → ready_for_sql={ref_ready}  "
                f"cost=€{result['refinement_cost_eur']:.4f}  "
                f"time={result['refinement_time_s']:.1f}s"
            )
            if result["sql"] is not None:
                print(
                    f"  sql        → answer_found={result['sql'].get('answer_found')}  "
                    f"cost=€{result['sql_cost_eur']:.4f}  "
                    f"time={result['sql_time_s']:.1f}s"
                )

        except Exception as exc:
            print(f"  ERROR: {exc}")
            result = {
                "input": {"question": question},
                "refinement": None,
                "sql": None,
                "tools_refinement": [],
                "tools_sql": [],
                "category": category,
                "type": q_type,
                "execution_time_s": 0.0,
                "cost_eur": 0.0,
                "tokens": {"input": 0, "output": 0},
                "error": str(exc),
            }

        results.append(result)

    return results, refinement_cost, sql_cost


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    evals_dir = Path(__file__).parent
    questions_path = evals_dir / "questions_generated.csv"

    if not questions_path.exists():
        raise FileNotFoundError(f"Questions file not found: {questions_path}")

    print(f"Loading questions from {questions_path}")
    df = pd.read_csv(questions_path)

    # Support both 'category' and 'group' column names
    category_col = "category" if "category" in df.columns else "group"

    questions = df["question"].tolist()
    categories = df[category_col].tolist()
    types = df["type"].tolist()
    print(f"Loaded {len(questions)} questions\n")

    print("=" * 70)
    print("Running two-agent pipeline on all questions...")
    print("=" * 70)

    results, refinement_cost, sql_cost = await run_pipeline_on_all_questions(
        questions, categories, types
    )

    total_cost = total_cost_eur(refinement_cost) + total_cost_eur(sql_cost)

    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    print(f"Total questions : {len(results)}")
    print(f"Successful      : {len([r for r in results if 'error' not in r])}")
    print(f"Failed          : {len([r for r in results if 'error' in r])}")
    print(f"Refinement agent  cost : €{total_cost_eur(refinement_cost):.4f}  "
          f"tokens: {refinement_cost.total_tokens():,}")
    print(f"SQL agent         cost : €{total_cost_eur(sql_cost):.4f}  "
          f"tokens: {sql_cost.total_tokens():,}")
    print(f"Total cost             : €{total_cost:.4f}")

    output_path = evals_dir / "results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
