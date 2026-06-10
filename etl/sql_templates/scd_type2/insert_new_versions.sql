-- ============================================================================
-- TEMPLATE: Insert New Versions (SCD Type 2)
-- ============================================================================
-- Fügt neue Versionen in History-Tabelle ein
-- Funktioniert für NEW und CHANGED Records (gleiche Logik)
-- 
-- PARAMETER:
--   ${TARGET_DATABASE}     : Target Database (z.B. MDP01_DISCOVERABLE_LAYER)
--   ${TARGET_TABLE}        : Target History-Tabelle (z.B. TAAA_PERSON_HISTORY)
--   ${NEW_RECORDS_TABLE}   : Temp-Tabelle mit Records (temp_new_records oder temp_changed_records)
--   ${INSERT_COLUMNS}      : Spalten-Liste für INSERT (generiert aus INSERT_COLUMNS)
--   ${SELECT_COLUMNS}      : SELECT-Liste mit Alias (generiert aus INSERT_COLUMNS + TABLE_ALIAS)
--   ${HASH_EXPRESSION}     : HASHROW-Expression (generiert aus HASH_COLUMNS)
-- ============================================================================

INSERT INTO ${TARGET_DATABASE}.${TARGET_TABLE}
(
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
FROM ${NEW_RECORDS_TABLE} src;
