import random

import duckdb

from src.db.utils import stable_hash_int

_VALID_FROM = "2025-01-01 00:00:00"
_VALID_TO = "8888-12-31 23:59:59"
_SEED = 2026
_TARGET_TOTAL_ROWS = 4372

_RSV_REGIONS = ["Noord-Oost", "Randstad-Noord", "Randstad-Zuid", "Zuid"]

_SSVO_REGIONS = [
    "PE Noord",
    "PE Midden",
    "PE Zuid",
    "Twente-IJssel",
    "West-Brabant en Zeeland",
    "Groot Amsterdam",
    "Rotterdam-Den Haag",
]

_CITY_NAMES = [
    "Amsterdam",
    "Rotterdam",
    "Den Haag",
    "Utrecht",
    "Eindhoven",
    "Groningen",
    "Leeuwarden",
    "Zwolle",
    "Arnhem",
    "Nijmegen",
    "Maastricht",
    "Amersfoort",
    "Haarlem",
    "Leiden",
    "Dordrecht",
    "Alkmaar",
    "Hilversum",
    "Deventer",
    "Enschede",
    "Assen",
    "Venlo",
    "Breda",
    "Tilburg",
    "Roosendaal",
    "Hoorn",
    "Den Helder",
    "Vlissingen",
    "Middelburg",
    "Lelystad",
    "Almere",
]

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

_CORE_STATIONS = [
    ("ASD", "Amsterdam Centraal"),
    ("RTD", "Rotterdam Centraal"),
    ("UT", "Utrecht Centraal"),
    ("GVC", "Den Haag Centraal"),
    ("EHV", "Eindhoven Centraal"),
    ("GN", "Groningen"),
    ("LWR", "Leeuwarden"),
    ("ZL", "Zwolle"),
    ("AH", "Arnhem Centraal"),
    ("NM", "Nijmegen"),
    ("MT", "Maastricht"),
    ("AMF", "Amersfoort Centraal"),
    ("HLM", "Haarlem"),
    ("LEDN", "Leiden Centraal"),
    ("DDR", "Dordrecht"),
    ("AMR", "Alkmaar"),
    ("HVSM", "Hilversum"),
    ("DV", "Deventer"),
    ("ES", "Enschede"),
    ("ASN", "Assen"),
    ("VL", "Venlo"),
    ("BD", "Breda"),
    ("TL", "Tilburg"),
    ("RSD", "Roosendaal"),
    ("HRN", "Hoorn"),
    ("HDR", "Den Helder"),
    ("VS", "Vlissingen"),
    ("MDB", "Middelburg"),
    ("LLS", "Lelystad Centrum"),
    ("ALM", "Almere Centrum"),
    ("VIN", "Virtueel Incheckpunt NS"),
    ("GNVP", "Geen opvolgend stoppunt"),
]


def _build_row(
    code: str,
    naam: str,
    regio_rsv: str,
    regio_ssvo: str,
    ind_backup_vens: int,
    ind_standplaats_vens: int,
) -> tuple[int, str, str, str, str, int, int, str, str, int]:
    return (
        stable_hash_int(code, _VALID_FROM),
        code,
        naam,
        regio_rsv,
        regio_ssvo,
        ind_backup_vens,
        ind_standplaats_vens,
        _VALID_FROM,
        _VALID_TO,
        1,
    )


def _generate_rows(total_positive_rows: int) -> list[tuple]:
    rng = random.Random(_SEED)
    rows: list[tuple] = []
    used_codes: set[str] = set()

    for code, name in _CORE_STATIONS:
        used_codes.add(code)
        rows.append(
            _build_row(
                code=code,
                naam=name,
                regio_rsv=rng.choice(_RSV_REGIONS),
                regio_ssvo=rng.choice(_SSVO_REGIONS),
                ind_backup_vens=1 if rng.random() < 0.08 else 0,
                ind_standplaats_vens=1 if rng.random() < 0.18 else 0,
            )
        )

    index = 1
    while len(rows) < total_positive_rows:
        city = rng.choice(_CITY_NAMES)
        code = f"DRP{index:04d}"
        if code in used_codes:
            index += 1
            continue

        used_codes.add(code)
        suffix = rng.choice(["Centrum", "Noord", "Zuid", "West", "Oost", "P+R"])
        type_name = rng.choice(["Station", "Halte", "Knooppunt"])
        rows.append(
            _build_row(
                code=code,
                naam=f"{city} {suffix} {type_name}",
                regio_rsv=rng.choice(_RSV_REGIONS),
                regio_ssvo=rng.choice(_SSVO_REGIONS),
                ind_backup_vens=1 if rng.random() < 0.05 else 0,
                ind_standplaats_vens=1 if rng.random() < 0.12 else 0,
            )
        )
        index += 1

    return rows


def load_dimdienstregelpunt(connection: duckdb.DuckDBPyConnection) -> None:
    positive_rows = _TARGET_TOTAL_ROWS - len(_SENTINEL_ROWS)
    rows = _generate_rows(positive_rows)

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
