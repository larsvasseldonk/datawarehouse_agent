"""LLM judge for the refinement agent's routing decision."""

import json
from typing import Literal, Any, Dict

from pydantic import BaseModel, Field
from pydantic_ai import Agent


JUDGE_MODEL = "openai-chat:gpt-4o-mini"

instructions = """
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


class JudgeEvaluation(BaseModel):
    """Output format for the refinement judge."""

    reasoning: str = Field(
        description="Step-by-step reasoning about the refinement agent's routing decision."
    )
    label: Literal["good", "bad"] = Field(
        description="The final label: 'good' or 'bad'."
    )


def create_refinement_judge() -> Agent[None, JudgeEvaluation]:
    """Creates the refinement judge agent."""
    return Agent(
        name="refinement_judge",
        model=JUDGE_MODEL,
        instructions=instructions,
        output_type=JudgeEvaluation,
    )


prompt_template = """
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


def _format_tools(tool_list: list | None) -> str:
    parts = [f"{t.get('name')}({t.get('args')})" for t in (tool_list or [])]
    return "\n".join(parts) if parts else "(no tools used)"


def format_refinement_prompt(entry: Dict[str, Any]) -> str:
    """Formats a results.json entry into a prompt for the refinement judge."""
    question = entry["input"]["question"]
    refinement = entry.get("refinement") or {}
    tools = _format_tools(entry.get("tools_refinement"))

    if "ready_for_sql" in refinement:
        outcome = "HANDOFF to SQL agent (question deemed answerable)"
        details = json.dumps(refinement, ensure_ascii=False, indent=2)
    else:
        outcome = "CLARIFICATION / REFUSAL (did not hand off)"
        details = refinement.get("clarification") or json.dumps(
            refinement, ensure_ascii=False, indent=2
        )

    return prompt_template.format(
        question=question,
        category=entry.get("category"),
        type=entry.get("type"),
        tools=tools,
        outcome=outcome,
        details=details,
    )
