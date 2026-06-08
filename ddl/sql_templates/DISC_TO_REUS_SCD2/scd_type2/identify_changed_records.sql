-- ============================================================================
-- TEMPLATE: Identify Changed Records (SCD Type 2) — DISC TO REUS
-- ============================================================================
-- Identifiziert Records deren HASHROW sich gegenüber dem aktuellen REUS-Satz
-- geändert hat.
--
-- UNTERSCHIED zu RAW→DISC: IS_CURRENT='Y' → ${IST_AKTUELL_COL}='${IST_AKTUELL_VAL}'
--
-- PARAMETER:
--   ${STAGING_TABLE}         : Staging-Tabelle       (z.B. temp_part_person_staging)
--   ${TARGET_DATABASE}       : REUS-Datenbank         (z.B. MDP01_REUSABLE_LAYER)
--   ${TARGET_TABLE}          : REUS-Zieltabelle       (z.B. PART_PERSON)
--   ${BUSINESS_KEY_JOIN}     : JOIN-Bedingung         (z.B. stg.PERSON_ID = hist.PERSON_ID)
--   ${PRIMARY_INDEX_COLS}    : PI-Spalten der VT      (z.B. PERSON_ID)
--   ${CHANGED_RECORDS_TABLE} : Output-VT              (z.B. temp_part_person_changed)
--   ${HASH_EXPRESSION}       : HASHROW()-Ausdruck     (generiert aus hash_columns + TABLE_ALIAS)
--                              z.B. HASHROW(stg.ZEMIS_NR, stg.EV_STATUS_CD, ...)
--   ${IST_AKTUELL_COL}       : Aktuell-Flag Spalte    (z.B. REUS_IST_AKTUELL)
--   ${IST_AKTUELL_VAL}       : Aktuell-Flag Wert      (z.B. J)
-- ============================================================================

CREATE MULTISET VOLATILE TABLE ${CHANGED_RECORDS_TABLE} AS (
    SELECT
        stg.*,
        ${HASH_EXPRESSION} AS RECORD_HASH
    FROM ${STAGING_TABLE} stg
    INNER JOIN ${TARGET_DATABASE}.${TARGET_TABLE} hist
        ON ${BUSINESS_KEY_JOIN}
        AND hist.${IST_AKTUELL_COL} = '${IST_AKTUELL_VAL}'
    WHERE ${HASH_EXPRESSION} <> hist.RECORD_HASH
) WITH DATA
PRIMARY INDEX (${PRIMARY_INDEX_COLS})
ON COMMIT PRESERVE ROWS;
