# uv run pytest test_agent.py -s

import pytest

from src.agent.refinement_agent import (
    refinement_agent, QuestionRefinementResponse, Deps
)
from src.agent.tests.judge import assert_criteria


@pytest.mark.asyncio
async def test_agent_ambiguous_question():
    user_prompt = "Hoe veel incidenten?"
    refinement_result = await refinement_agent.run(user_prompt, deps=Deps())

    output = refinement_result.output
    assert isinstance(output, str)


@pytest.mark.asyncio
async def test_judge_asking_follow_up_questions():
    user_prompt = "Hoe veel incidenten?"
    refinement_result = await refinement_agent.run(user_prompt, deps=Deps())

    await assert_criteria(refinement_result, [
        "the agent should ask at least 1 clarifying question to gather more information about the user's request",
        "the agent should ask for the specific time period to query over",
        "the agent should ask for the specific station or location to query over",
        "the agent should not attempt to generate a SQL query",
    ])


@pytest.mark.asyncio
async def test_judge_unrelated_question():
    user_prompt = "Wat is het weer?"
    refinement_result = await refinement_agent.run(user_prompt, deps=Deps())

    await assert_criteria(refinement_result, [
        "the agent should tell the user that it cannot answer the question",
        "the agent should tell the user to ask a question about the database instead",
    ])


@pytest.mark.asyncio
async def test_agent_refined_question():
    user_prompt = "Wat is het totaal aantal incidenten geregistreerd in augustus 2025 op station Utrecht Centraal?"
    refinement_result = await refinement_agent.run(
        user_prompt,
        deps=Deps()
    )

    output = refinement_result.output
    assert isinstance(output, QuestionRefinementResponse)
    assert output.refined_question is not None
    assert output.ready_for_sql == True
    assert output.date_range["from_date"] == "2025-08-01"
    assert output.date_range["to_date"] == "2025-08-31"
    assert "Utrecht Centraal" in output.stations


@pytest.mark.asyncio
async def test_judge_refined_question():
    user_prompt = "Hoe veel agressie incidenten waren er in mei 2025 op station Amsterdam Centraal?"
    refinement_result = await refinement_agent.run(user_prompt, deps=Deps())

    await assert_criteria(refinement_result, [
        "the agent should extract the station name from the user's question and include it in the refined question",
        "the agent should extract the date range from the user's question and include it in the refined question",
        "the agent should extract the incident type from the user's question and include it in the refined question",
        "the agent should indicate that the refined question is ready for SQL generation",
        "the agent should add in the additional_specs that meldingssort should be agressie",
    ])


# @pytest.mark.asyncio
# async def test_future_date():
#     import datetime
#     future_year = datetime.datetime.now().year + 1
#     user_prompt = f"Wat is het totaal aantal incidenten geregistreerd in augustus {future_year}?"
#     refinement_result = await refinement_agent.run(
#         user_prompt,
#         deps=Deps()
#     )

#     output = refinement_result.output
#     assert isinstance(output, str)
