import duckdb
import json
from datetime import datetime
from zoneinfo import ZoneInfo

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
        self._stations_cache = None


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
                cached_metadata = json.load(f)
            if "_stations" in cached_metadata:
                cached_metadata.pop("_stations", None)
                with open(cache_file, "w") as f:
                    json.dump(cached_metadata, f, indent=4)
            return cached_metadata

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
    

    def validate_date_range(self, from_date: str, to_date: str) -> tuple[bool, str, str, str]:
        """
        Validates that the requested date range is within the database's available data.
        Uses precomputed metadata for performance.
        
        Args:
            from_date: Start date (YYYY-MM-DD format)
            to_date: End date (YYYY-MM-DD format)
        
        Returns:
            Tuple of (is_valid, min_date, max_date, message)
        """
        try:
            # Get metadata with precomputed date range
            metadata = self.get_db_metadata()
            
            # Extract date range from factincidentmkns metadata
            if "factincidentmkns" not in metadata:
                return False, "", "", "Could not find factincidentmkns in metadata"
            
            date_range_str = metadata["factincidentmkns"].get("date_range", "")
            # Parse: "Date range (both inclusive) to query in factincidentmkns: 2025-01-01 to 2025-12-31"
            if not date_range_str or " to " not in date_range_str:
                return False, "", "", "Could not parse date range from metadata"
            
            parts = date_range_str.split(" to ")
            min_date = parts[-2].strip().split()[-1]  # Get last part before " to "
            max_date = parts[-1].strip()
            
            # Validate date format and comparison
            try:
                from datetime import datetime
                from_dt = datetime.strptime(from_date, "%Y-%m-%d")
                to_dt = datetime.strptime(to_date, "%Y-%m-%d")
                min_dt = datetime.strptime(min_date, "%Y-%m-%d")
                max_dt = datetime.strptime(max_date, "%Y-%m-%d")
                
                is_valid = (from_dt >= min_dt and to_dt <= max_dt and from_dt <= to_dt)
                
                if is_valid:
                    message = f"✓ Date range valid. Database contains incident data from {min_date} to {max_date}."
                else:
                    message = f"✗ Invalid date range. Database contains incident data from {min_date} to {max_date}. "
                    if from_dt > to_dt:
                        message += "From date must be before or equal to to date."
                    elif from_dt < min_dt or to_dt > max_dt:
                        message += "Requested dates are outside available data range."
                
                return is_valid, min_date, max_date, message
                
            except ValueError as e:
                return False, min_date, max_date, f"Invalid date format: {e}"
        
        except Exception as e:
            return False, "", "", f"Error validating date range: {e}"

    def _get_all_stations_cached(self) -> List[Dict[str, str]]:
        """
        Retrieves all stations and regions from dimdienstregelpunt and caches them.
        
        Returns:
            List[Dict]: List of dicts with dienstregelpunt_code, dienstregelpunt_naam, and region info.
        """
        try:
            result = self.con.execute("""
                SELECT 
                    dienstregelpunt_code,
                    dienstregelpunt_naam,
                    COALESCE(regio_rsv_naam, 'Unknown') as regio_rsv_naam,
                    COALESCE(regio_ssvo_naam, 'Unknown') as regio_ssvo_naam
                FROM dimdienstregelpunt
                WHERE ind_huidig = 1
                ORDER BY dienstregelpunt_naam
            """).fetchall()
            
            stations = [
                {
                    "code": row[0],
                    "naam": row[1],
                    "regio_rsv": row[2],
                    "regio_ssvo": row[3]
                }
                for row in result
            ]
            return stations
        except Exception as e:
            print(f"Error retrieving stations: {e}")
            return []

    def _get_stations_cache_file(self) -> Path:
        """
        Returns the cache file path for station and region data.
        """
        cache_dir = Path(".cache")
        cache_dir.mkdir(exist_ok=True)
        return cache_dir / "stations.json"

    def _load_or_build_stations_cache(self) -> List[Dict[str, str]]:
        """
        Loads stations from a dedicated cache file, or rebuilds it from the database.
        """
        cache_file = self._get_stations_cache_file()

        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    return json.load(f)
            except Exception:
                # If cache is corrupted, rebuild it from source.
                pass

        stations = self._get_all_stations_cached()
        with open(cache_file, "w") as f:
            json.dump(stations, f, indent=4)
        return stations
    
    
    def get_all_stations(self) -> List[Dict[str, str]]:
        """
        Returns the cached list of all available stations with their regions.
        
        Returns:
            List[Dict]: List of station dicts with code, naam, and region info.
        """
        if self._stations_cache is None:
            self._stations_cache = self._load_or_build_stations_cache()
        return self._stations_cache
    
    
    def validate_station_name(self, station_name: str) -> tuple[bool, str]:
        """
        Validates that a station name exists exactly in the database.
        Uses cached station data for performance.
        
        Args:
            station_name: The exact station name to validate
        
        Returns:
            Tuple of (is_valid, message)
        """
        stations = self.get_all_stations()
        
        # Check for exact match
        matching_station = next(
            (s for s in stations if s["naam"].lower() == station_name.lower()),
            None
        )
        
        if matching_station:
            msg = f"✓ Station '{matching_station['naam']}' (code: {matching_station['code']}) found. "
            msg += f"Region RSV: {matching_station['regio_rsv']}, Region SSVO: {matching_station['regio_ssvo']}"
            return True, msg
        else:
            return False, f"✗ Station '{station_name}' not found. Use a valid station name."


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


    def run_sql_structured(self, query: str) -> Dict[str, Any]:
        """
        Executes a SQL query and returns a structured payload that includes
        execution status, row_count, column names, and row data.
        """

        try:
            cursor = self.con.execute(query)
            rows = cursor.fetchall()
            columns = [col[0] for col in cursor.description]

            return {
                "success": True,
                "row_count": len(rows),
                "columns": columns,
                "rows": rows,
            }
        except Exception as e:
            return {
                "success": False,
                "row_count": 0,
                "columns": [],
                "rows": [],
                "error": str(e),
            }


class PyTools:
    """
    Provides non-database Python utility tools.
    """

    def get_current_datetime(self) -> Dict[str, str]:
        """
        Returns the current Amsterdam datetime context for resolving relative date phrases.

        Returns:
            Dict[str, str]: Current timestamp details including ISO date/time and weekday.
        """
        amsterdam_tz = ZoneInfo("Europe/Amsterdam")
        now = datetime.now(amsterdam_tz)
        return {
            "current_datetime_iso": now.isoformat(),
            "current_date": now.date().isoformat(),
            "current_time": now.strftime("%H:%M:%S"),
            "weekday": now.strftime("%A"),
            "timezone": "Europe/Amsterdam",
        }
