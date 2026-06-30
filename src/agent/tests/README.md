# Tests

Async pytest suite for the refinement and SQL agents. Some tests assert exact
behaviour; others use an LLM judge (`gpt-4.1-mini`) to grade the agent's output
against a list of criteria. Agent and judge runs are traced with Logfire.

## Structure

```text
tests/
├── conftest.py                 # loads .env + configures Logfire (runs once at startup)
├── judge.py                    # LLM judge: assert_criteria(result, [...])
├── utils.py                    # collect_tools() helper for inspecting tool calls
├── test_refinement_agent.py    # tests for the refinement agent
└── test_sql_agent.py           # tests for the SQL agent
```

## Usage

Run from the project root.

```bash
make test
# or
uv run pytest src/agent/tests -s
```

Requires `OPENAI_API_KEY` in your `.env`. Set a Logfire token to send token
usage/cost traces to the dashboard; without one it is a no-op.
