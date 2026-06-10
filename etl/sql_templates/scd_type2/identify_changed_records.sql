-- ============================================================================
-- TEMPLATE: Identify Changed Records (SCD Type 2)
-- ============================================================================
-- Identifiziert Records deren Daten sich geändert haben (HASH-Vergleich)
-- Verwendet INNER JOIN + HASH-Vergleich: RECORD_HASH unterschiedlich → CHANGED
-- 
-- PARAMETER:
--   ${STAGING_TABLE}         : Staging-Tabelle (z.B. temp_taaa_person_staging)
--   ${TARGET_DATABASE}       : Target Database (z.B. MDP01_DISCOVERABLE_LAYER)
--   ${TARGET_TABLE}          : Target History-Tabelle (z.B. TAAA_PERSON_HISTORY)
--   ${BUSINESS_KEY_JOIN}     : JOIN-Bedingung (generiert)
--                              Single:    stg.PERSON_ID = hist.PERSON_ID
--                              Composite: stg.COL1 = hist.COL1 AND stg.COL2 = hist.COL2
--   ${PRIMARY_INDEX_COLS}    : PRIMARY INDEX Spalten (generiert), z.B. PERSON_ID oder COL1, COL2
--   ${HASH_EXPRESSION}       : HASHROW-Expression mit Spalten (generiert, mit TABLE_ALIAS)
--   ${CHANGED_RECORDS_TABLE} : Output-Tabelle für geänderte Records (z.B. temp_taaa_person_changed)
-- ============================================================================

CREATE MULTISET VOLATILE TABLE ${CHANGED_RECORDS_TABLE} AS (
    SELECT 
        stg.*,
        ${HASH_EXPRESSION} AS RECORD_HASH
    FROM ${STAGING_TABLE} stg
    INNER JOIN ${TARGET_DATABASE}.${TARGET_TABLE} hist
        ON ${BUSINESS_KEY_JOIN}
        AND hist.IS_CURRENT = 'Y'
    WHERE ${HASH_EXPRESSION} <> hist.RECORD_HASH
) WITH DATA
PRIMARY INDEX (${PRIMARY_INDEX_COLS})
ON COMMIT PRESERVE ROWS;
