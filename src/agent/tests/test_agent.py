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
    user_prompt = "Hoe veel incidenten zijn er geregistreerd in augustus 2025?"
    result = await run_agent_test(agent, user_prompt)
    print(result)

    rag_response = result.output
    assert rag_response.answer is not None
    assert "8471" in rag_response.answer or "8.471" in rag_response.answer or "8,471" in rag_response.answer
    assert rag_response.found_answer == True
    assert rag_response.query_specs is not None
    assert rag_response.confidence is not None


@pytest.mark.asyncio
async def test_agent_tool_order(agent):
    user_prompt = "Wat is de meest voorkomende meldingsoort in 2025?"
    result = await run_agent_test(agent, user_prompt)

    messages = result.new_messages()
    tool_calls = collect_tools(messages)
    assert tool_calls[0].name == "get_db_metadata"
    assert "get_example_queries" in [t.name for t in tool_calls]
    assert "run_sql" in [t.name for t in tool_calls]


@pytest.mark.asyncio
async def test_agent_no_answer(agent):
    user_prompt = "Wat is het weer vandaag?"
    result = await run_agent_test(agent, user_prompt)

    rag_response = result.output
    messages = result.new_messages()
    tool_calls = collect_tools(messages)
    assert "run_sql" not in [t.name for t in tool_calls]
    assert rag_response.sql_query is None or rag_response.sql_query.strip() == ""
    assert rag_response.found_answer == False
    assert rag_response.confidence == 0


@pytest.mark.asyncio
async def test_agent_future_date(agent):
    user_prompt = "Wat is het aantal incidenten geregistreerd in augustus 2026?"
    result = await run_agent_test(agent, user_prompt)

    rag_response = result.output
    messages = result.new_messages()
    tool_calls = collect_tools(messages)
    assert "run_sql" not in [t.name for t in tool_calls]
    assert rag_response.found_answer == False
