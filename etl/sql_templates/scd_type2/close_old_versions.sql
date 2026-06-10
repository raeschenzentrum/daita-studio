-- ============================================================================
-- TEMPLATE: Close Old Versions (SCD Type 2)
-- ============================================================================
-- Schließt alte Versionen für geänderte Records
-- Setzt IS_CURRENT='N' und VALID_TO=CURRENT_TIMESTAMP
-- 
-- PARAMETER:
--   ${TARGET_DATABASE}       : Target Database (z.B. MDP01_DISCOVERABLE_LAYER)
--   ${TARGET_TABLE}          : Target History-Tabelle (z.B. TAAA_PERSON_HISTORY)
--   ${BUSINESS_KEY_TGT_JOIN} : JOIN-Bedingung (generiert)
--                              Single:    MDP01_DISC.TAAA_PERSON_HISTORY.PERSON_ID = chg.PERSON_ID
--                              Composite: MDP01_DISC.TARF_TX_HISTORY.KEYCD = chg.KEYCD AND MDP01_DISC.TARF_TX_HISTORY.LANG_CD = chg.LANG_CD
--   ${CHANGED_RECORDS_TABLE} : Temp-Tabelle mit geänderten Records (z.B. temp_taaa_person_changed)
-- ============================================================================

UPDATE ${TARGET_DATABASE}.${TARGET_TABLE}
FROM ${CHANGED_RECORDS_TABLE} chg
SET
    IS_CURRENT = 'N',
    VALID_TO = CURRENT_TIMESTAMP(6),
    LAST_UPDATED_TIMESTAMP = CURRENT_TIMESTAMP(6),
    LAST_UPDATED_BY = USER
WHERE ${BUSINESS_KEY_TGT_JOIN}
  AND ${TARGET_DATABASE}.${TARGET_TABLE}.IS_CURRENT = 'Y';
