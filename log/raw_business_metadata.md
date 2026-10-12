# RAW Fachmetadaten-Analyse

- Metadatenbank: `SEM_DEV_MET_BASE`
- Read-only: `True`
- Tabellenumfang: `10` fest definierte Tabellen
- Es werden keine Fachdaten, Beispielwerte oder Definitionstexte ausgegeben.

## Zusammenfassung

- Gefundene Tabellen: **10 / 10**
- Mit Area-Zuordnung: **0**
- Mit Business-Object-Zuordnung: **0**
- Mit logischem PK: **4**
- Mit Business Key: **10**
- Mit logischer FK-Referenz: **6**
- Mit dokumentiertem Index: **10**

## Ergebnisse

### `UZMS01_TAAA_IDENTITAET`
- Tabelle-ID: `92`, Typ: `T`, historisiert: `N `
- Area: `keine/nicht aufloesbar`
- Business Object: `keines/nicht aufloesbar`
- PK/BK/FK/PI: `0` / `1` / `0` / `0`
- Technische/Audit/SCD/PII-Spalten: `0` / `0` / `0` / `0`
- Business-Dokumentation Name/Definition/Kommentar: `0` / `0` / `0`
- FK-Referenzen: `0` (nicht aufloesbar: `0`), Indizes: `1`, ETL-Mappings: `0`
- Erkenntnisse:
  - Kein logischer PK in META_COLUMN markiert
  - Kein Primary Index in META_COLUMN markiert
  - Keine META_AREA-Zuordnung vorhanden
  - Keine META_BUSINESS_OBJECT-Zuordnung vorhanden
  - Keine fachliche Spaltendefinition dokumentiert
  - Keine logische FK-Referenz dokumentiert

### `UZMS01_TAAA_PERSON`
- Tabelle-ID: `86`, Typ: `T`, historisiert: `N `
- Area: `keine/nicht aufloesbar`
- Business Object: `keines/nicht aufloesbar`
- PK/BK/FK/PI: `0` / `1` / `0` / `0`
- Technische/Audit/SCD/PII-Spalten: `0` / `0` / `0` / `0`
- Business-Dokumentation Name/Definition/Kommentar: `0` / `0` / `0`
- FK-Referenzen: `0` (nicht aufloesbar: `0`), Indizes: `1`, ETL-Mappings: `0`
- Erkenntnisse:
  - Kein logischer PK in META_COLUMN markiert
  - Kein Primary Index in META_COLUMN markiert
  - Keine META_AREA-Zuordnung vorhanden
  - Keine META_BUSINESS_OBJECT-Zuordnung vorhanden
  - Keine fachliche Spaltendefinition dokumentiert
  - Keine logische FK-Referenz dokumentiert

### `UZMS01_TAAS_ERLEDIGUNG`
- Tabelle-ID: `48`, Typ: `T`, historisiert: `N `
- Area: `keine/nicht aufloesbar`
- Business Object: `keines/nicht aufloesbar`
- PK/BK/FK/PI: `1` / `1` / `0` / `1`
- Technische/Audit/SCD/PII-Spalten: `0` / `0` / `0` / `0`
- Business-Dokumentation Name/Definition/Kommentar: `0` / `0` / `0`
- FK-Referenzen: `2` (nicht aufloesbar: `0`), Indizes: `3`, ETL-Mappings: `0`
- Referenzen:
  - `UZMS01_TAAS_ERLEDIGUNG.GESCHAEFT_ID` -> `UZMS01_TAAS_GESCHAEFT.GESCHAEFT_ID` (Delete: `None`, Update: `None`)
  - `UZMS01_TAAS_ERLEDIG_ZUSATZ.ERLEDIGUNG_ID` -> `UZMS01_TAAS_ERLEDIGUNG.ERLEDIGUNG_ID` (Delete: `None`, Update: `None`)
- Erkenntnisse:
  - Keine META_AREA-Zuordnung vorhanden
  - Keine META_BUSINESS_OBJECT-Zuordnung vorhanden
  - Keine fachliche Spaltendefinition dokumentiert

### `UZMS01_TAAS_ERLEDIG_ZUSATZ`
- Tabelle-ID: `49`, Typ: `T`, historisiert: `N `
- Area: `keine/nicht aufloesbar`
- Business Object: `keines/nicht aufloesbar`
- PK/BK/FK/PI: `1` / `1` / `0` / `1`
- Technische/Audit/SCD/PII-Spalten: `0` / `0` / `0` / `0`
- Business-Dokumentation Name/Definition/Kommentar: `0` / `0` / `0`
- FK-Referenzen: `1` (nicht aufloesbar: `0`), Indizes: `3`, ETL-Mappings: `0`
- Referenzen:
  - `UZMS01_TAAS_ERLEDIG_ZUSATZ.ERLEDIGUNG_ID` -> `UZMS01_TAAS_ERLEDIGUNG.ERLEDIGUNG_ID` (Delete: `None`, Update: `None`)
- Erkenntnisse:
  - Keine META_AREA-Zuordnung vorhanden
  - Keine META_BUSINESS_OBJECT-Zuordnung vorhanden
  - Keine fachliche Spaltendefinition dokumentiert

### `UZMS01_TAAS_GESCHAEFT`
- Tabelle-ID: `50`, Typ: `T`, historisiert: `N `
- Area: `keine/nicht aufloesbar`
- Business Object: `keines/nicht aufloesbar`
- PK/BK/FK/PI: `1` / `1` / `0` / `1`
- Technische/Audit/SCD/PII-Spalten: `0` / `0` / `0` / `0`
- Business-Dokumentation Name/Definition/Kommentar: `0` / `0` / `0`
- FK-Referenzen: `3` (nicht aufloesbar: `2`), Indizes: `3`, ETL-Mappings: `0`
- Referenzen:
  - `UZMS01_TAAS_GESCHAEFT.VERFAHREN_ID` -> `UZMS01_TAAS_VERFAHREN.VERFAHREN_ID` (Delete: `None`, Update: `None`)
  - `UZMS01_TAAS_ERLEDIGUNG.GESCHAEFT_ID` -> `UZMS01_TAAS_GESCHAEFT.GESCHAEFT_ID` (Delete: `None`, Update: `None`)
  - `UZMS01_TAAS_GESCHAEFTSSCHRITT.GESCHAEFT_ID` -> `UZMS01_TAAS_GESCHAEFT.GESCHAEFT_ID` (Delete: `None`, Update: `None`)
- Erkenntnisse:
  - Keine META_AREA-Zuordnung vorhanden
  - Keine META_BUSINESS_OBJECT-Zuordnung vorhanden
  - Keine fachliche Spaltendefinition dokumentiert

### `UZMS01_TAAS_GESCHAEFTSSCHRITT`
- Tabelle-ID: `51`, Typ: `T`, historisiert: `N `
- Area: `keine/nicht aufloesbar`
- Business Object: `keines/nicht aufloesbar`
- PK/BK/FK/PI: `0` / `1` / `0` / `0`
- Technische/Audit/SCD/PII-Spalten: `0` / `0` / `0` / `0`
- Business-Dokumentation Name/Definition/Kommentar: `0` / `0` / `0`
- FK-Referenzen: `1` (nicht aufloesbar: `0`), Indizes: `3`, ETL-Mappings: `0`
- Referenzen:
  - `UZMS01_TAAS_GESCHAEFTSSCHRITT.GESCHAEFT_ID` -> `UZMS01_TAAS_GESCHAEFT.GESCHAEFT_ID` (Delete: `None`, Update: `None`)
- Erkenntnisse:
  - Kein logischer PK in META_COLUMN markiert
  - Kein Primary Index in META_COLUMN markiert
  - Keine META_AREA-Zuordnung vorhanden
  - Keine META_BUSINESS_OBJECT-Zuordnung vorhanden
  - Keine fachliche Spaltendefinition dokumentiert

### `UZMS01_TAAS_VERFAHREN`
- Tabelle-ID: `52`, Typ: `T`, historisiert: `N `
- Area: `keine/nicht aufloesbar`
- Business Object: `keines/nicht aufloesbar`
- PK/BK/FK/PI: `1` / `1` / `1` / `1`
- Technische/Audit/SCD/PII-Spalten: `0` / `0` / `0` / `0`
- Business-Dokumentation Name/Definition/Kommentar: `0` / `0` / `0`
- FK-Referenzen: `2` (nicht aufloesbar: `0`), Indizes: `3`, ETL-Mappings: `0`
- Referenzen:
  - `UZMS01_TAAS_GESCHAEFT.VERFAHREN_ID` -> `UZMS01_TAAS_VERFAHREN.VERFAHREN_ID` (Delete: `None`, Update: `None`)
  - `UZMS01_TAAS_VERFAHREN_BEM.VERFAHREN_ID` -> `UZMS01_TAAS_VERFAHREN.VERFAHREN_ID` (Delete: `None`, Update: `None`)
- Erkenntnisse:
  - Keine META_AREA-Zuordnung vorhanden
  - Keine META_BUSINESS_OBJECT-Zuordnung vorhanden
  - Keine fachliche Spaltendefinition dokumentiert

### `UZMS01_TAAS_VERFAHREN_BEM`
- Tabelle-ID: `53`, Typ: `T`, historisiert: `N `
- Area: `keine/nicht aufloesbar`
- Business Object: `keines/nicht aufloesbar`
- PK/BK/FK/PI: `0` / `1` / `0` / `0`
- Technische/Audit/SCD/PII-Spalten: `0` / `0` / `0` / `0`
- Business-Dokumentation Name/Definition/Kommentar: `0` / `0` / `0`
- FK-Referenzen: `1` (nicht aufloesbar: `0`), Indizes: `3`, ETL-Mappings: `0`
- Referenzen:
  - `UZMS01_TAAS_VERFAHREN_BEM.VERFAHREN_ID` -> `UZMS01_TAAS_VERFAHREN.VERFAHREN_ID` (Delete: `None`, Update: `None`)
- Erkenntnisse:
  - Kein logischer PK in META_COLUMN markiert
  - Kein Primary Index in META_COLUMN markiert
  - Keine META_AREA-Zuordnung vorhanden
  - Keine META_BUSINESS_OBJECT-Zuordnung vorhanden
  - Keine fachliche Spaltendefinition dokumentiert

### `UZMS01_TARF_ASYLGS_ART_TX`
- Tabelle-ID: `55`, Typ: `T`, historisiert: `N `
- Area: `keine/nicht aufloesbar`
- Business Object: `keines/nicht aufloesbar`
- PK/BK/FK/PI: `0` / `2` / `0` / `0`
- Technische/Audit/SCD/PII-Spalten: `0` / `0` / `0` / `0`
- Business-Dokumentation Name/Definition/Kommentar: `0` / `0` / `0`
- FK-Referenzen: `0` (nicht aufloesbar: `0`), Indizes: `1`, ETL-Mappings: `0`
- Erkenntnisse:
  - Kein logischer PK in META_COLUMN markiert
  - Kein Primary Index in META_COLUMN markiert
  - Keine META_AREA-Zuordnung vorhanden
  - Keine META_BUSINESS_OBJECT-Zuordnung vorhanden
  - Keine fachliche Spaltendefinition dokumentiert
  - Keine logische FK-Referenz dokumentiert

### `UZMS01_TARF_ASYL_ERLEDIG_TX`
- Tabelle-ID: `57`, Typ: `T`, historisiert: `N `
- Area: `keine/nicht aufloesbar`
- Business Object: `keines/nicht aufloesbar`
- PK/BK/FK/PI: `0` / `2` / `0` / `0`
- Technische/Audit/SCD/PII-Spalten: `0` / `0` / `0` / `0`
- Business-Dokumentation Name/Definition/Kommentar: `0` / `0` / `0`
- FK-Referenzen: `0` (nicht aufloesbar: `0`), Indizes: `1`, ETL-Mappings: `0`
- Erkenntnisse:
  - Kein logischer PK in META_COLUMN markiert
  - Kein Primary Index in META_COLUMN markiert
  - Keine META_AREA-Zuordnung vorhanden
  - Keine META_BUSINESS_OBJECT-Zuordnung vorhanden
  - Keine fachliche Spaltendefinition dokumentiert
  - Keine logische FK-Referenz dokumentiert

