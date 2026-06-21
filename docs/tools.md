# Agent Tools

The SQL agent (`src/agent/sql_agent.py`) is equipped with the following tools.
The refinement agent uses no tools; it reasons over the available table list
injected into its instructions and either asks a clarifying question or hands off
a refined question.

## get_database_metadata

Description: Retrieves the complete warehouse schema metadata — table types
(fact/dimension), table and column comments, columns and data types, primary and
foreign keys, and date ranges for fact tables. Results are cached to
`.cache/db_metadata.json` after the first call.
When to call: First, before drafting any SQL, for every question.
Inputs: (none; reads from the read-only DuckDB connection in `Deps`)
Returns: a dict keyed by table name with `type`, `comment`, `columns`,
`primary_key`, `foreign_keys`, and (for fact tables) `date_range`.

## execute_sql_query

Description: Executes a DuckDB SQL query against the read-only warehouse and
returns the result rows. The connection is opened read-only, so write/DDL
statements (e.g. DROP/DELETE) cannot modify data.
When to call: After schema metadata has been retrieved and a candidate SQL query
has been drafted.
Inputs: `query` (DuckDB SQL string)
Returns: the result rows as a string, or a `SQL Error: ...` message on failure.

---

## Candidate tools (future work)

### create_plotly_visualisation

Description: Converts the result set of an executed query into a Plotly figure
that can be rendered to the user (e.g. a time-series line chart of incidents per
month, or a bar chart of incidents per station), instead of returning only a
text answer.
When to call: After `execute_sql_query` returns rows, when the question implies a
trend or comparison that is clearer as a chart.
Inputs: `rows`, `column_names`, and an inferred `chart_type` / axis mapping.
Returns: a serialized Plotly figure spec (and/or a rendered chart in the
Streamlit app) alongside the text answer.
