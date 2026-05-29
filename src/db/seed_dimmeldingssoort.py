import duckdb

from src.db.utils import stable_hash_int

_VALID_FROM = "2025-01-01 00:00:00"
_VALID_TO = "8888-12-31 23:59:59"

_SENTINEL_ROWS = [
    (
        -1,
        -1,
        "<Niet gevonden>",
        None,
        None,
        "1900-01-01 00:00:00",
        "8888-12-31 23:59:59",
        1,
    ),
    (
        -2,
        -2,
        "<Ontbrekend>",
        None,
        None,
        "1900-01-01 00:00:00",
        "8888-12-31 23:59:59",
        1,
    ),
    (
        -3,
        -3,
        "<Niet van toepassing>",
        None,
        None,
        "1900-01-01 00:00:00",
        "8888-12-31 23:59:59",
        1,
    ),
]

_AGRESSIE_TYPES = [
    ("Verbale agressie tegen medewerker", "A", "Agressie tegen medewerker"),
    ("Fysieke agressie tegen medewerker", "A", "Agressie tegen medewerker"),
    ("Bedreiging van conducteur", "A", "Agressie tegen medewerker"),
    ("Spugen richting medewerker", "A", "Agressie tegen medewerker"),
    ("Verbale agressie tegen reiziger", "A", "Agressie tegen reiziger"),
    ("Fysieke agressie tegen reiziger", "A", "Agressie tegen reiziger"),
    ("Intimidatie in trein", "A", "Agressie tegen reiziger"),
    ("Mishandeling op station", "A", "Agressie tegen reiziger"),
    ("Dreigen met voorwerp", "A", "Agressie tegen medewerker"),
    ("Groepsgeweld op perron", "A", "Agressie tegen reiziger"),
    ("Agressie tijdens controle", "A", "Agressie tegen medewerker"),
    ("Agressie bij uitstapconflict", "A", "Agressie tegen reiziger"),
]

_OVERLAST_TYPES = [
    ("Roken in trein", "C", "Overlast"),
    ("Harddrugsgebruik", "A", "Overlast"),
    ("Softdrugsgebruik", "B", "Overlast"),
    ("Veroorzaken geluidsoverlast", "C", "Overlast"),
    ("Openbare dronkenschap", "B", "Overlast"),
    ("Hinderlijk bedelen", "C", "Overlast"),
    ("Verstoring orde op perron", "C", "Overlast"),
    ("Ongewenst filmen reizigers", "C", "Overlast"),
    ("Wildplassen op station", "C", "Overlast"),
    ("Aanhoudende hinder in stationshal", "C", "Overlast"),
    ("Lastigvallen personeel", "B", "Overlast"),
    ("Verlaten bagage na waarschuwing", "B", "Overlast"),
    ("Niet opvolgen aanwijzing", "C", "Overlast"),
    ("Misbruik noodvoorziening", "B", "Overlast"),
    ("Verbaal conflict reizigers", "C", "Overlast"),
    ("Baldadig gedrag in trein", "C", "Overlast"),
    ("Onbevoegd verblijf op emplacement", "B", "Overlast"),
    ("Overtreden huisregels station", "C", "Overlast"),
    ("Hinder met fiets in spits", "C", "Overlast"),
    ("Onveilig gedrag op trap", "C", "Overlast"),
]

_VEILIGHEID_TYPES = [
    ("Vandalisme treininterieur", "B", "Vandalisme"),
    ("Vandalisme stationsvoorziening", "B", "Vandalisme"),
    ("Bekladding materieel", "B", "Vandalisme"),
    ("Bekladding station", "B", "Vandalisme"),
    ("Steenmarter op spoor", "B", "Spoorveiligheid"),
    ("Onbevoegden op spoor", "A", "Spoorveiligheid"),
    ("Overwegincident", "A", "Spoorveiligheid"),
    ("Noodremtrekking zonder noodzaak", "B", "Veiligheid"),
    ("Melding zakkenroller", "A", "Veiligheid"),
    ("Melding diefstal", "A", "Veiligheid"),
    ("Melding wapenbezit", "A", "Veiligheid"),
    ("Ontruiming trein", "B", "Veiligheid"),
    ("Ontruiming stationshal", "B", "Veiligheid"),
    ("Brandmelding trein", "A", "Veiligheid"),
    ("Brandmelding station", "A", "Veiligheid"),
    ("Aanrijding met persoon", "A", "Spoorveiligheid"),
    ("Eenzijdige val reiziger", "B", "Veiligheid"),
    ("Medische noodsituatie", "B", "Veiligheid"),
    ("Technische storing met veiligheidsimpact", "B", "Veiligheid"),
    ("Verdacht pakket", "A", "Veiligheid"),
]


def _build_rows() -> list[tuple]:
    rows: list[tuple] = []
    code = 100
    for meldingsoort, abc_categorie, hoofdsoort in (
        _AGRESSIE_TYPES + _OVERLAST_TYPES + _VEILIGHEID_TYPES
    ):
        rows.append(
            (
                stable_hash_int(str(code), _VALID_FROM),
                code,
                meldingsoort,
                abc_categorie,
                hoofdsoort,
                _VALID_FROM,
                _VALID_TO,
                1,
            )
        )
        code += 1
    return rows


def load_dimmeldingssoort(connection: duckdb.DuckDBPyConnection) -> None:
    rows = _build_rows()

    existing_keys = {row[0] for row in rows}
    for sentinel in _SENTINEL_ROWS:
        if sentinel[0] not in existing_keys:
            rows.append(sentinel)

    connection.execute("DELETE FROM dimmeldingssoort")
    connection.executemany(
        """
        INSERT INTO dimmeldingssoort (
            dimmeldingsoortkey,
            meldingsoort_code,
            meldingsoort,
            abc_categorie,
            hoofdsoort,
            geldig_vanaf,
            geldig_tm,
            ind_huidig
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
