import pytest 

from src.agent.tools import SQLTools
from src.agent.llm import LLMProvider
from src.agent.agent import create_agent, SQLAgentConfig

from src.agent.tests.utils import collect_tools, run_agent_test

from src.agent.tests.utils import run_agent_test
from src.agent.tests.judge import assert_criteria


@pytest.fixture(scope="module")
def agent():
    tools = SQLTools()
    agent_config = SQLAgentConfig()
    llm = LLMProvider()

    return create_agent(agent_config, tools, llm)


@pytest.mark.asyncio
async def test_agent_generates_correct_sql(agent):
    user_prompt = "Op welk station zijn de meeste A Agressie tegen medewerker incidenten in 2025 geregistreerd?"
    result = await run_agent_test(agent, user_prompt)

    await assert_criteria(result, [
        "the SQL query uses the dimdatum, dimmeldingssoort and dimdienstregelpunt tables",
        "the SQL query filters for incidents in 2025 using the dimdatum table",
        "the SQL query filters for 'A Agressie tegen medewerker' incidents using 'hoofdsoort' and 'abc_categorie' columns in the dimmeldingssoort table",
        # "the SQL query uses the 'dimdienstregelpuntkey_station' column to group incidents by station",
        "the agent called get_db_metadata tool before running any SQL query",
        "the agent returns the station name with the highest counts as a final answer",
    ])

@pytest.mark.asyncio
async def test_agent_uses_correct_columns(agent):
    user_prompt = "Op welke weekdag vinden de meeste overlastincidenten plaats in mei 2025?"
    result = await run_agent_test(agent, user_prompt)

    await assert_criteria(result, [
        "the SQL query only uses incidents reported in May 2025 by filtering on the dimdatum table",
        "the SQL query filters for 'Overlast' incidents using the 'hoofdsoort' column",
        "the SQL query counts the number of incidents by weekday",
        "the agent returns the weekday with the highest number of incidents.",
        "the agent does not filter on station or location type since the user did not ask for that",
    ])