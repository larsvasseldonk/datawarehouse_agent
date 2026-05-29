CREATE TABLE IF NOT EXISTS factincidentmkns (
    dimdatumkey DECIMAL(38, 0) NOT NULL,
    dimdienstregelpuntkey DECIMAL(38, 0) NOT NULL,
    dimdienstregelpuntkey_van DECIMAL(38, 0),
    dimdienstregelpuntkey_naar DECIMAL(38, 0),
    dimdienstregelpuntkey_station DECIMAL(38, 0),
    dimlocatietypekey DECIMAL(38, 0) NOT NULL,
    dimmeldingsoortkey DECIMAL(38, 0) NOT NULL,
    dimtijdkey DECIMAL(38, 0) NOT NULL,
    dimtreinnummer_treinseriekey DECIMAL(38, 0),
    aantal_incident DECIMAL(38, 0) NOT NULL,
    ind_agressie INTEGER NOT NULL,
    ind_letsel INTEGER NOT NULL,
    incident_nr DECIMAL(38, 0) NOT NULL,
    opmerking VARCHAR NOT NULL,
    loaddate_utc TIMESTAMP NOT NULL,
    CONSTRAINT pk_factincidentmkns PRIMARY KEY (incident_nr),
    CONSTRAINT fk_factincidentmkns_dimdatum FOREIGN KEY (dimdatumkey)
    REFERENCES dimdatum (dimdatumkey),
    CONSTRAINT fk_factincidentmkns_dimdienstregelpunt FOREIGN KEY (dimdienstregelpuntkey)
    REFERENCES dimdienstregelpunt (dimdienstregelpuntkey),
    CONSTRAINT fk_factincidentmkns_dimdienstregelpunt_van FOREIGN KEY (dimdienstregelpuntkey_van)
    REFERENCES dimdienstregelpunt (dimdienstregelpuntkey),
    CONSTRAINT fk_factincidentmkns_dimdienstregelpunt_naar FOREIGN KEY (dimdienstregelpuntkey_naar)
    REFERENCES dimdienstregelpunt (dimdienstregelpuntkey),
    CONSTRAINT fk_factincidentmkns_dimdienstregelpunt_station FOREIGN KEY (dimdienstregelpuntkey_station)
    REFERENCES dimdienstregelpunt (dimdienstregelpuntkey),
    CONSTRAINT fk_factincidentmkns_dimlocatietype FOREIGN KEY (dimlocatietypekey)
    REFERENCES dimlocatietype (dimlocatietypekey),
    CONSTRAINT fk_factincidentmkns_dimmeldingssoort FOREIGN KEY (dimmeldingsoortkey)
    REFERENCES dimmeldingssoort (dimmeldingsoortkey),
    CONSTRAINT fk_factincidentmkns_dimtijd FOREIGN KEY (dimtijdkey)
    REFERENCES dimtijd (dimtijdkey),
    CONSTRAINT fk_factincidentmkns_dimtreinnummer_treinserie FOREIGN KEY (dimtreinnummer_treinseriekey)
    REFERENCES dimtreinnummer_treinserie (dimtreinnummer_treinseriekey)
);

COMMENT ON TABLE factincidentmkns IS
'Facttabel met alle door de Meldkamer NS afgehandelde incidenten die betrekking hebben op de '
'sociale veiligheid in de publieke ruimtes van NS of ProRail. Granulariteit: een rij per incident. '
'Businessnaam: incident. Alias: meldkaart.';

COMMENT ON COLUMN factincidentmkns.dimdatumkey IS
'Kalenderdatum waarop de eerste melding van het incident is geopend. Referentie: dimdatum.';
COMMENT ON COLUMN factincidentmkns.dimdienstregelpuntkey IS
'Kunstmatige kolom om incidenten eenduidig in een regio te kunnen rapporteren. Referentie: '
'dimdienstregelpunt. Incidenten op een station worden op dat station gerapporteerd; incidenten '
'op de trein op het eerstvolgende station waar de trein stopt.';
COMMENT ON COLUMN factincidentmkns.dimdienstregelpuntkey_van IS
'Startpunt van het traject waarop het incident heeft plaatsgevonden. Referentie: dimdienstregelpunt. '
'Voorbeeldwaarde: -3 wanneer locatietype <> trein.';
COMMENT ON COLUMN factincidentmkns.dimdienstregelpuntkey_naar IS
'Eindpunt van het traject waarop het incident heeft plaatsgevonden. Referentie: dimdienstregelpunt. '
'Voorbeeldwaarde: -3 wanneer locatietype <> trein.';
COMMENT ON COLUMN factincidentmkns.dimdienstregelpuntkey_station IS
'Station waarop het incident heeft plaatsgevonden. Referentie: dimdienstregelpunt. '
'Voorbeeldwaarde: -3 wanneer locatietype <> station.';
COMMENT ON COLUMN factincidentmkns.dimlocatietypekey IS
'Locatietype waar het incident heeft plaatsgevonden. Referentie: dimlocatietype.';
COMMENT ON COLUMN factincidentmkns.dimmeldingsoortkey IS
'Categorisering van de melding in ABC-categorie, hoofdsoort en soort. Referentie: dimmeldingssoort. '
'ABC-categorie is conform landelijke OV-afspraken.';
COMMENT ON COLUMN factincidentmkns.dimtijdkey IS
'Tijdstip waarop het incident heeft plaatsgevonden, in lokale tijd. Referentie: dimtijd.';
COMMENT ON COLUMN factincidentmkns.dimtreinnummer_treinseriekey IS
'Trein waarop het incident heeft plaatsgevonden. Referentie: dimtreinnummer_treinserie. '
'Voorbeeldwaarde: -3 wanneer locatiesoort <> trein.';
COMMENT ON COLUMN factincidentmkns.aantal_incident IS
'Telling van het aantal door de meldkamer geregistreerde sociale veiligheidsincidenten. '
'Voorbeeldwaarde: 1. Is altijd 1.';
COMMENT ON COLUMN factincidentmkns.ind_agressie IS
'Indicator of er sprake is van agressie. Voorbeeldwaarden: 0 of 1.';
COMMENT ON COLUMN factincidentmkns.ind_letsel IS
'Indicator of een medewerker letsel heeft opgelopen bij het incident. Voorbeeldwaarden: 0 of 1. '
'Het gaat alleen om letsel door directe agressie tegen de medewerker of letsel als gevolg van '
'toegepast geweld of dwangmiddelen door de medewerker.';
COMMENT ON COLUMN factincidentmkns.incident_nr IS
'Uniek nummer van het incident.';
COMMENT ON COLUMN factincidentmkns.opmerking IS
'Chronologische tekstuele beschrijving van het verloop van het incident zoals geregistreerd en '
'bijgewerkt door de centralist. Wordt voornamelijk gebruikt door MT SV en RSV om inzicht te krijgen '
'in individuele incidenten.';
COMMENT ON COLUMN factincidentmkns.loaddate_utc IS
'Technische kolom met de datum en tijd waarop de gegevens zijn geladen in het datawarehouse.';
