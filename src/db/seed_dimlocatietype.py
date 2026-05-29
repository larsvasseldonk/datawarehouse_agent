import duckdb

from src.db.utils import stable_hash_int

_VALID_FROM = "2025-01-01 00:00:00"
_VALID_TO = "8888-12-31 23:59:59"

_LOCATION_TYPES = [
    (3, "Station"),
    (4, "Opstelterrein"),
    (5, "Perron"),
    (6, "Stationshal"),
    (8, "Overweg"),
    (10, "Trein"),
]


def load_dimlocatietype(connection: duckdb.DuckDBPyConnection) -> None:
    rows = [
        (
            stable_hash_int(str(code), label, _VALID_FROM),
            code,
            label,
            _VALID_FROM,
            _VALID_TO,
            1,
        )
        for code, label in _LOCATION_TYPES
    ]

    connection.execute("DELETE FROM dimlocatietype")
    connection.executemany(
        """
        INSERT INTO dimlocatietype (
            dimlocatietypekey,
            locatietype_code,
            locatietype,
            geldig_vanaf,
            geldig_tm,
            ind_huidig
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
