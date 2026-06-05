import duckdb
import json

from typing import Any, Dict, List
from pathlib import Path

DB_PATH = "db/db.duckdb"

con = duckdb.connect(DB_PATH)


class SQLTools:
    """
    Provides tools to retrieve database metadata and
    run SQL queries against the DuckDB database.
    """

    def __init__(self, db_path: str = DB_PATH) -> None:
        """
        Initializes the SQLTools instance.

        Args:
            db_path (str): The path to the DuckDB database file.
        """
        self.db_path = db_path
        self.con = duckdb.connect(self.db_path)


    def get_db_metadata(self) -> Dict[str, Any]:
        """
        Retrieves metadata about the database schema, including tables,
        columns, and constraints.

        Returns:
            Dict[str, Any]: A dictionary containing metadata for each table.
        """
        cache_dir = Path(".cache")
        cache_dir.mkdir(exist_ok=True)

        cache_file = cache_dir / "db_metadata.json"

        if cache_file.exists():
            with open(cache_file, "r") as f:
                return json.load(f)

        # Construct metadata dictionary
        db_metadata = {}

        # Get tables and their comments
        tables = self.con.execute("""
            SELECT
                table_name,
                comment AS table_comment
            FROM duckdb_tables()
            WHERE schema_name = 'main'
        """).fetchall()

        # Add tables and their comments
        for table_name, table_comment in tables:
            db_metadata[table_name] = {
                "name": table_name,
                "type": "dimension" if table_name.startswith("dim") else "fact",
                "comment": table_comment,
                "columns": [],
                "primary_key": None,
                "foreign_keys": [],
            }

        # Get columns and their metadata
        columns = self.con.execute("""
            SELECT
                table_name,
                column_name,
                data_type,
                is_nullable,
                comment AS column_comment,
                column_index
            FROM duckdb_columns()
            WHERE
                table_name IN (SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main')
        """).fetchall()

        # Add columns to the corresponding tables
        for (
            table_name,
            column_name,
            data_type,
            is_nullable,
            column_comment,
            column_index,
        ) in columns:
            db_metadata[table_name]["columns"].append(
                {
                    "name": column_name,
                    "type": data_type,
                    "nullable": is_nullable,
                    "comment": column_comment,
                    "index": column_index,
                }
            )

        # Get constraints (primary keys and foreign keys)
        constraints = self.con.execute("""
            SELECT
                table_name,
                constraint_name,
                constraint_type,
                constraint_column_names,
                referenced_table,
                referenced_column_names
            FROM duckdb_constraints()
            WHERE
                table_name IN (SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main')
                AND constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
        """).fetchall()

        # Add constraints to the corresponding tables
        for (
            table_name,
            constraint_name,
            constraint_type,
            constraint_column_names,
            referenced_table,
            referenced_column_names,
        ) in constraints:
            if constraint_type == "PRIMARY KEY":
                db_metadata[table_name]["primary_key"] = constraint_column_names
            elif constraint_type == "FOREIGN KEY":
                db_metadata[table_name]["foreign_keys"].append(
                    {
                        "columns": constraint_column_names,
                        "referenced_table": referenced_table,
                        "referenced_columns": referenced_column_names,
                    }
                )

        # Add date ranges for fact tables with a dimdatumkey column
        for table in db_metadata.values():
            if table["type"] == "fact" and any("dimdatumkey" in col["name"] for col in table["columns"]):
                date_range_str = self._get_date_range(table["name"])
                table["date_range"] = date_range_str

        # Cache the metadata to a JSON file for future use
        with open(cache_file, "w") as f:
            json.dump(db_metadata, f, indent=4)

        return db_metadata
    

    def get_example_queries(self) -> Dict[str, str]:
        """
        Provides example SQL queries for common information needs based on the
        database schema.

        Returns:
            Dict[str, str]: A dictionary mapping information needs to example SQL queries.
        """
        return {
            "What are the total number of incidents per day in 2025?": """
                SELECT d_dtm.datum, SUM(f_inc.aantal_incident) AS incident_count
                FROM factincidentmkns f_inc
                INNER JOIN dimdatum d_dtm ON f_inc.datum_id = d_dtm.datum_id
                WHERE d_dtm.datum BETWEEN '2025-01-01' AND '2025-12-31'
                GROUP BY d_dtm.datum
                ORDER BY d_dtm.datum;
            """,
            "What are the top 5 most common incident types?": """
                SELECT d_mld.meldingssoort, SUM(f_inc.aantal_incident) AS incident_count
                FROM factincidentmkns f_inc
                INNER JOIN dimmeldingssoort d_mld ON f_inc.meldingssoort_id = d_mld.meldingssoort_id
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
    

    def _get_date_range(self, fact_table_name: str) -> str:
        """
        Retrieves the date range for the given fact table.

        Args:
            fact_table_name (str): The name of the fact table with a dimdatumkey column.

        Returns:
            str: A message indicating the date range for the given fact table.
        """

        try:
            query = f"""
                SELECT 
                    min(d_dtm.datum) AS min_date, 
                    max(d_dtm.datum) AS max_date
                FROM {fact_table_name} f_tbl
                INNER JOIN dimdatum d_dtm 
                    ON f_tbl.dimdatumkey = d_dtm.dimdatumkey;
            """

            result = self.con.execute(query).fetchall()
            return f"Date range (both inclusive) to query in {fact_table_name}: {result[0][0]} to {result[0][1]}"
        except Exception as e:
            return f"Error while executing SQL query '{query}': {e}"
    

    def search_station_name(self, station_name: str) -> List[str]:
        """
        Searches for a station name in the database.

        Args:
            station_name (str): The name of the station to search for.
        Returns:
            List[str]: List of stations that match the search criteria, empty list otherwise.
        """

        result = self.con.execute(f"""
            SELECT 
                dienstregelpunt_code, 
                dienstregelpunt_naam
            FROM dimdienstregelpunt
            WHERE dienstregelpunt_naam ILIKE '%{station_name}%'
        """).fetchall()

        list_of_stations = [row[0] for row in result]

        return list_of_stations


    def run_sql(self, query: str) -> str:
        """
        Executes a SQL query against the DuckDB database and
        returns the results as a formatted string.

        Args:
            query (str): The SQL query to execute.

        Returns:
            str: The results of the query or an error message if the query fails.
        """

        try:
            cursor = self.con.execute(query)
            result = cursor.fetchall()
            headers = [col[0] for col in cursor.description]
            lines = ["\t".join(headers)]
            for row in result:
                lines.append("\t".join(str(v) for v in row))
            return "\n".join(lines)

        except Exception as e:
            return f"Error while executing SQL query '{query}': {e}"
