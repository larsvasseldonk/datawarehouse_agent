from dataclasses import dataclass

from pydantic_ai import Agent, RunContext
from pydantic import BaseModel, Field

from typing import Annotated
from annotated_types import MinLen

from pathlib import Path
import json
import os
import duckdb
import textwrap
import logfire
import plotly.graph_objects as go


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT_DIR / "db/db.duckdb"


@dataclass
class SQLAgentConfig:
    """
    Configuration class for the SQLAgent, containing any parameters 
    or settings needed for the agent's operation.
    """
    name: str = "SQLAgent"
    model: str = "gpt-4o-mini"

@dataclass
class Deps:
    conn: duckdb.DuckDBPyConnection = duckdb.connect(DB_PATH, read_only=True)
    cache_path: Path = ROOT_DIR / ".cache/db_metadata.json"
    # Populated by execute_sql_query so create_plotly_visualisation can chart the
    # last result set without the model having to re-transmit the rows.
    last_rows: list | None = None
    last_columns: list[str] | None = None
    # Serialized Plotly figure (fig.to_json()) produced by the last successful
    # create_plotly_visualisation call; the app reads this to render the chart.
    figure_json: str | None = None


class SQLResponse(BaseModel):
    """
    This model provides a structured representation of the results returned
    by the SQL agent, including the original SQL query, a text representation
    of the results, the number of rows returned, and the agent's confidence
    level in the correctness of the results.
    """
    answer: str = Field(description="The main answer to the user's question in text form")  
    answer_found: bool = Field(description="Indicates whether the answer to the user's question was found in the database")
    refined_question: str = Field(description="The refined question that was used to generate the SQL query")
    sql_query: str = Field(description="The SQL query that was run")
    success: bool = Field(description="Indicates whether the SQL query executed successfully without errors")
    explanation: str = Field(description="Explanation about how the SQL query was generated and executed")
    visualisation_created: bool = Field(default=False, description="Indicates whether a Plotly visualisation was created for this answer")


sql_config = SQLAgentConfig()
sql_agent = Agent(
    name=sql_config.name,
    model="openai-chat:" + sql_config.model,
    deps_type=Deps, 
    output_type=SQLResponse,
) # type: ignore


def get_sql_examples_str() -> str:
    """
    Returns a formatted string of reference SQL examples for the agent.
    """
    examples = {
        "What are the total number of incidents per day in 2025?": """
            SELECT d_dtm.datum, SUM(f_inc.aantal_incident) AS incident_count
            FROM factincidentmkns f_inc
            INNER JOIN dimdatum d_dtm ON f_inc.dimdatumkey = d_dtm.dimdatumkey
            WHERE d_dtm.datum BETWEEN '2025-01-01' AND '2025-12-31'
            GROUP BY d_dtm.datum
            ORDER BY d_dtm.datum;
        """,
        "What are the top 5 most common incident types?": """
            SELECT d_mld.meldingssoort, SUM(f_inc.aantal_incident) AS incident_count
            FROM factincidentmkns f_inc
            INNER JOIN dimmeldingssoort d_mld ON f_inc.dimmeldingssoortkey = d_mld.dimmeldingssoortkey
            GROUP BY d_mld.meldingssoort
            ORDER BY incident_count DESC
            LIMIT 5;
        """,
        "Hoe veel incidenten zijn er geregistreerd op station Utrecht Centraal in januari 2025?": """
            SELECT 
                d_drp.dienstregelpunt_naam, 
                SUM(f_inc.aantal_incident) AS incident_count
            FROM factincidentmkns f_inc
            INNER JOIN dimdienstregelpunt d_drp
                ON f_inc.dimdienstregelpuntkey_station = d_drp.dimdienstregelpuntkey
            WHERE d_drp.dienstregelpunt_code = 'Ut'
            GROUP BY d_drp.dienstregelpunt_naam
            ORDER BY incident_count DESC;
        """,
    }

    formatted_examples = []
    for question, query in examples.items():
        clean_query = textwrap.dedent(query).strip()
        formatted_examples.append(f"Question: {question}\nSQL:\n```sql\n{clean_query}\n```")
        
    return "\n\n".join(formatted_examples)


@sql_agent.instructions
def provide_instructions() -> str:
    return f"""
You are a SQL generation and execution agent. Your task is to 
translate a user's natural language question into a DuckDB SQL query, 
execute it, and return the answer.

IMPORTANT BEHAVIOR:
1. Always call `get_database_metadata` at the start of the conversation to understand the tables, comments, schemas, and relationships.
2. Refer closely to the example queries below to understand patterns for naming conventions, join conditions, keys, and filter logic (e.g., handling locations like 'Ut' for Utrecht Centraal or handling dates/fact counting patterns).
3. Only call `create_plotly_visualisation` when BOTH of these are true: the user explicitly asked for a visualisation (a chart, graph, plot, trend, or comparison), AND `execute_sql_query` returned a valid, non-empty result set. Never create a visualisation for a failed query, an empty result, or when the user did not ask for one. When you do create one, set `visualisation_created` to true in your final answer.

### REFERENCE SQL EXAMPLES:
{get_sql_examples_str()}
""".strip()


@sql_agent.tool
def get_database_metadata(ctx: RunContext[Deps]) -> dict:
    """Retrieves the complete database schema metadata, including table types (fact/dimension), 
    comments, columns, keys, and date ranges. Always call this first.
    """
    # 1. Check cache early
    if os.path.exists(ctx.deps.cache_path):
        with open(ctx.deps.cache_path, "r") as f:
            return json.load(f)

    # 2. Nested helper function for date ranges
    def get_date_range(table_name: str) -> str:
        try:
            res = ctx.deps.conn.execute(
                f"SELECT MIN(dimdatumkey), MAX(dimdatumkey) FROM {table_name}"
            ).fetchone()
            return f"From {res[0]} to {res[1]}" if res and res[0] is not None else "Unknown"
        except Exception:
            return "Unknown"

    db_metadata = {}

    # 3. Get tables and their comments
    tables = ctx.deps.conn.execute("""
        SELECT table_name, comment AS table_comment
        FROM duckdb_tables()
        WHERE schema_name = 'main'
    """).fetchall()

    for table_name, table_comment in tables:
        db_metadata[table_name] = {
            "name": table_name,
            "type": "dimension" if table_name.startswith("dim") else "fact",
            "comment": table_comment,
            "columns": [],
            "primary_key": None,
            "foreign_keys": [],
        }

    # 4. Get columns and their metadata
    columns = ctx.deps.conn.execute("""
        SELECT table_name, column_name, data_type, is_nullable, comment AS column_comment, column_index
        FROM duckdb_columns()
        WHERE table_name IN (SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main')
    """).fetchall()

    for table_name, column_name, data_type, is_nullable, column_comment, column_index in columns:
        if table_name in db_metadata:
            db_metadata[table_name]["columns"].append({
                "name": column_name,
                "type": data_type,
                "nullable": is_nullable,
                "comment": column_comment,
                "index": column_index,
            })

    # 5. Get constraints (primary keys and foreign keys)
    constraints = ctx.deps.conn.execute("""
        SELECT table_name, constraint_name, constraint_type, constraint_column_names, referenced_table, referenced_column_names
        FROM duckdb_constraints()
        WHERE table_name IN (SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main')
          AND constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
    """).fetchall()

    for table_name, constraint_name, constraint_type, constraint_column_names, referenced_table, referenced_column_names in constraints:
        if table_name in db_metadata:
            if constraint_type == "PRIMARY KEY":
                db_metadata[table_name]["primary_key"] = constraint_column_names
            elif constraint_type == "FOREIGN KEY":
                db_metadata[table_name]["foreign_keys"].append({
                    "columns": constraint_column_names,
                    "referenced_table": referenced_table,
                    "referenced_columns": referenced_column_names,
                })

    # 6. Add date ranges for fact tables using the nested function
    for table in db_metadata.values():
        if table["type"] == "fact" and any("dimdatumkey" in col["name"] for col in table["columns"]):
            table["date_range"] = get_date_range(table["name"])

    # 7. Cache results
    with open(ctx.deps.cache_path, "w") as f:
        json.dump(db_metadata, f, indent=4)

    return db_metadata


@sql_agent.tool
def execute_sql_query(ctx: RunContext[Deps], query: str) -> str:
    """Executes a DuckDB SQL query and returns the rows as a string list."""
    try:
        cursor = ctx.deps.conn.execute(query)
        res = cursor.fetchall()
        # Cache the result set so create_plotly_visualisation can chart it.
        ctx.deps.last_columns = [d[0] for d in cursor.description] if cursor.description else []
        ctx.deps.last_rows = res
        return str(res)
    except Exception as e:
        return f"SQL Error: {e}"


@sql_agent.tool
def create_plotly_visualisation(
    ctx: RunContext[Deps],
    chart_type: str,
    x_column: str,
    y_column: str,
    title: str,
) -> str:
    """Render the most recent query result set as a Plotly chart.

    Only call this after `execute_sql_query` has returned a non-empty result set
    and the user explicitly asked for a visualisation.

    Args:
        chart_type: One of "bar", "line", or "scatter".
        x_column: Column name (from the query result) to use for the x-axis.
        y_column: Column name (from the query result) to use for the y-axis.
        title: A short, descriptive chart title.
    """
    rows = ctx.deps.last_rows
    columns = ctx.deps.last_columns
    if not rows or not columns:
        return "No query results available to visualise. Run execute_sql_query first."

    col_index = {name: i for i, name in enumerate(columns)}
    if x_column not in col_index or y_column not in col_index:
        return f"Unknown column(s). Available columns: {columns}"

    x_vals = [row[col_index[x_column]] for row in rows]
    y_vals = [row[col_index[y_column]] for row in rows]

    chart = chart_type.strip().lower()
    if chart == "bar":
        trace = go.Bar(x=x_vals, y=y_vals)
    elif chart == "line":
        trace = go.Scatter(x=x_vals, y=y_vals, mode="lines+markers")
    elif chart == "scatter":
        trace = go.Scatter(x=x_vals, y=y_vals, mode="markers")
    else:
        return "Unsupported chart_type. Use one of: bar, line, scatter."

    fig = go.Figure(data=[trace])
    fig.update_layout(title=title, xaxis_title=x_column, yaxis_title=y_column)
    ctx.deps.figure_json = fig.to_json()
    return f"Created a {chart} chart titled '{title}'."


if __name__ == "__main__":
    logfire.configure(send_to_logfire="if-token-present")
    logfire.instrument_pydantic_ai()

    deps = Deps()
    sql_history = []

    with logfire.span('sql_agent_session'):
      while True:
            try:
                user_prompt = input("User 👤: ").strip()
                if not user_prompt:
                    continue
                if user_prompt.lower() in ['exit', 'quit']:
                    print("Closing system session. Goodbye!")
                    break
                
                sql_result = sql_agent.run_sync(
                    user_prompt, 
                    message_history=sql_history,
                    deps=deps
                )

                sql_history = sql_result.all_messages()
                print(f"\nSQL Agent 🤖: {sql_result.output}\n")
                    
            except (KeyboardInterrupt, EOFError):
                print("\nTerminal interrupt encountered. Closing cleanly.")
                break
