import duckdb

from src.db.utils import stable_hash_int

_VALID_FROM = "1900-01-01 00:00:00"
_VALID_TO = "8888-12-31 23:59:59"

_SERIES = [
    ("2200", "Intercity", 2200),
    ("2400", "Intercity", 2400),
    ("2800", "Intercity", 2800),
    ("3000", "Intercity", 3000),
    ("3500", "Intercity", 3500),
    ("3600", "Intercity", 3600),
    ("3700", "Intercity", 3700),
    ("3900", "Intercity", 3900),
    ("5000", "Sprinter", 5000),
    ("5600", "Sprinter", 5600),
    ("6000", "Sprinter", 6000),
    ("7000", "Sprinter", 7000),
    ("8000", "Sprinter", 8000),
    ("8800", "Sprinter", 8800),
]


def load_dimtreinnummer_treinserie(
    connection: duckdb.DuckDBPyConnection,
    per_series_count: int = 10,
) -> None:
    rows = [
        (
            -3,
            "-3",
            "-3",
            "Niet van toepassing",
            _VALID_FROM,
            _VALID_TO,
            1,
        )
    ]

    for treinserie, treintype, base_number in _SERIES:
        for offset in range(per_series_count):
            treinnummer = str(base_number + offset)
            key = stable_hash_int(treinnummer, treinserie, _VALID_FROM)
            rows.append(
                (
                    key,
                    treinnummer,
                    treinserie,
                    treintype,
                    _VALID_FROM,
                    _VALID_TO,
                    1,
                )
            )

    connection.execute("DELETE FROM dimtreinnummer_treinserie")
    connection.executemany(
        """
        INSERT INTO dimtreinnummer_treinserie (
            dimtreinnummer_treinseriekey,
            treinnummer,
            treinserie,
            treintype,
            geldig_vanaf,
            geldig_tm,
            ind_huidig
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
