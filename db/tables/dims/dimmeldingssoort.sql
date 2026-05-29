CREATE TABLE IF NOT EXISTS dimmeldingssoort (
    dimmeldingsoortkey DECIMAL(38, 0) NOT NULL,
    meldingsoort_code DECIMAL(38, 0) NOT NULL,
    meldingsoort VARCHAR(255) NOT NULL,
    abc_categorie VARCHAR(255),
    hoofdsoort VARCHAR(255),
    geldig_vanaf TIMESTAMP NOT NULL,
    geldig_tm TIMESTAMP NOT NULL,
    ind_huidig INTEGER NOT NULL,
    CONSTRAINT pk_dimmeldingssoort PRIMARY KEY (dimmeldingsoortkey)
);

COMMENT ON TABLE dimmeldingssoort IS
'Dimensietabel met de categorisering van meldingen in meldingsoort, hoofdsoort, en ABC-categorie conform
landelijke OV-afspraken.';

COMMENT ON COLUMN dimmeldingssoort.dimmeldingsoortkey IS
'Surrogaatsleutel van de meldingsoort. Dit is een sha256 hash van de velden meldingsoort_code en geldig_vanaf.
Voorbeeldwaarde: 42.';
COMMENT ON COLUMN dimmeldingssoort.meldingsoort_code IS
'Code van de meldingsoort. Voorbeeldwaarde: 101.';
COMMENT ON COLUMN dimmeldingssoort.meldingsoort IS
'Naam van de meldingsoort. Voorbeeldwaarde: Vuurwerk, Roken, of Overtreden huisregels.';
COMMENT ON COLUMN dimmeldingssoort.abc_categorie IS
'ABC-categorie conform landelijke OV-afspraken. Voorbeeldwaarden: A (strafrechtelijk), B (spoorwet overtreding),
C (huisregels).';
COMMENT ON COLUMN dimmeldingssoort.hoofdsoort IS
'Hoofdcategorie van de meldingsoort, NS-specifiek. Voorbeeldwaarde: Overlast, Agressie tegen reizger, of Agressie tegen medewerker.';
COMMENT ON COLUMN dimmeldingssoort.geldig_vanaf IS
'Datum en tijd vanaf wanneer de meldingsoort geldig is. Voorbeeldwaarde: 2026-01-01 00:00:00';
COMMENT ON COLUMN dimmeldingssoort.geldig_tm IS
'Datum en tijd tot wanneer de meldingsoort geldig is. Voor voorbeeldwaarde: 9999-12-31 23:59:59 voor huidige meldingsoorten.';
COMMENT ON COLUMN dimmeldingssoort.ind_huidig IS
'Indicator of de meldingsoort momenteel in gebruik is. Voorbeeldwaarde: 1 voor huidige meldingsoorten,
0 voor historische meldingsoorten.';
