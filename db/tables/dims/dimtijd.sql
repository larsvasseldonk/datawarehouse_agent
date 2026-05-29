CREATE TABLE IF NOT EXISTS dimtijd (
    dimtijdkey DECIMAL(38, 0) NOT NULL,
    tijd VARCHAR(50) NOT NULL,
    dagdeel VARCHAR(32) NOT NULL,
    halfuurblok VARCHAR(32) NOT NULL,
    uurblok VARCHAR(32) NOT NULL,
    tweeuurblok VARCHAR(32) NOT NULL,
    ind_avondspits INTEGER NOT NULL,
    ind_ochtendspits INTEGER NOT NULL,
    ind_spits INTEGER NOT NULL,
    CONSTRAINT pk_dimtijd PRIMARY KEY (dimtijdkey)
);

COMMENT ON TABLE dimtijd IS
'Tijddimensie met uurblokken, dagdelen en piekuurindicators voor verkeers- en logistieke analyses.';

COMMENT ON COLUMN dimtijd.dimtijdkey IS
'Surrogaatsleutel van het moment in formaat UUMMSS. Voorbeeldwaarde: 143000';
COMMENT ON COLUMN dimtijd.tijd IS
'Tijdstip in formaat UU:MM:SS. Voorbeeldwaarde: 14:30:00';
COMMENT ON COLUMN dimtijd.dagdeel IS
'Dagdeel classificatie: Dag (07:00-18:00) of Avond (18:00-07:00). Voorbeeldwaarde: Dag';
COMMENT ON COLUMN dimtijd.halfuurblok IS
'Halfuurs blok waar het moment in valt. Voorbeeldwaarde: 14:30-15:00';
COMMENT ON COLUMN dimtijd.uurblok IS
'Uurblok waar het moment in valt. Voorbeeldwaarde: 14:00-15:00';
COMMENT ON COLUMN dimtijd.tweeuurblok IS
'Twee-uurblok waar het moment in valt. Voorbeeldwaarde: 14:00-16:00';
COMMENT ON COLUMN dimtijd.ind_avondspits IS
'Indicator avondspits (16:00-19:00). Voorbeeldwaarde: 1';
COMMENT ON COLUMN dimtijd.ind_ochtendspits IS
'Indicator ochtendspits (07:00-09:00). Voorbeeldwaarde: 1';
COMMENT ON COLUMN dimtijd.ind_spits IS
'Indicator piekuur (07:00-09:00 of 16:00-19:00). Voorbeeldwaarde: 1';
