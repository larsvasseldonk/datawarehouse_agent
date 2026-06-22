"""LLM-as-judge agents and their prompt formatters."""

from src.agent.evals.judges.refinement_judge import (
    JUDGE_MODEL as REFINEMENT_JUDGE_MODEL,
    create_refinement_judge,
    format_refinement_prompt,
)
from src.agent.evals.judges.sql_judge import (
    JUDGE_MODEL as SQL_JUDGE_MODEL,
    create_sql_judge,
    format_sql_prompt,
)

__all__ = [
    "REFINEMENT_JUDGE_MODEL",
    "SQL_JUDGE_MODEL",
    "create_refinement_judge",
    "format_refinement_prompt",
    "create_sql_judge",
    "format_sql_prompt",
]
