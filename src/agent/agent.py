from typing import Any, Dict
from dataclasses import dataclass

from pydantic_ai import Agent, AgentRun, AgentRunResult
from pydantic_ai.messages import FunctionToolCallEvent
from pydantic_ai._agent_graph import UserPromptNode, ModelRequestNode, CallToolsNode

from jaxn import JSONParserHandler, StreamingJSONParser

from src.agent.llm import LLMProvider
from src.agent.models import RAGResponse
from src.agent.tools import SQLTools

AgentResponse = RAGResponse | str

from dotenv import load_dotenv
import logfire

load_dotenv()

logfire.configure(send_to_logfire="if-token-present", console=False)
logfire.instrument_pydantic_ai()


DEFAULT_INSTRUCTIONS = """
# Role & Objective
You are an expert Data Assistant Agent specializing in translating natural language questions regarding social safety incident reports into precise, highly accurate SQL queries. 

Because you are dealing with sensitive safety reporting data, correctness is paramount. You must strictly guide the user through a three-phase pipeline: 
1. Feasibility Check
2. Interactive Refinement (populating `QuerySpecs`)
3. SQL Generation, Execution, & Evaluation (instantiating `RAGResponse`)

---

## Phase 1: Feasibility Check
Upon receiving a user query, immediately evaluate if the question can be answered using the available database schema and metadata.

* **Action:** Inspect the database metadata (tables, columns, descriptions).
* **Outcome A (Unfeasible):** If the required data does not exist in the metadata, politely inform the user that the question cannot be answered with the current data, explain *why* briefly, and halt execution.
* **Outcome B (Feasible):** If the question can potentially be answered, silently transition to **Phase 2**.

---

## Phase 2: Interactive Refinement Phase
Your objective in this phase is to completely and accurately populate the `QuerySpecs` data structure. You must interact with the user to gather, clarify, and validate this information before any SQL code is drafted.

* **Target Schema to Populate:** `QuerySpecs` (including `LocationSpecs` and `QueryFilter`).
* **Behavior Rules:**
    * Ask targeted follow-up questions to fill missing mandatory fields (like dates).
    * **Handling Location Constraints:** Disambiguate where the incident took place. Explicitly separate points (stations), trajectories (train numbers), and polygons (regions).
    * Present questions clearly with structured input suggestions and concrete examples:
        * *Station Example:* "Which station? (e.g., 'Amsterdam Centraal' or 'Utrecht Centraal')"
        * *Train Example:* "Which train number or series? (e.g., '4000')"
        * *Region Example:* "Which operational region? (e.g., 'Noord-Oost' or 'Randstad Zuid')"
    * **Handling Optional Fields:** For optional parameters (like non-spatial `filters`), you *must* explicitly check with the user if they want to apply them before proceeding.
* **Exit Condition:** Do not leave this phase until all mandatory `QuerySpecs` fields are filled and optional fields have been explicitly confirmed or declined by the user.
* **Clarification rule:** If mandatory information is still missing, return a plain-text clarification question (a simple string). Do NOT return a `RAGResponse`. Ask exactly one question that unblocks the next step.

---

## Phase 3: SQL Generation, Execution & Evaluation
Once the `QuerySpecs` object is fully populated, transition to execution and build the final `RAGResponse`.

1. **Few-Shot Knowledge Retrieval:**
    * Fetch relevant example SQL queries from the knowledge base to ensure correct join structures and business logic mapping.
    * *Constraint:* You are allowed to perform this retrieval step exactly **once (max 1 time)** per session.
2. **SQL Generation & Execution:**
    * Map the `QuerySpecs` strictly to the database columns. 
    * If `location.train_numbers` is populated, filter by the specific train series column. If `location.regions` is populated, perform the proper dimension join for regional filtering.
    * Convert periods to strict `YYYY-MM-DD` date structures.
    * Execute the query safely against the database to retrieve the raw results and the exact `row_count`.
3. **Confidence Score Assessment:**
    * Evaluate the generated SQL code for **technical correctness** (syntax, join predicates) and **functional correctness** (does the logic strictly match the user's safety query?).
    * Deduct points if schemas were ambiguous or if complex business logic assumptions had to be made.

---

## Final Output Structure
You must return your final output matching the schema of the `RAGResponse` model:

* **answer:** Natural language summary of the data. If 0 rows are returned, explicitly state that no incidents matched the criteria.
* **query_executed_successfully:** True if the SQL query ran without errors (even if 0 rows returned). False if a DB error occurred.
* **row_count:** The exact number of rows returned by the SQL execution.
* **query_specs:** The finalized `QuerySpecs` object used for the run.
* **sql_query:** The exact, clean SQL code executed.
* **confidence:** Score from 0.0 to 1.0.
* **confidence_explanation:** Technical and functional justification for the score.
* **followup_questions:** 2-3 proactive, highly relevant follow-up questions that are *completely answerable* using the available database metadata.

Tool discipline:
* Call `get_db_metadata()` at most once per session.
* If `get_db_metadata()` has already been called, reuse the earlier metadata. Do NOT call it again.
* Do not loop on metadata retrieval when user clarification is the real blocker.
""".strip()


@dataclass
class SQLAgentConfig:
    name: str = "SQLAgent"
    instructions: str = DEFAULT_INSTRUCTIONS


class RAGResponseHandler(JSONParserHandler):
    def on_value_chunk(self, path: str, field_name: str, chunk: str) -> None:
        if path == '' and field_name == 'answer':
            print(chunk, end='', flush=True)

    def on_field_end(self, path: str, field_name: str, value: str, parsed_value: Any = None) -> None:
        if path == '' and field_name == 'sql_query':
            print('sql query:', value)

    def on_array_item_end(self, path: str, field_name: str, item: Dict[str, Any] = None) -> None:
        if field_name == 'followup_questions':
            print('follow up question:', item)


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
            async for response in stream.stream_response():
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

    metadata_cache: dict | None = None

    def get_db_metadata() -> dict:
        """Retrieves database schema metadata. May only be called once per session."""
        nonlocal metadata_cache
        if metadata_cache is None:
            metadata_cache = sql_tools.get_db_metadata()
            return metadata_cache
        return {
            "already_loaded": True,
            "message": "Metadata already retrieved. Reuse it and proceed to the next phase.",
        }

    tools = [
        get_db_metadata,
        sql_tools.get_example_queries,
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


class NamedCallback:

    def __init__(self, agent):
        self.agent_name = agent.name

    async def print_function_calls(self, ctx, event):
        # Detect nested streams
        if hasattr(event, "__aiter__"):
            async for sub in event:
                await self.print_function_calls(ctx, sub)
            return

        if isinstance(event, FunctionToolCallEvent):
            tool_name = event.part.tool_name
            args = event.part.args
            print(f"TOOL CALL ({self.agent_name}): {tool_name}({args})")

    async def __call__(self, ctx, event):
        return await self.print_function_calls(ctx, event)
    

async def print_stream_node(node: ModelRequestNode, agent_run: AgentRun):
    args_so_far = ""

    parser = StreamingJSONParser(RAGResponseHandler())

    async with node.stream(agent_run.ctx) as stream:
        async for response in stream.stream_response():
            for part in response.parts:
                if part.part_kind != 'tool-call':
                    continue
                if part.tool_name != 'final_result':
                    continue

                args_new = part.args
                args_new_chunk = args_new[len(args_so_far):]
                args_so_far = args_new

                parser.parse_incremental(args_new_chunk)

    print()


async def print_tool_calls(node: CallToolsNode, agent_run: AgentRun, agent_name: str):
    async with node.stream(agent_run.ctx) as events:
        async for event in events:
            if isinstance(event, FunctionToolCallEvent):
                tool_name = event.part.tool_name
                args = event.part.args
                print(f"TOOL CALL ({agent_name}): {tool_name}({args})")

    

async def run_agent(
        agent: Agent,
        user_prompt: str,
        message_history=None
    ) -> AgentRunResult:
    callback = NamedCallback(agent)

    if message_history is None:
        message_history = []

    result = await agent.run(
        user_prompt,
        event_stream_handler=callback,
        message_history=message_history,
        output_type=RAGResponse
    )

    return result


async def run_agent_stream(
        agent: Agent,
        user_prompt: str,
        message_history=None
    ):

    if message_history is None:
        message_history = []

    async with agent.iter(
        user_prompt,
        message_history=message_history,
        output_type=AgentResponse
    ) as agent_run:
        async for node in agent_run:
            if Agent.is_user_prompt_node(node):
                print(f"USER PROMPT ({agent.name}): {node.user_prompt}")
            elif Agent.is_model_request_node(node):
                await print_stream_node(node, agent_run)
            elif Agent.is_call_tools_node(node):
                await print_tool_calls(node, agent_run, agent.name)

        return agent_run.result
