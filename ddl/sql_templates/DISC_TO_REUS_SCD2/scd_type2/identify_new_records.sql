-- ============================================================================
-- TEMPLATE: Identify New Records (SCD Type 2) — DISC TO REUS
-- ============================================================================
-- Identifiziert Records die noch NICHT in der REUS-Tabelle existieren.
-- Verwendet LEFT JOIN: Wenn REUS NULL → Record ist NEU.
--
-- UNTERSCHIED zu RAW→DISC: IS_CURRENT='Y' → ${IST_AKTUELL_COL}='${IST_AKTUELL_VAL}'
--
-- PARAMETER:
--   ${STAGING_TABLE}           : Staging-Tabelle      (z.B. temp_part_person_staging)
--   ${TARGET_DATABASE}         : REUS-Datenbank        (z.B. MDP01_REUSABLE_LAYER)
--   ${TARGET_TABLE}            : REUS-Zieltabelle      (z.B. PART_PERSON)
--   ${BUSINESS_KEY_JOIN}       : JOIN-Bedingung        (z.B. stg.PERSON_ID = hist.PERSON_ID)
--   ${BUSINESS_KEY_NULL_CHECK} : NULL-Check neue Rec.  (z.B. hist.PERSON_ID IS NULL)
--   ${PRIMARY_INDEX_COLS}      : PI-Spalten der VT     (z.B. PERSON_ID)
--   ${NEW_RECORDS_TABLE}       : Output-VT             (z.B. temp_part_person_new)
--   ${IST_AKTUELL_COL}         : Aktuell-Flag Spalte   (z.B. REUS_IST_AKTUELL)
--   ${IST_AKTUELL_VAL}         : Aktuell-Flag Wert     (z.B. J)
-- ============================================================================

CREATE MULTISET VOLATILE TABLE ${NEW_RECORDS_TABLE} AS (
    SELECT stg.*
    FROM ${STAGING_TABLE} stg
    LEFT JOIN ${TARGET_DATABASE}.${TARGET_TABLE} hist
        ON ${BUSINESS_KEY_JOIN}
        AND hist.${IST_AKTUELL_COL} = '${IST_AKTUELL_VAL}'
    WHERE ${BUSINESS_KEY_NULL_CHECK}
) WITH DATA
PRIMARY INDEX (${PRIMARY_INDEX_COLS})
ON COMMIT PRESERVE ROWS;
