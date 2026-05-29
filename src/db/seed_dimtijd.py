from datetime import time

import duckdb


def _format_block(
    start_hour: int, start_minute: int, end_hour: int, end_minute: int
) -> str:
    return f"{start_hour:02d}:{start_minute:02d}-{end_hour:02d}:{end_minute:02d}"


def load_dimtijd(connection: duckdb.DuckDBPyConnection) -> None:
    rows = []

    for hour in range(24):
        for minute in range(60):
            for second in range(60):
                current = time(hour, minute, second)
                key = hour * 10000 + minute * 100 + second
                is_ochtendspits = 1 if 7 <= hour < 9 else 0
                is_avondspits = 1 if 16 <= hour < 19 else 0

                half_start_minute = 0 if minute < 30 else 30
                half_end_hour = hour
                half_end_minute = half_start_minute + 30
                if half_end_minute == 60:
                    half_end_minute = 0
                    half_end_hour = (hour + 1) % 24

                hour_end = (hour + 1) % 24
                two_hour_end = (hour + 2) % 24

                rows.append(
                    (
                        key,
                        current.strftime("%H:%M:%S"),
                        "Dag" if 7 <= hour < 18 else "Avond",
                        _format_block(
                            hour, half_start_minute, half_end_hour, half_end_minute
                        ),
                        _format_block(hour, 0, hour_end, 0),
                        _format_block(hour, 0, two_hour_end, 0),
                        is_avondspits,
                        is_ochtendspits,
                        1 if (is_ochtendspits or is_avondspits) else 0,
                    )
                )

    connection.execute("DELETE FROM dimtijd")
    connection.executemany(
        """
        INSERT INTO dimtijd (
            dimtijdkey,
            tijd,
            dagdeel,
            halfuurblok,
            uurblok,
            tweeuurblok,
            ind_avondspits,
            ind_ochtendspits,
            ind_spits
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
