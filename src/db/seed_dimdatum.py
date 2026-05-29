from datetime import date, timedelta

import duckdb

_DUTCH_MONTHS = {
    1: "januari",
    2: "februari",
    3: "maart",
    4: "april",
    5: "mei",
    6: "juni",
    7: "juli",
    8: "augustus",
    9: "september",
    10: "oktober",
    11: "november",
    12: "december",
}

_DUTCH_DAYS = {
    0: "maandag",
    1: "dinsdag",
    2: "woensdag",
    3: "donderdag",
    4: "vrijdag",
    5: "zaterdag",
    6: "zondag",
}

_HOLIDAYS_2025 = {
    date(2025, 1, 1),
    date(2025, 4, 18),
    date(2025, 4, 20),
    date(2025, 4, 21),
    date(2025, 4, 26),
    date(2025, 5, 5),
    date(2025, 5, 29),
    date(2025, 6, 8),
    date(2025, 6, 9),
    date(2025, 12, 25),
    date(2025, 12, 26),
}


def load_dimdatum(connection: duckdb.DuckDBPyConnection) -> None:
    start_date = date(2025, 1, 1)
    end_date = date(2025, 12, 31)

    rows = []
    current = start_date
    while current <= end_date:
        rows.append(
            (
                int(current.strftime("%Y%m%d")),
                current,
                current.year,
                _DUTCH_MONTHS[current.month],
                current.isocalendar().week,
                _DUTCH_DAYS[current.weekday()],
                1 if current in _HOLIDAYS_2025 else 0,
            )
        )
        current += timedelta(days=1)

    connection.execute("DELETE FROM dimdatum")
    connection.executemany(
        """
        INSERT INTO dimdatum (
            dimdatumkey,
            datum,
            jaar,
            maand,
            weeknummer,
            dag,
            ind_feestdag
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
