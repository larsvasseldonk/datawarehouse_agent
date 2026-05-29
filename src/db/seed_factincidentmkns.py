from datetime import datetime, timezone

import duckdb

from src.db.utils import make_rng


def _sample_opmerking(
    incident_type: str,
    location_name: str,
    location_context: str,
    train_number: str | None,
    hour: int,
) -> str:
    fragments = [
        f"({hour:02d}:12 u) Melding ontvangen: {incident_type}.",
        f"Locatie: {location_name} ({location_context}).",
    ]
    if train_number:
        fragments.append(f"Trein: {train_number}.")
    fragments.append("Incident afgehandeld conform standaardproces Meldkamer NS.")
    return " ".join(fragments)


def load_factincidentmkns(
    connection: duckdb.DuckDBPyConnection,
    row_count: int = 10_000,
    seed: int = 42,
) -> None:
    rng = make_rng(seed)

    date_keys = [
        r[0] for r in connection.execute("SELECT dimdatumkey FROM dimdatum").fetchall()
    ]
    time_keys = [
        r[0] for r in connection.execute("SELECT dimtijdkey FROM dimtijd").fetchall()
    ]

    stations = connection.execute("""
        SELECT dimdienstregelpuntkey, dienstregelpunt_naam
        FROM dimdienstregelpunt
        WHERE ind_huidig = 1
          AND dimdienstregelpuntkey > 0
          AND dienstregelpunt_code NOT IN ('VIN', 'GNVP')
        """).fetchall()

    station_keys = [r[0] for r in stations]
    station_names_by_key = {r[0]: r[1] for r in stations}

    loc_types = {
        code: key
        for key, code in connection.execute(
            "SELECT dimlocatietypekey, locatietype_code FROM dimlocatietype"
        ).fetchall()
    }

    melding_rows = connection.execute("""
        SELECT dimmeldingsoortkey, meldingsoort, COALESCE(hoofdsoort, '')
        FROM dimmeldingssoort
        WHERE ind_huidig = 1 AND dimmeldingsoortkey > 0
        """).fetchall()

    train_rows = connection.execute("""
        SELECT dimtreinnummer_treinseriekey, treinnummer
        FROM dimtreinnummer_treinserie
        WHERE ind_huidig = 1 AND dimtreinnummer_treinseriekey > 0
        """).fetchall()

    train_keys = [r[0] for r in train_rows]
    train_numbers_by_key = {r[0]: r[1] for r in train_rows}

    location_station_key = loc_types[3]
    location_train_key = loc_types[10]
    location_yard_key = loc_types[4]

    rows = []
    incident_nr_start = 4_900_000
    load_ts = datetime.now(timezone.utc).replace(tzinfo=None)

    for index in range(row_count):
        scenario = rng.random()

        dimdatumkey = rng.choice(date_keys)
        dimtijdkey = rng.choice(time_keys)

        melding_key, meldingsoort, hoofdsoort = rng.choice(melding_rows)
        ind_agressie = 1 if hoofdsoort.startswith("Agressie") else 0
        ind_letsel = 1 if (ind_agressie == 1 and rng.random() < 0.12) else 0

        if scenario < 0.60:
            station_key = rng.choice(station_keys)
            dimdienstregelpuntkey = station_key
            dimdienstregelpuntkey_van = -3
            dimdienstregelpuntkey_naar = -3
            dimdienstregelpuntkey_station = station_key
            dimlocatietypekey = location_station_key
            dimtreinnummer_treinseriekey = -3
            location_name = station_names_by_key.get(station_key, "Onbekend station")
            location_context = "station"
            train_number = None
        elif scenario < 0.95:
            start_key = rng.choice(station_keys)
            end_key = rng.choice(station_keys)
            if len(station_keys) > 1:
                while end_key == start_key:
                    end_key = rng.choice(station_keys)

            report_key = end_key
            train_key = rng.choice(train_keys)

            dimdienstregelpuntkey = report_key
            dimdienstregelpuntkey_van = start_key
            dimdienstregelpuntkey_naar = end_key
            dimdienstregelpuntkey_station = -3
            dimlocatietypekey = location_train_key
            dimtreinnummer_treinseriekey = train_key
            location_name = station_names_by_key.get(report_key, "Onbekend station")
            location_context = "trein"
            train_number = train_numbers_by_key.get(train_key)
        else:
            station_key = rng.choice(station_keys)
            dimdienstregelpuntkey = station_key
            dimdienstregelpuntkey_van = -3
            dimdienstregelpuntkey_naar = -3
            dimdienstregelpuntkey_station = -3
            dimlocatietypekey = location_yard_key
            dimtreinnummer_treinseriekey = -3
            location_name = station_names_by_key.get(station_key, "Onbekende locatie")
            location_context = "opstelterrein"
            train_number = None

        hour = int(dimtijdkey) // 10000
        opmerking = _sample_opmerking(
            incident_type=meldingsoort,
            location_name=location_name,
            location_context=location_context,
            train_number=train_number,
            hour=hour,
        )

        rows.append(
            (
                dimdatumkey,
                dimdienstregelpuntkey,
                dimdienstregelpuntkey_van,
                dimdienstregelpuntkey_naar,
                dimdienstregelpuntkey_station,
                dimlocatietypekey,
                melding_key,
                dimtijdkey,
                dimtreinnummer_treinseriekey,
                1,
                ind_agressie,
                ind_letsel,
                incident_nr_start + index,
                opmerking,
                load_ts,
            )
        )

    connection.execute("DELETE FROM factincidentmkns")
    connection.executemany(
        """
        INSERT INTO factincidentmkns (
            dimdatumkey,
            dimdienstregelpuntkey,
            dimdienstregelpuntkey_van,
            dimdienstregelpuntkey_naar,
            dimdienstregelpuntkey_station,
            dimlocatietypekey,
            dimmeldingsoortkey,
            dimtijdkey,
            dimtreinnummer_treinseriekey,
            aantal_incident,
            ind_agressie,
            ind_letsel,
            incident_nr,
            opmerking,
            loaddate_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
