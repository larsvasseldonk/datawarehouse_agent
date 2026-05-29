from pathlib import Path

import duckdb

from src.db import (
    seed_dimdatum,
    seed_dimdienstregelpunt,
    seed_dimlocatietype,
    seed_dimmeldingssoort,
    seed_dimtijd,
    seed_dimtreinnummer_treinserie,
    seed_factincidentmkns,
)


class DuckDBManager:
    def __init__(self, db_name: str = "db") -> None:
        self.db_path = Path("db/" + db_name + ".duckdb")

    def reset_database(self) -> None:
        if self.db_path.exists():
            self.db_path.unlink()

    def run_sql_file(
        self, connection: duckdb.DuckDBPyConnection, sql_file: str | Path
    ) -> None:
        sql = Path(sql_file).read_text(encoding="utf-8")
        connection.execute(sql)

    def _create_schema(self, connection: duckdb.DuckDBPyConnection) -> None:
        sql_files = [
            "db/tables/dims/dimdatum.sql",
            "db/tables/dims/dimdienstregelpunt.sql",
            "db/tables/dims/dimlocatietype.sql",
            "db/tables/dims/dimmeldingssoort.sql",
            "db/tables/dims/dimtijd.sql",
            "db/tables/dims/dimtreinnummer_treinserie.sql",
            "db/tables/facts/factincidentmkns.sql",
        ]

        for sql_file in sql_files:
            self.run_sql_file(connection, sql_file)

    def _load_data(
        self, connection: duckdb.DuckDBPyConnection, fact_row_count: int = 10000
    ) -> None:
        seed_dimdatum.load_dimdatum(connection)
        seed_dimdienstregelpunt.load_dimdienstregelpunt(connection)
        seed_dimlocatietype.load_dimlocatietype(connection)
        seed_dimmeldingssoort.load_dimmeldingssoort(connection)
        seed_dimtijd.load_dimtijd(connection)
        seed_dimtreinnummer_treinserie.load_dimtreinnummer_treinserie(connection)
        seed_factincidentmkns.load_factincidentmkns(
            connection, row_count=fact_row_count
        )

    def build_database(self, fact_row_count: int = 10000) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.reset_database()

        connection = duckdb.connect(str(self.db_path))
        try:
            self._create_schema(connection)
            self._load_data(connection, fact_row_count=fact_row_count)
        finally:
            connection.close()


if __name__ == "__main__":
    manager = DuckDBManager()
    manager.build_database(fact_row_count=100000)
