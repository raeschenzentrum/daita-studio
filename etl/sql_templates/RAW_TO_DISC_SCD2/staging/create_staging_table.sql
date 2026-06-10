-- ============================================================================
-- TEMPLATE: Create Staging Table with Type Conversion
-- ============================================================================
-- Erstellt eine VOLATILE Staging-Tabelle aus RAW-Daten mit Type Conversion
-- 
-- PARAMETER:
--   ${SOURCE_DATABASE}     : Source Database (z.B. MDP01_RAW_LAYER)
--   ${SOURCE_TABLE}        : Source Table (z.B. TAAA_PERSON)
--   ${STAGING_TABLE}       : Name der Staging-Tabelle (z.B. temp_taaa_person_staging)
--   ${BUSINESS_KEY}        : Business Key Spalte (z.B. PERSON_ID)
--   ${SELECT_COLUMNS}      : SELECT-Liste mit Type Conversions (generiert)
-- ============================================================================

CREATE MULTISET VOLATILE TABLE ${STAGING_TABLE} AS (
    SELECT
        ${SELECT_COLUMNS}
    FROM ${SOURCE_DATABASE}.${SOURCE_TABLE}
) WITH DATA
PRIMARY INDEX (${BUSINESS_KEY})
ON COMMIT PRESERVE ROWS;
