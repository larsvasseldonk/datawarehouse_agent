CREATE TABLE IF NOT EXISTS dimdienstregelpunt (
    dimdienstregelpuntkey DECIMAL(38, 0) NOT NULL,
    dienstregelpunt_code VARCHAR(50) NOT NULL,
    dienstregelpunt_naam VARCHAR(255) NOT NULL,
    regio_rsv_naam VARCHAR(255),
    regio_ssvo_naam VARCHAR(255),
    ind_backup_vens INTEGER,
    ind_standplaats_vens INTEGER,
    geldig_vanaf TIMESTAMP NOT NULL,
    geldig_tm TIMESTAMP NOT NULL,
    ind_huidig INTEGER NOT NULL,
    CONSTRAINT pk_dimdienstregelpunt PRIMARY KEY (dimdienstregelpuntkey)
);

COMMENT ON TABLE dimdienstregelpunt IS
'Dimensietabel met alle dienstregelpunten (stations, haltes en knooppunten) '
'op het NS-netwerk. Wordt gebruikt als locatiesleutel in factabellen voor '
'rapportage per regio.';

COMMENT ON COLUMN dimdienstregelpunt.dimdienstregelpuntkey IS
'Surrogaatsleutel van het dienstregelpunt. Dit is een sha256 hash van de velden '
'dienstregelpunt_code en geldig_vanaf. Voorbeeldwaarde: 1234. Speciale waarde: -3 '
'bij onbekende of niet-van-toepassing locatie.';
COMMENT ON COLUMN dimdienstregelpunt.dienstregelpunt_code IS
'Officiële afkorting van het dienstregelpunt conform de NS-dienstregeling. '
'Voorbeeldwaarde: Asd (Amsterdam Centraal), Rtd (Rotterdam Centraal).';
COMMENT ON COLUMN dimdienstregelpunt.dienstregelpunt_naam IS
'Volledige naam van het dienstregelpunt. Voorbeeldwaarde: Amsterdam Centraal.';
COMMENT ON COLUMN dimdienstregelpunt.regio_rsv_naam IS
'Naam van de RSV-regio waaronder het dienstregelpunt valt. Voorbeeldwaarde: Zuid, '
'Randstad-Noord, Randstad-Zuid, en Noord-Oost.';
COMMENT ON COLUMN dimdienstregelpunt.regio_ssvo_naam IS
'Naam van de SSVO-regio waaronder het dienstregelpunt valt. Voorbeeldwaarde: '
'West-Brabant en Zeeland, Twente-IJsel, PE Noord.';
COMMENT ON COLUMN dimdienstregelpunt.ind_backup_vens IS
'Indicator of het dienstregelpunt een backup V&S-locatie is. Voorbeeldwaarde: 1 '
'voor backup locaties, 0 voor reguliere locaties.';
COMMENT ON COLUMN dimdienstregelpunt.ind_standplaats_vens IS
'Indicator of het dienstregelpunt een standplaats V&S-locatie is. Voorbeeldwaarde: 1 '
'voor standplaats locaties, 0 voor reguliere locaties.';
COMMENT ON COLUMN dimdienstregelpunt.geldig_vanaf IS
'Datum en tijd vanaf wanneer het dienstregelpunt geldig is. Voorbeeldwaarde: 2026-01-01 00:00:00';
COMMENT ON COLUMN dimdienstregelpunt.geldig_tm IS
'Datum en tijd tot wanneer het dienstregelpunt geldig is. Voor voorbeeldwaarde: '
'9999-12-31 23:59:59 voor huidige locaties.';
COMMENT ON COLUMN dimdienstregelpunt.ind_huidig IS
'Indicator of het dienstregelpunt momenteel in gebruik is. Voorbeeldwaarde: 1 '
'voor huidige locaties, 0 voor historische locaties.';
