import csv
from pathlib import Path

import duckdb

from src.db.utils import stable_hash_int

_STATIONS_CSV_PATH = Path(__file__).resolve().parents[2] / "data" / "stations.csv"

_SENTINEL_ROWS = [
    (
        -1,
        "-1",
        "<Niet gevonden>",
        None,
        None,
        0,
        0,
        "1900-01-01 00:00:00",
        "8888-12-31 23:59:59",
        1,
    ),
    (
        -2,
        "-2",
        "<Ontbrekend>",
        None,
        None,
        0,
        0,
        "1900-01-01 00:00:00",
        "8888-12-31 23:59:59",
        1,
    ),
    (
        -3,
        "-3",
        "<Niet van toepassing>",
        None,
        None,
        0,
        0,
        "1900-01-01 00:00:00",
        "8888-12-31 23:59:59",
        1,
    ),
]


def _load_station_rows() -> list:
    rows = []
    seen_codes = set()
    seen_names = set()

    with _STATIONS_CSV_PATH.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for source_row in reader:
            code = source_row["STATIONSAFKORTING"].strip()
            naam = source_row["STATIONS_NAAM"].strip()

            if code in seen_codes:
                raise ValueError(f"Duplicate station code in stations.csv: {code}")

            if naam in seen_names:
                raise ValueError(f"Duplicate station name in stations.csv: {naam}")

            seen_codes.add(code)
            seen_names.add(naam)
            geldig_vanaf = source_row["GELDIGVANAF"].strip()
            rows.append(
                (
                    stable_hash_int(code, geldig_vanaf),
                    code,
                    naam,
                    source_row["REGIO_RSV_NAAM"].strip() or None,
                    source_row["REGIO_SSVO_NAAM"].strip() or None,
                    int(source_row["IND_BACKUP_VENS"]),
                    int(source_row["IND_STANDPLAATS_VENS"]),
                    geldig_vanaf,
                    source_row["GELDIGTM"].strip(),
                    int(source_row["IND_HUIDIG"]),
                )
            )

    return rows


def load_dimdienstregelpunt(connection: duckdb.DuckDBPyConnection) -> None:
    rows = _load_station_rows()

    existing_keys = {row[0] for row in rows}
    for sentinel in _SENTINEL_ROWS:
        if sentinel[0] not in existing_keys:
            rows.append(sentinel)

    connection.execute("DELETE FROM dimdienstregelpunt")
    connection.executemany(
        """
        INSERT INTO dimdienstregelpunt (
            dimdienstregelpuntkey,
            dienstregelpunt_code,
            dienstregelpunt_naam,
            regio_rsv_naam,
            regio_ssvo_naam,
            ind_backup_vens,
            ind_standplaats_vens,
            geldig_vanaf,
            geldig_tm,
            ind_huidig
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
