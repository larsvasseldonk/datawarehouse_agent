"""LLM judge for the SQL agent's generated query and answer."""

from typing import Literal, Any, Dict

from pydantic import BaseModel, Field
from pydantic_ai import Agent


JUDGE_MODEL = "openai-chat:gpt-4o-mini"

instructions = """
You are an expert evaluator assessing a *SQL agent* in an NL-to-SQL system for Dutch
Railways station-safety data. Given a refined question, it generates a DuckDB SQL query,
executes it, and explains the answer.

The warehouse contains ONLY incident-log data: a fact table of registered incidents
(factincidentmkns) joined to dimensions for date (dimdatum), station/service point
(dimdienstregelpunt), location type (dimlocatietype), incident/report type
(dimmeldingssoort), time (dimtijd), and train number/series (dimtreinnummer_treinserie).

You are given the refined question, the executed SQL query, its status
(answer_found/success), the tools used, and the agent's final answer.

Label "good" if the SQL is valid against this schema and faithfully answers the question,
the answer's numbers/dates/stations/incident types are consistent with the query and its
results, and the answer is clear and in the same language as the question.

Label "bad" if it hallucinates tables, columns, stations, or values not in the schema;
writes SQL that would not run; states a confident answer when the query errored, returned
no rows, or success/answer_found indicate failure; gives an answer inconsistent with the
SQL; or contains broken formatting/symbols.

Be strict. Reason step by step, then give your final label.
""".strip()


class JudgeEvaluation(BaseModel):
    """Output format for the SQL judge."""

    reasoning: str = Field(
        description="Step-by-step reasoning about the SQL agent's query and answer."
    )
    label: Literal["good", "bad"] = Field(
        description="The final label: 'good' or 'bad'."
    )


def create_sql_judge() -> Agent[None, JudgeEvaluation]:
    """Creates the SQL judge agent."""
    return Agent(
        name="sql_judge",
        model=JUDGE_MODEL,
        instructions=instructions,
        output_type=JudgeEvaluation,
    )


prompt_template = """
Evaluate the SQL agent's query and answer.

Refined Question:
{question}

Tools Used:
{tools}

Executed SQL Query:
{sql_query}

Query Status:
{sql_status}

Agent Answer:
{answer}
"""


def _format_tools(tool_list: list | None) -> str:
    parts = [f"{t.get('name')}({t.get('args')})" for t in (tool_list or [])]
    return "\n".join(parts) if parts else "(no tools used)"


def format_sql_prompt(entry: Dict[str, Any]) -> str:
    """Formats a results.json entry into a prompt for the SQL judge."""
    sql = entry.get("sql") or {}
    # The SQL agent receives the refined question; fall back to the original.
    question = sql.get("refined_question") or entry["input"]["question"]

    return prompt_template.format(
        question=question,
        tools=_format_tools(entry.get("tools_sql")),
        sql_query=sql.get("sql_query") or "(none)",
        sql_status=f"answer_found={sql.get('answer_found')}, success={sql.get('success')}",
        answer=sql.get("answer", ""),
    )
