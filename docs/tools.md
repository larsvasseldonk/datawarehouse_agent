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
Side effect: caches the last result rows and column names in `Deps` so
`create_plotly_visualisation` can chart them.

## create_plotly_visualisation

Description: Renders the most recent query result set as a Plotly chart (bar,
line, or scatter) using the rows and column names cached by `execute_sql_query`,
and stores the serialized figure in `Deps` for the Streamlit app to render.
When to call: Only when BOTH conditions hold — the user explicitly asked for a
visualisation (chart/graph/plot/trend/comparison) AND `execute_sql_query`
returned a valid, non-empty result set. Never for a failed/empty query or an
unrequested chart.
Inputs: `chart_type` (`bar` | `line` | `scatter`), `x_column`, `y_column`
(column names from the result set), and `title`.
Returns: a short confirmation string; the serialized Plotly figure is written to
`Deps.figure_json` and rendered in the chat alongside the text answer.

---

## Candidate tools (future work)

### resolve_station_name (refinement agent)

Description: Fuzzy-matches a user's free-text station phrase against
`dimdienstregelpunt` (station name + code) and returns the best candidate
matches. This lets the refinement agent confirm or disambiguate stations
(e.g. "Utrecht" → `Ut` / "Utrecht Centraal") against real data instead of
guessing, and ask a precise clarifying question when several stations match.
When to call: During refinement, whenever the user references a station, before
setting the `stations` field and handing off to the SQL agent.
Inputs: `station_query` (the user's station phrase).
Returns: a ranked list of `{dienstregelpunt_naam, dienstregelpunt_code, score}`
candidates (empty if no plausible match).
Impact: highest-impact addition for the refinement agent — it grounds entity
resolution in the data, reducing downstream SQL failures from invalid station
filters.

### retrieve_sql_examples (SQL agent)

Description: Retrieves the top-k most relevant NL→SQL example pairs for the
current question from an indexed example corpus (e.g. via `minsearch`), instead
of injecting a fixed, hardcoded example set into the prompt. The retrieved
examples ground SQL generation in patterns most similar to the question.
When to call: After schema metadata is retrieved and before drafting SQL, for
every question.
Inputs: `question` (the refined question), optional `k` (number of examples).
Returns: a list of `{question, sql}` example pairs ranked by similarity.
Impact: highest-impact addition for the SQL agent — it turns the static example
list into a real retrieval step, improving SQL quality and enabling retrieval
evaluation (hit rate / MRR) over the example corpus.