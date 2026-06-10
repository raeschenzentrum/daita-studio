-- ============================================================================
-- TEMPLATE: Identify New Records (SCD Type 2)
-- ============================================================================
-- Identifiziert Records die noch NICHT in der History-Tabelle existieren
-- Verwendet LEFT JOIN: Wenn History NULL → Record ist NEU
-- 
-- PARAMETER:
--   ${STAGING_TABLE}       : Staging-Tabelle (z.B. temp_taaa_person_staging)
--   ${TARGET_DATABASE}     : Target Database (z.B. MDP01_DISCOVERABLE_LAYER)
--   ${TARGET_TABLE}        : Target History-Tabelle (z.B. TAAA_PERSON_HISTORY)
--   ${BUSINESS_KEY_JOIN}   : JOIN-Bedingung (generiert)
--                            Single:    stg.PERSON_ID = hist.PERSON_ID
--                            Composite: stg.COL1 = hist.COL1 AND stg.COL2 = hist.COL2
--   ${BUSINESS_KEY_NULL_CHECK} : NULL-Check für neue Records (generiert, erste PK-Spalte)
--                            Bsp: hist.PERSON_ID IS NULL
--   ${PRIMARY_INDEX_COLS}  : PRIMARY INDEX Spalten (generiert), z.B. PERSON_ID oder COL1, COL2
--   ${NEW_RECORDS_TABLE}   : Output-Tabelle für neue Records (z.B. temp_taaa_person_new)
-- ============================================================================

CREATE MULTISET VOLATILE TABLE ${NEW_RECORDS_TABLE} AS (
    SELECT stg.*
    FROM ${STAGING_TABLE} stg
    LEFT JOIN ${TARGET_DATABASE}.${TARGET_TABLE} hist
        ON ${BUSINESS_KEY_JOIN}
        AND hist.IS_CURRENT = 'Y'
    WHERE ${BUSINESS_KEY_NULL_CHECK}
) WITH DATA
PRIMARY INDEX (${PRIMARY_INDEX_COLS})
ON COMMIT PRESERVE ROWS;
