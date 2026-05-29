from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent, AgentRun
from pydantic_ai.messages import FunctionToolCallEvent
from pydantic_ai._agent_graph import UserPromptNode, ModelRequestNode, CallToolsNode

from jaxn import JSONParserHandler, StreamingJSONParser

from src.agent.llm import LLMProvider
from src.agent.tools import SQLTools
from src.agent.utils import print_messages, print_result

from dotenv import load_dotenv
import logfire

load_dotenv()

logfire.configure(send_to_logfire="if-token-present")
logfire.instrument_pydantic_ai()


DEFAULT_INSTRUCTIONS = """
You are a SQL assistant.

Answer the user question using only data available in the database.

Your user is a data analyst who wants to retrieve insights from the 
database by asking natural language questions. Your task is to translate 
these natural language questions into SQL queries that can be executed 
against the database. 

Make sure to follow the steps and conventions outlined below to ensure 
your SQL queries are accurate and effective.

Make 3 iterations:

1) First iteration:
    - Retrieve the database metadata using get_db_metadata() to understand the schema, including the available tables, their columns, and data types.

2) Second iteration:
    - Analyze the metadata and refine the user's question:
        - If the user's question is too broad or ambiguous, ask for clarification.
        - If the question cannot be answered with the available data, inform the user that the information is not available in the database.
    - Validate search terms:
        - Validate time period with get_date_range() tool if the question involves time-based data.
        - Validate station name with search_station_name() tool if the question involves station-specific data.
    - If the question is clear and can be answered with the available data, get example SQL queries
    - Construct SQL query following the SQL conventions and rules, ensuring to join fact and dimension tables as needed to produce meaningful results. Use the example queries as a guide for structuring your SQL query.
    - Run the SQL query using run_sql() and analyze the results.

3) Third iteration:
    - Review the results of the SQL query and ensure they answer the user's question accurately.
    - If query fails, analyze the error message, correct the query, and try running it again. Make at least three attempts to fix and rerun the query if it fails.
    - Synthesize the final answer to the user's question based on the query results and return it in a clear and concise manner.

IMPORTANT:
- Use only information from the database to answer the user's question.
- Do not make assumptions or use external knowledge.
- If the answer cannot be found in the database, clearly communicate this to the user instead of trying to fabricate an answer.
- Always validate user inputs.
- Strictly follow the SQL conventions and rules stated below.

Additional notes:
- Always use exact matches for station names in SQL queries. Use the search_station_name() tool to validate station names before including them in SQL queries.
- Never use wildcards in SQL queries, as this can lead to inaccurate results. 
- Never use LIKE or ILIKE operators in SQL queries.

Code formatting rules (you MUST follow these when constructing SQL queries):
- Uppercase for SQL keywords (e.g., 'SELECT', 'FROM', 'WHERE', 'SUM')
- Lowercase table and column names
- Use CTEs (Common Table Expressions) for complex queries to break them into manageable parts
- Use meaningful aliases for tables and columns
- Comment your queries to explain complex logic or business rules
""".strip()


@dataclass
class SQLAgentConfig:
    name: str = "SQLAgent"
    instructions: str = DEFAULT_INSTRUCTIONS


class QuerySpecs(BaseModel):
    """
    This model captures the specifications for a SQL query that the agent
    intends to run, including the target fact table, any relevant dimension
    tables, and the time period for which to query the data.
    """

    fact_table: list[str] = Field(description="A list of fact tables to query")
    dimension_tables: list[str] = Field(
        description="A list of dimension tables to join with the fact table"
    )
    from_period: str = Field(
        description="The start of the time period to filter the data (e.g., '2025', '2025-01', '2025-01-01')"
    )
    to_period: str = Field(
        description="The end of the time period to filter the data (e.g., '2025', '2025-01', '2025-01-01')"
    )
    stations: list[str] = Field(description="The stations (dienstregelpuntnaam) to filter the data, if applicable")
    filters: dict = Field(
        description="Filters to apply to the query, represented as a dictionary of column names and their corresponding filter values"
    )


class RAGResponse(BaseModel):
    """
    This model provides a structured representation of the results returned
    by the SQL agent, including the original SQL query, a text representation
    of the results, the number of rows returned, and the agent's confidence
    level in the correctness of the results.
    """

    answer: str = Field(description="The main answer to the user's question in text form")
    found_answer: bool = Field(description="True if relevant information was found in the database, False otherwise")
    query_specs: QuerySpecs = Field(description="Specifications of the SQL query used to generate the answer")
    sql_query: str = Field(description="The SQL query that was run")
    confidence: float = Field(description="Confidence score from 0.0 to 1.0 indicating how certain the answer is")
    confidence_explanation: str = Field(description="Explanation about the confidence level")


class AgentStreamRunner:

    def __init__(self, agent: Agent, handler: JSONParserHandler):
        self.agent = agent
        self.handler = handler
    
    async def run(self, user_prompt: str, message_history=None):
        if message_history is None:
            message_history = []

        async with self.agent.iter(
            user_prompt,
            message_history=message_history,
            output_type=RAGResponse
        ) as agent_run:
            async for node in agent_run:
                if Agent.is_user_prompt_node(node):
                    await self.process_user_node(node, agent_run)
                elif Agent.is_model_request_node(node):
                    await self.process_model_request_node(node, agent_run)
                elif Agent.is_call_tools_node(node):
                    await self.process_call_tools_node(node, agent_run)

            return agent_run.result
    
    async def process_user_node(self, node: UserPromptNode, agent_run: AgentRun):
        print(f"USER PROMPT ({self.agent.name}): {node.user_prompt}")

    async def process_model_request_node(self, node: ModelRequestNode, agent_run: AgentRun):
        args_so_far = ""

        parser = StreamingJSONParser(self.handler)

        async with node.stream(agent_run.ctx) as stream:
            async for response in stream.stream_responses():
                for part in response.parts:
                    if part.part_kind != 'tool-call':
                        continue
                    if part.tool_name != 'final_result':
                        continue

                    args_new = part.args
                    args_new_chunk = args_new[len(args_so_far):]
                    args_so_far = args_new

                    parser.parse_incremental(args_new_chunk)

    async def process_call_tools_node(self, node: CallToolsNode, agent_run: AgentRun):
        async with node.stream(agent_run.ctx) as events:
            async for event in events:
                if not isinstance(event, FunctionToolCallEvent):
                    continue

                tool_name = event.part.tool_name
                args = event.part.args
                print(f"TOOL CALL ({self.agent.name}): {tool_name}({args})")


def create_agent(
    config: SQLAgentConfig, sql_tools: SQLTools, model_provider: LLMProvider
) -> Agent:

    tools = [
        sql_tools.get_db_metadata,
        sql_tools.get_example_queries,
        sql_tools.get_date_range,
        sql_tools.search_station_name,
        sql_tools.run_sql,
    ]
    model = model_provider.get_chatns_model()

    sql_agent = Agent(
        name=config.name,
        model=model,
        instructions=config.instructions,
        tools=tools,
    )

    return sql_agent


def run(agent):
    message_history = []

    while True:
        prompt = input("You (write 'stop' to stop): ")
        if not prompt or prompt.lower().strip() == "stop":
            break

        result = agent.run_sync(
            prompt, message_history=message_history, output_type=RAGResponse
        )

        print_messages(result.all_messages())
        print_result(result.output)
        message_history = result.all_messages()


if __name__ == "__main__":

    agent = create_agent(SQLAgentConfig(), SQLTools(), LLMProvider())
    run(agent)
