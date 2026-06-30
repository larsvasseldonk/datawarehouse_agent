"""LLM judges that label the refinement and SQL agent outputs as good/bad."""

import json
from typing import Any, Dict, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from src.agent.llm import LLMProvider


JUDGE_MODEL = "gpt-4.1-mini"


class JudgeEvaluation(BaseModel):
    """Output format shared by both judges."""

    reasoning: str = Field(description="Step-by-step reasoning about the agent's output.")
    label: Literal["good", "bad"] = Field(description="The final label: 'good' or 'bad'.")


REFINEMENT_INSTRUCTIONS = """
You are an expert evaluator assessing a *refinement agent* in an NL-to-SQL system for
Dutch Railways station-safety data. Its only job is to ROUTE the user's question:

- If the question is answerable with the available incident data, refine it into a clear,
  structured question and hand off to the SQL agent (ready_for_sql = true).
- If the question is ambiguous or missing information (e.g. no time range, no station),
  ask a clarifying/follow-up question instead of handing off.
- If the question cannot be answered with the available data (e.g. weather, social media,
  news) or is off-topic (cooking, sports, generic ML), explicitly refuse and explain the
  data limitation instead of handing off.

The warehouse contains ONLY incident-log data: a fact table of registered incidents
(factincidentmkns) joined to dimensions for date, station/service point, location type,
incident/report type, time, and train number/series. There is NO social-media, news,
weather, or passenger-level data.

You are given the user's question, a reference category/type describing the EXPECTED
behavior, the tools used, and the refinement agent's outcome.

Label "good" if the routing decision matches the expected behavior: answerable questions
are handed off with a faithful refined question, ambiguous ones get a relevant clarifying
question, and unanswerable/off-topic ones are explicitly refused with the right reason.
It should also respond in the same language as the user (e.g. Dutch for Dutch questions).

Label "bad" if it hands off an unanswerable or off-topic question, refuses an answerable
one, fails to ask for clarification on a clearly ambiguous question, distorts the user's
intent in the refined question, or gives a confusing/broken response.

Reason step by step, then give your final label.
""".strip()


SQL_INSTRUCTIONS = """
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


def create_refinement_judge(provider: str = "openai", model: str = JUDGE_MODEL) -> Agent[None, JudgeEvaluation]:
    """Creates the refinement judge agent on the chosen provider ('openai' or 'chatns')."""
    return Agent(
        name="refinement_judge",
        model=LLMProvider(model).get_model(provider),
        instructions=REFINEMENT_INSTRUCTIONS,
        output_type=JudgeEvaluation,
    )


def create_sql_judge(provider: str = "openai", model: str = JUDGE_MODEL) -> Agent[None, JudgeEvaluation]:
    """Creates the SQL judge agent on the chosen provider ('openai' or 'chatns')."""
    return Agent(
        name="sql_judge",
        model=LLMProvider(model).get_model(provider),
        instructions=SQL_INSTRUCTIONS,
        output_type=JudgeEvaluation,
    )


def _format_tools(tool_list: list | None) -> str:
    parts = [f"{t.get('name')}({t.get('args')})" for t in (tool_list or [])]
    return "\n".join(parts) if parts else "(no tools used)"


REFINEMENT_PROMPT = """
Evaluate the refinement agent's routing decision.

User Question:
{question}

Expected behavior (reference): category={category}, type={type}

Tools Used:
{tools}

Outcome:
{outcome}

Refinement Output:
{details}
"""


def format_refinement_prompt(entry: Dict[str, Any]) -> str:
    """Formats a results.json entry into a prompt for the refinement judge."""
    refinement = entry.get("refinement") or {}
    if "ready_for_sql" in refinement:
        outcome = "HANDOFF to SQL agent (question deemed answerable)"
        details = json.dumps(refinement, ensure_ascii=False, indent=2)
    else:
        outcome = "CLARIFICATION / REFUSAL (did not hand off)"
        details = refinement.get("clarification") or json.dumps(
            refinement, ensure_ascii=False, indent=2
        )

    return REFINEMENT_PROMPT.format(
        question=entry["input"]["question"],
        category=entry.get("category"),
        type=entry.get("type"),
        tools=_format_tools(entry.get("tools_refinement")),
        outcome=outcome,
        details=details,
    )


SQL_PROMPT = """
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


def format_sql_prompt(entry: Dict[str, Any]) -> str:
    """Formats a results.json entry into a prompt for the SQL judge."""
    sql = entry.get("sql") or {}
    # The SQL agent receives the refined question; fall back to the original.
    question = sql.get("refined_question") or entry["input"]["question"]

    return SQL_PROMPT.format(
        question=question,
        tools=_format_tools(entry.get("tools_sql")),
        sql_query=sql.get("sql_query") or "(none)",
        sql_status=f"answer_found={sql.get('answer_found')}, success={sql.get('success')}",
        answer=sql.get("answer", ""),
    )
