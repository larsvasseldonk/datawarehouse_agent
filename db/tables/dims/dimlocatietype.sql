CREATE TABLE IF NOT EXISTS dimlocatietype (
    dimlocatietypekey DECIMAL(38, 0) NOT NULL,
    locatietype_code DECIMAL(38, 0) NOT NULL,
    locatietype VARCHAR(255) NOT NULL,
    geldig_vanaf TIMESTAMP NOT NULL,
    geldig_tm TIMESTAMP NOT NULL,
    ind_huidig INTEGER NOT NULL,
    CONSTRAINT pk_dimlocatietype PRIMARY KEY (dimlocatietypekey)
);

COMMENT ON TABLE dimlocatietype IS
'Dimensietabel met de type locaties waarop een incident kan plaatsvinden binnen het NS-domein.';

COMMENT ON COLUMN dimlocatietype.dimlocatietypekey IS
'Surrogaatsleutel van de locatietype. Dit is een sha256 hash van de velden locatietype en geldig_vanaf. '
'Voorbeeldwaarde: 132321.';
COMMENT ON COLUMN dimlocatietype.locatietype_code IS
'Code van de locatietype. Voorbeeldwaarde: 1 voor station, 2 voor trein.';
COMMENT ON COLUMN dimlocatietype.locatietype IS
'Korte naam van de locatietype. Voorbeeldwaarden: Station, Trein.';
COMMENT ON COLUMN dimlocatietype.geldig_vanaf IS
'Datum en tijd vanaf wanneer de locatietype geldig is. Voorbeeldwaarde: 2026-01-01 00:00:00';
COMMENT ON COLUMN dimlocatietype.geldig_tm IS
'Datum en tijd tot wanneer de locatietype geldig is. Voor voorbeeldwaarde: 9999-12-31 23:59:59 '
'voor huidige locatietypes.';
COMMENT ON COLUMN dimlocatietype.ind_huidig IS
'Indicator of de locatietype momenteel in gebruik is. Voorbeeldwaarde: 1 voor huidige locatietypes, '
'0 voor historische locatietypes.';
