CREATE TABLE IF NOT EXISTS dimtreinnummer_treinserie (
    dimtreinnummer_treinseriekey DECIMAL(38, 0) NOT NULL,
    treinnummer VARCHAR(10) NOT NULL,
    treinserie VARCHAR(10) NOT NULL,
    treintype VARCHAR(255) NOT NULL,
    geldig_vanaf TIMESTAMP NOT NULL,
    geldig_tm TIMESTAMP NOT NULL,
    ind_huidig INTEGER NOT NULL,
    CONSTRAINT pk_dimtreinnummer_treinserie PRIMARY KEY (dimtreinnummer_treinseriekey)
);

COMMENT ON TABLE dimtreinnummer_treinserie IS
'Dimensietabel met de combinatie van treinnummer en treinserie zoals geregistreerd op het '
'moment van het incident. Wordt gebruikt om incidenten te analyseren per trein en lijn. '
'Speciale waarde -3 voor de surrogaatsleutel als het incident niet op een trein plaatsvond.';

COMMENT ON COLUMN dimtreinnummer_treinserie.dimtreinnummer_treinseriekey IS
'Surrogaatsleutel van de treinnummer-treinserie combinatie. Dit is een sha256 hash van de velden '
'treinnummer, treinserie en geldig_vanaf. Voorbeeldwaarde: 567.';
COMMENT ON COLUMN dimtreinnummer_treinserie.treinnummer IS
'Treinnummer waarop het incident heeft plaatsgevonden. Voorbeeldwaarde: 3742.';
COMMENT ON COLUMN dimtreinnummer_treinserie.treinserie IS
'Treinserie (lijn) waarop het incident heeft plaatsgevonden. Voorbeeldwaarden: 2400, 4300, 4900.';
COMMENT ON COLUMN dimtreinnummer_treinserie.treintype IS
'Type van de trein. Voorbeeldwaarde: Intercity of Sprinter.';
COMMENT ON COLUMN dimtreinnummer_treinserie.geldig_vanaf IS
'Datum en tijd vanaf wanneer de treinnummer-treinserie combinatie geldig is. Voorbeeldwaarde: 2026-01-01 00:00:00';
COMMENT ON COLUMN dimtreinnummer_treinserie.geldig_tm IS
'Datum en tijd tot wanneer de treinnummer-treinserie combinatie geldig is. Voorbeeldwaarde: '
'9999-12-31 23:59:59 voor huidige combinaties.';
COMMENT ON COLUMN dimtreinnummer_treinserie.ind_huidig IS
'Indicator of de treinnummer-treinserie combinatie momenteel in gebruik is. Voorbeeldwaarde: 1 '
'voor huidige combinaties, 0 voor historische combinaties.';
