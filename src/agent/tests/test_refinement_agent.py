import pytest

from src.agent.refinement_agent import (
    refinement_agent, QuestionRefinementResponse, Deps
)


@pytest.mark.asyncio
async def test_ambiguous_question():
    user_prompt = "Hoe veel incidenten?"
    refinement_result = await refinement_agent.run(
        user_prompt,
        message_history=None,
        deps=Deps()
    )

    output = refinement_result.output
    assert isinstance(output, str)


@pytest.mark.asyncio
async def test_refined_question():
    user_prompt = "Wat is het totaal aantal incidenten geregistreerd in augustus 2025 op station Utrecht Centraal?"
    refinement_result = await refinement_agent.run(
        user_prompt,
        message_history=None,
        deps=Deps()
    )

    output = refinement_result.output
    assert isinstance(output, QuestionRefinementResponse)
    assert output.refined_question is not None
    assert output.ready_for_sql == True
    assert output.date_range["from_date"] == "2025-08-01"
    assert output.date_range["to_date"] == "2025-08-31"
    assert "Utrecht Centraal" in output.stations


# @pytest.mark.asyncio
# async def test_future_date():
#     import datetime
#     future_year = datetime.datetime.now().year + 1
#     user_prompt = f"Wat is het totaal aantal incidenten geregistreerd in augustus {future_year}?"
#     refinement_result = await refinement_agent.run(
#         user_prompt,
#         message_history=None,
#         deps=Deps()
#     )

#     output = refinement_result.output
#     assert isinstance(output, str)
