-- ============================================================================
-- TEMPLATE: Insert New Versions with Surrogate Key Lookup (SCD Type 2)
-- ============================================================================
-- Fügt neue Versionen in History-Tabelle ein MIT Surrogate Key aus KEY-Tabelle
-- 
-- Jaffle Pattern: SK wird zur Laufzeit per JOIN aus KEY_* Tabelle geholt.
-- Dies ermöglicht:
--   - Zentrale SK-Verwaltung (eine Quelle der Wahrheit)
--   - Keine SK-Spalte in RAW/Staging nötig
--   - Einfache Erweiterung auf weitere Entitäten
--
-- PARAMETER:
--   ${TARGET_DATABASE}     : Target Database (z.B. MDP01_DISCOVERABLE_LAYER)
--   ${TARGET_TABLE}        : Target History-Tabelle (z.B. TAAA_PERSON_HISTORY)
--   ${NEW_RECORDS_TABLE}   : Temp-Tabelle mit Records (temp_new_records / temp_changed_records)
--   ${INSERT_COLUMNS}      : Spalten-Liste für INSERT (generiert)
--   ${SELECT_COLUMNS}      : SELECT-Liste mit Alias 'src.' (generiert)
--   ${HASH_EXPRESSION}     : HASHROW-Expression (generiert)
--   ${KEY_DATABASE}        : Key-Datenbank (z.B. MDP01_META)
--   ${KEY_TABLE}           : Key-Tabelle (z.B. KEY_PERSON)
--   ${NATURAL_KEY_COL}     : Erste PK-Spalte (rückwärtskompatibel)
--   ${NATURAL_KEY_EXPRESSION_SRC} : SQL-Ausdruck für Natural Key Lookup (generiert)
--                             Single:    CAST(src.PERSON_ID AS VARCHAR(255))
--                             Composite: TRIM(CAST(src.COL1 AS VARCHAR(100))) || '~|~' || TRIM(CAST(src.COL2 AS VARCHAR(100)))
--   ${DOMAIN}              : Domain für KEY-Lookup (z.B. ZEMIS)
--   ${SK_COLUMN}           : Name der SK-Spalte in Ziel (z.B. PERSON_SK)
-- ============================================================================

INSERT INTO ${TARGET_DATABASE}.${TARGET_TABLE}
(
    -- Surrogate Key (aus KEY-Tabelle, NICHT aus Quelle!)
    ${SK_COLUMN},
    
    -- Business Columns
    ${INSERT_COLUMNS},
    
    -- SCD Type 2 Fields
    VALID_FROM,
    VALID_TO,
    IS_CURRENT,
    
    -- DWH Technical Fields
    RECORD_HASH,
    CREATED_TIMESTAMP,
    LAST_UPDATED_TIMESTAMP,
    CREATED_BY,
    LAST_UPDATED_BY
)
SELECT
    -- SK aus KEY-Tabelle per JOIN (COALESCE auf -1 falls nicht gefunden)
    COALESCE(k.SURROGATE_KEY, -1) AS ${SK_COLUMN},
    
    -- Business Columns
    ${SELECT_COLUMNS},
    
    -- SCD Type 2 Fields
    CURRENT_TIMESTAMP(6) AS VALID_FROM,
    TIMESTAMP '9999-12-31 23:59:59.999999' AS VALID_TO,
    'Y' AS IS_CURRENT,
    
    -- DWH Technical Fields
    ${HASH_EXPRESSION} AS RECORD_HASH,
    CURRENT_TIMESTAMP(6) AS CREATED_TIMESTAMP,
    CURRENT_TIMESTAMP(6) AS LAST_UPDATED_TIMESTAMP,
    USER AS CREATED_BY,
    USER AS LAST_UPDATED_BY

FROM ${NEW_RECORDS_TABLE} src

-- JOIN auf KEY-Tabelle um Surrogate Key zu holen
LEFT JOIN ${KEY_DATABASE}.${KEY_TABLE} k
    ON ${NATURAL_KEY_EXPRESSION_SRC} = k.NATURAL_KEY_VALUE
   AND k.NATURAL_KEY_DOMAIN = '${DOMAIN}';

-- Hinweis: LEFT JOIN + COALESCE(-1) statt INNER JOIN, damit Records
-- auch ohne Key geladen werden (mit Default-SK -1/UNKNOWN).
-- Dies verhindert Datenverlust bei fehlender Key-Generierung.
