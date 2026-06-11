# Template Parameter Reference – RAW_TO_DISC_SCD2

> Alle Parameter die in den SQL-Templates des `RAW_TO_DISC_SCD2` Prozesses verwendet werden.
> Parameter werden beim Job-Erstellen automatisch generiert (aus `META_COLUMN`, Config `cfg/parameter_rules.yml` und User-Input).
> Job-spezifische Werte liegen in `etl/jobs/{job_id}/{step_id}.json`.

---

## Übersicht nach Kategorie

| Kategorie | Parameter |
|-----------|-----------|
| **Quelle** | `SOURCE_DATABASE`, `SOURCE_TABLE` |
| **Ziel** | `TARGET_DATABASE`, `target_database`, `TARGET_TABLE`, `target_table` |
| **Surrogate Key** | `SK_COLUMN`, `KEY_DATABASE`, `KEY_TABLE`, `DOMAIN` |
| **Natural / Business Key** | `NATURAL_KEY_COL`, `NATURAL_KEY_EXPRESSION_SRC`, `NATURAL_KEY_EXPRESSION_STG`, `BUSINESS_KEY`, `BUSINESS_KEY_JOIN`, `BUSINESS_KEY_NULL_CHECK`, `BUSINESS_KEY_TGT_JOIN` |
| **Staging / Volatile Tables** | `STAGING_TABLE`, `NEW_RECORDS_TABLE`, `CHANGED_RECORDS_TABLE` |
| **Spalten** | `SELECT_COLUMNS`, `INSERT_COLUMNS`, `PRIMARY_INDEX_COLS` |
| **Hashing** | `HASH_EXPRESSION` |

---

## Parameter im Detail

### Quell-Parameter

#### `SOURCE_DATABASE`
- **Typ:** String
- **Beispiel:** `MDP01_RAW_LAYER`
- **Beschreibung:** Name der Quelldatenbank in Teradata. Wird aus `META_DATABASE` des Source-Layers ermittelt.
- **Verwendet in:** `create_staging_table.sql`

#### `SOURCE_TABLE`
- **Typ:** String
- **Beispiel:** `UZMS01_TAAA_PERSON`
- **Beschreibung:** Tabellenname der Quelltabelle (ohne Datenbankpräfix). Entspricht `META_TABLE.TABLE_NAME` des Source-Layers.
- **Verwendet in:** `create_staging_table.sql`

---

### Ziel-Parameter

#### `TARGET_DATABASE` / `target_database`
- **Typ:** String
- **Beispiel:** `MDP01_DISCOVERABLE_LAYER`
- **Beschreibung:** Name der Zieldatenbank. Wird aus Layer-Config (`cfg/parameter_rules.yml` → `layers.discoverable.database`) ermittelt. **Hinweis:** Einige ältere Templates verwenden Lowercase `target_database` — beide sind identisch.
- **Verwendet in:** `delete_target_table.sql`, `identify_new_records.sql`, `identify_changed_records.sql`, `close_old_versions.sql`, `insert_new_versions_with_sk.sql`, `calculate_statistics.sql`

#### `TARGET_TABLE` / `target_table`
- **Typ:** String
- **Beispiel:** `UZMS01_TAAA_PERSON`
- **Beschreibung:** Tabellenname der Zieltabelle (ohne Datenbankpräfix). Entspricht dem Zieldatensatz im DISC-Layer. **Hinweis:** Gleiche Konvention wie `TARGET_DATABASE` — Lowercase in älteren Templates.
- **Verwendet in:** `delete_target_table.sql`, `identify_new_records.sql`, `identify_changed_records.sql`, `close_old_versions.sql`, `insert_new_versions_with_sk.sql`, `calculate_statistics.sql`

---

### Surrogate Key Parameter

#### `SK_COLUMN`
- **Typ:** String
- **Beispiel:** `UZMS01_TAAA_PERSON_SK`
- **Beschreibung:** Name der Surrogate-Key-Spalte in der Zieltabelle. Wird nach Pattern `{CORE_NAME}_SK` generiert (aus `cfg/parameter_rules.yml` → `scd2_technical_columns.surrogate_key.pattern`).
- **Verwendet in:** `insert_new_versions_with_sk.sql`

#### `KEY_DATABASE`
- **Typ:** String
- **Beispiel:** `MDP01_DISCOVERABLE_LAYER`
- **Beschreibung:** Datenbank in der die Key-Lookup-Tabelle (`KEY_*`) liegt. Identisch mit `TARGET_DATABASE`. Aus Layer-Config.
- **Verwendet in:** `generate_surrogate_keys_from_staging.sql`, `insert_new_versions_with_sk.sql`

#### `KEY_TABLE`
- **Typ:** String
- **Beispiel:** `KEY_UZMS01_TAAA_PERSON`
- **Beschreibung:** Name der Surrogate-Key-Lookup-Tabelle. Format: `KEY_` + `{CORE_NAME}` (aus Config `layers.discoverable.key_prefix`). Wird beim Job-Erstellen automatisch angelegt falls nicht vorhanden.
- **Verwendet in:** `generate_surrogate_keys_from_staging.sql`, `insert_new_versions_with_sk.sql`

#### `DOMAIN`
- **Typ:** String
- **Beispiel:** `UZMS01_TAAA_PERSON`
- **Beschreibung:** Domain-Identifier für den Natural-Key-Eintrag in der Key-Tabelle (`KEY_*.NATURAL_KEY_DOMAIN`). Entspricht i.d.R. dem Tabellennamen der Quelle. Verhindert Kollisionen wenn mehrere Entitäten dieselbe Key-Tabelle teilen.
- **Verwendet in:** `generate_surrogate_keys_from_staging.sql`, `insert_new_versions_with_sk.sql`

---

### Natural Key / Business Key Parameter

#### `NATURAL_KEY_COL`
- **Typ:** String (einzelne Spalte)
- **Beispiel:** `PERSON_ID`
- **Beschreibung:** Name der **ersten** Primary-Key-Spalte der Quelltabelle (aus `META_COLUMN` mit `IS_BUSINESS_KEY = 'Y'`). Wird für NOT-NULL-Checks verwendet. Bei zusammengesetzten PKs: nur die erste Spalte.
- **Verwendet in:** `generate_surrogate_keys_from_staging.sql`, `insert_new_versions_with_sk.sql`

#### `NATURAL_KEY_EXPRESSION_STG`
- **Typ:** SQL-Ausdruck (generiert)
- **Beispiel (einfach):** `CAST(stg.PERSON_ID AS VARCHAR(255))`
- **Beispiel (zusammengesetzt):** `TRIM(CAST(stg.COL1 AS VARCHAR(100))) || '~|~' || TRIM(CAST(stg.COL2 AS VARCHAR(100)))`
- **Beschreibung:** SQL-Ausdruck der den Natural Key aus der **Staging-Tabelle** (`stg`-Alias) als einzelnen VARCHAR-Wert zusammensetzt. Bei zusammengesetzten PKs werden die Teile mit Separator `~|~` verbunden (aus Config `composite_key.separator`).
- **Verwendet in:** `generate_surrogate_keys_from_staging.sql`

#### `NATURAL_KEY_EXPRESSION_SRC`
- **Typ:** SQL-Ausdruck (generiert)
- **Beispiel (einfach):** `CAST(src.PERSON_ID AS VARCHAR(255))`
- **Beispiel (zusammengesetzt):** `TRIM(CAST(src.COL1 AS VARCHAR(100))) || '~|~' || TRIM(CAST(src.COL2 AS VARCHAR(100)))`
- **Beschreibung:** Identisch zu `NATURAL_KEY_EXPRESSION_STG`, aber mit `src`-Alias. Wird beim INSERT in die Zieltabelle für den SK-Lookup verwendet.
- **Verwendet in:** `insert_new_versions_with_sk.sql`

#### `BUSINESS_KEY`
- **Typ:** String (kommagetrennt bei mehreren Spalten)
- **Beispiel:** `PERSON_ID` oder `COL1, COL2`
- **Beschreibung:** Kommagetrennte Liste aller Business-Key-Spalten (aus `META_COLUMN` mit `IS_BUSINESS_KEY = 'Y'`). Wird als `PRIMARY INDEX` der Staging-Tabelle verwendet.
- **Verwendet in:** `create_staging_table.sql`

#### `BUSINESS_KEY_JOIN`
- **Typ:** SQL-Ausdruck (generiert)
- **Beispiel (einfach):** `stg.PERSON_ID = hist.PERSON_ID`
- **Beispiel (zusammengesetzt):** `stg.COL1 = hist.COL1 AND stg.COL2 = hist.COL2`
- **Beschreibung:** JOIN-Bedingung zwischen Staging (`stg`) und History-Tabelle (`hist`) über alle Business-Key-Spalten. Wird für `identify_new_records` und `identify_changed_records` verwendet.
- **Verwendet in:** `identify_new_records.sql`, `identify_changed_records.sql`

#### `BUSINESS_KEY_NULL_CHECK`
- **Typ:** SQL-Ausdruck (generiert)
- **Beispiel:** `hist.PERSON_ID IS NULL`
- **Beschreibung:** WHERE-Bedingung die prüft ob ein Record neu ist (kein Match im LEFT JOIN → History-Spalte ist NULL). Verwendet die erste Business-Key-Spalte der History-Tabelle.
- **Verwendet in:** `identify_new_records.sql`

#### `BUSINESS_KEY_TGT_JOIN`
- **Typ:** SQL-Ausdruck (generiert)
- **Beispiel:** `MDP01_DISCOVERABLE_LAYER.UZMS01_TAAA_PERSON.PERSON_ID = chg.PERSON_ID`
- **Beschreibung:** Vollqualifizierter JOIN zwischen Zieltabelle und der Tabelle der geänderten Records (`chg`). Wird beim Schließen alter Versionen (SCD2 UPDATE via DELETE+INSERT) verwendet.
- **Verwendet in:** `close_old_versions.sql`

---

### Staging / Volatile Table Parameter

#### `STAGING_TABLE`
- **Typ:** String
- **Beispiel:** `temp_uzms01_taaa_person_staging`
- **Beschreibung:** Name der VOLATILE Staging-Tabelle die in `create_staging_table.sql` erstellt wird und in den Folge-Steps weiterverwendet wird. Format: `temp_{source_table_lower}_staging` (aus Config `staging.prefix` + `staging.suffix`).
- **Verwendet in:** `create_staging_table.sql`, `generate_surrogate_keys_from_staging.sql`, `identify_new_records.sql`, `identify_changed_records.sql`

#### `NEW_RECORDS_TABLE`
- **Typ:** String
- **Beispiel:** `temp_uzms01_taaa_person_new`
- **Beschreibung:** Name der VOLATILE Tabelle für neu identifizierte Records (keine Entsprechung in History). Wird in `identify_new_records.sql` erstellt, in `insert_new_versions_with_sk.sql` gelesen. Format: `temp_{source_table_lower}_new`.
- **Verwendet in:** `identify_new_records.sql`, `insert_new_versions_with_sk.sql`

#### `CHANGED_RECORDS_TABLE`
- **Typ:** String
- **Beispiel:** `temp_uzms01_taaa_person_changed`
- **Beschreibung:** Name der VOLATILE Tabelle für geänderte Records (Business Key match, aber RECORD_HASH unterschiedlich). Wird in `identify_changed_records.sql` erstellt, in `close_old_versions.sql` und `insert_new_versions_with_sk.sql` gelesen. Format: `temp_{source_table_lower}_changed`.
- **Verwendet in:** `identify_changed_records.sql`, `close_old_versions.sql`, `insert_new_versions_with_sk.sql`

---

### Spalten-Parameter

#### `SELECT_COLUMNS`
- **Typ:** String (kommagetrennte Spaltenliste)
- **Beispiel:** `PERSON_ID, ZEMIS_NR, EV_STATUS, CTL_CRE_DAT`
- **Beschreibung:** Liste aller zu ladenden Spalten aus der Quelltabelle. Wird aus `META_COLUMN` generiert (alle Spalten der Source-Tabelle). Verwendet als SELECT-Liste in der Staging-Tabelle und beim INSERT in die Zieltabelle.
- **Verwendet in:** `create_staging_table.sql`, `insert_new_versions_with_sk.sql`

#### `INSERT_COLUMNS`
- **Typ:** String (kommagetrennte Spaltenliste)
- **Beschreibung:** Spalten-Liste für den INSERT in die Zieltabelle. Entspricht i.d.R. `SELECT_COLUMNS`. Explizit aufgeführt um die INSERT-Zielspalten klar zu definieren (ohne SK und SCD2-Technische-Spalten die separat aufgeführt werden).
- **Verwendet in:** `insert_new_versions_with_sk.sql`

#### `PRIMARY_INDEX_COLS`
- **Typ:** String (kommagetrennt bei mehreren Spalten)
- **Beispiel:** `PERSON_ID`
- **Beschreibung:** PRIMARY INDEX Spalten für die VOLATILE Tabellen der neuen und geänderten Records. Entspricht dem Business Key. Identisch mit `BUSINESS_KEY`.
- **Verwendet in:** `identify_new_records.sql`, `identify_changed_records.sql`

---

### Hash-Parameter

#### `HASH_EXPRESSION`
- **Typ:** SQL-Ausdruck (generiert)
- **Beispiel:** `HASHROW(stg.PERSON_ID, stg.ZEMIS_NR, stg.EV_STATUS)`
- **Beschreibung:** Teradata `HASHROW()`-Ausdruck über alle Hash-Spalten (`HASH_COLUMNS` aus Job-Konfiguration, Default: alle Source-Spalten). Wird als `RECORD_HASH` in der Zieltabelle gespeichert und für den Änderungs-Vergleich (SCD2) verwendet. Enthält Tabellen-Alias (`stg.` oder `src.`).
- **Verwendet in:** `identify_changed_records.sql`, `insert_new_versions_with_sk.sql`

---

## Zusammenhang: Parameter-Generierung beim Job-Erstellen

```
User-Input (Wizard)
    │
    ▼
create_job_from_template()
    ├── SOURCE_TABLE / SOURCE_DATABASE   ← aus META_TABLE + META_DATABASE (source_table_id)
    ├── TARGET_TABLE / TARGET_DATABASE   ← aus User-Input oder generiert
    ├── BUSINESS_KEY / NATURAL_KEY_COL   ← aus META_COLUMN (IS_BUSINESS_KEY = 'Y')
    ├── SELECT_COLUMNS / INSERT_COLUMNS  ← aus META_COLUMN (alle Spalten)
    ├── HASH_COLUMNS / HASH_EXPRESSION   ← aus META_COLUMN (alle Spalten)
    ├── STAGING_TABLE                    ← generiert: temp_{source_lower}_staging
    ├── NEW_RECORDS_TABLE                ← generiert: temp_{source_lower}_new
    ├── CHANGED_RECORDS_TABLE            ← generiert: temp_{source_lower}_changed
    ├── KEY_TABLE / KEY_DATABASE         ← aus Layer-Config (key_prefix + CORE_NAME)
    ├── DOMAIN                           ← = SOURCE_TABLE
    ├── SK_COLUMN                        ← generiert: {CORE_NAME}_SK
    ├── NATURAL_KEY_EXPRESSION_*         ← generiert aus BUSINESS_KEY (CAST + Concat)
    ├── BUSINESS_KEY_JOIN                ← generiert aus BUSINESS_KEY (stg.X = hist.X AND ...)
    ├── BUSINESS_KEY_NULL_CHECK          ← generiert: hist.{erste_PK_Spalte} IS NULL
    └── BUSINESS_KEY_TGT_JOIN            ← generiert: {TARGET_DATABASE}.{TARGET_TABLE}.X = chg.X
```

Gespeichert in: `etl/jobs/{job_id}/{step_id}.json`

---

## Konfiguration: `cfg/parameter_rules.yml`

Die generierten Parameter-Werte (Prefixe, Suffixe, Muster) sind konfigurierbar:

| Config-Key | Steuert | Standard |
|------------|---------|---------|
| `staging.prefix` | Prefix für VOLATILE Tabellen | `temp_` |
| `staging.suffix` | Suffix für Staging-Tabelle | `_staging` |
| `composite_key.separator` | Trennzeichen bei zusammengesetzten PKs | `~\|~` |
| `composite_key.max_col_length` | Max. Zeichenlänge je PK-Teil im CAST | `100` |
| `layers.discoverable.database` | Name der DISC-Datenbank | `MDP01_DISCOVERABLE_LAYER` |
| `layers.discoverable.key_prefix` | Prefix für KEY_*-Tabellen | `KEY_` |
| `scd2_technical_columns.surrogate_key.pattern` | Muster für SK-Spaltenname | `{core_name}_SK` |
