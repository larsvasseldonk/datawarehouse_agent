CREATE TABLE IF NOT EXISTS dimdatum (
    dimdatumkey DECIMAL(38, 0) NOT NULL,
    datum DATE NOT NULL,
    jaar DECIMAL(38, 0) NOT NULL,
    maand VARCHAR(10) NOT NULL,
    weeknummer DECIMAL(38, 0) NOT NULL,
    dag VARCHAR(10) NOT NULL,
    ind_feestdag INTEGER NOT NULL,
    CONSTRAINT pk_dimdatum PRIMARY KEY (dimdatumkey)
);

COMMENT ON TABLE dimdatum IS
'Datumdimensie met kalenderkenmerken voor rapportages en fact-koppelingen.';

COMMENT ON COLUMN dimdatum.dimdatumkey IS
'Surrogaatsleutel van de datum in formaat JJJJMMDD. Voorbeeldwaarde: 20260101';
COMMENT ON COLUMN dimdatum.datum IS
'Kalenderdatum in formaat JJJJ-MM-DD. Voorbeeldwaarde: 2026-01-01';
COMMENT ON COLUMN dimdatum.jaar IS
'Het kalenderjaar van de datum. Voorbeeldwaarde: 2026';
COMMENT ON COLUMN dimdatum.maand IS
'De maandnaam van de datum. Voorbeeldwaarde: januari';
COMMENT ON COLUMN dimdatum.weeknummer IS
'Weeknummer binnen het jaar. Voorbeeldwaarde: 1';
COMMENT ON COLUMN dimdatum.dag IS
'De weekdagnaam van de datum. Voorbeeldwaarde: donderdag';
COMMENT ON COLUMN dimdatum.ind_feestdag IS
'Indicator of de datum een feestdag is. Voorbeeldwaarde: 1 voor feestdag, 0 voor geen feestdag';
