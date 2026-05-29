import pytest

from time import time 

from src.agent.tools import SQLTools
from src.agent.llm import LLMProvider
from src.agent.agent import create_agent, SQLAgentConfig

from src.agent.tests.utils import collect_tools, run_agent_test


@pytest.fixture(scope="module")
def agent():
    t0 = time()

    tools = SQLTools()
    agent_config = SQLAgentConfig()
    llm = LLMProvider()

    agent = create_agent(agent_config, tools, llm)

    t1 = time()
    print(f'Loading agent took {t1 - t0}')

    return agent


@pytest.mark.asyncio
async def test_agent_runs(agent):
    user_prompt = "Hoe veel incidenten zijn er geregistreerd in Augustus 2025?"
    result = await run_agent_test(agent, user_prompt)

    sql_result = result.output
    assert sql_result.sql_query is not None
    assert sql_result.result_text is not None
    assert sql_result.row_count is not None
    assert sql_result.confidence is not None
    assert "8471" in sql_result.result_text


@pytest.mark.asyncio
async def test_agent_tool_order(agent):
    user_prompt = "Wat is de meest voorkomende meldingsoort?"
    result = await run_agent_test(agent, user_prompt)

    messages = result.new_messages()
    tool_calls = collect_tools(messages)
    assert tool_calls[0].name == "get_db_metadata"
    assert tool_calls[1].name == "get_example_queries"
    assert "run_sql" in [t.name for t in tool_calls]


@pytest.mark.asyncio
async def test_agent_no_answer(agent):
    user_prompt = "Wat is het weer vandaag?"
    result = await run_agent_test(agent, user_prompt)

    messages = result.new_messages()
    tool_calls = collect_tools(messages)
    assert "run_sql" not in [t.name for t in tool_calls]
    assert result.output.sql_query is None
