-- ============================================================================
-- TEMPLATE: Close Old Versions (SCD Type 2) — DISC TO REUS
-- ============================================================================
-- Schliesst alte Versionen für alle geänderten Records:
--   ${IST_AKTUELL_COL} = '${IST_AKTUELL_GESCHLOSSEN}'
--   ${GUELTIGBIS_COL}  = CURRENT_TIMESTAMP
--
-- UNTERSCHIED zu RAW→DISC:
--   IS_CURRENT='N'  → ${IST_AKTUELL_COL}='${IST_AKTUELL_GESCHLOSSEN}'
--   VALID_TO        → ${GUELTIGBIS_COL}
--
-- PARAMETER:
--   ${TARGET_DATABASE}         : REUS-Datenbank         (z.B. MDP01_REUSABLE_LAYER)
--   ${TARGET_TABLE}            : REUS-Zieltabelle        (z.B. PART_PERSON)
--   ${CHANGED_RECORDS_TABLE}   : VT mit geänderten Rec.  (z.B. temp_part_person_changed)
--   ${BUSINESS_KEY_TGT_JOIN}   : Vollqualifizierter JOIN
--                                z.B. MDP01_REUSABLE_LAYER.PART_PERSON.PERSON_ID = chg.PERSON_ID
--   ${GUELTIGBIS_COL}          : Gültig-Bis Spalte       (z.B. REUS_GUELTIGBIS)
--   ${IST_AKTUELL_COL}         : Aktuell-Flag Spalte     (z.B. REUS_IST_AKTUELL)
--   ${IST_AKTUELL_GESCHLOSSEN} : Wert für geschlossen    (z.B. N)
-- ============================================================================

UPDATE ${TARGET_DATABASE}.${TARGET_TABLE}
FROM ${CHANGED_RECORDS_TABLE} chg
SET
    ${IST_AKTUELL_COL}         = '${IST_AKTUELL_GESCHLOSSEN}',
    ${GUELTIGBIS_COL}          = CURRENT_TIMESTAMP(6),
    LAST_UPDATED_TIMESTAMP     = CURRENT_TIMESTAMP(6),
    LAST_UPDATED_BY            = USER
WHERE ${BUSINESS_KEY_TGT_JOIN}
  AND ${TARGET_DATABASE}.${TARGET_TABLE}.${IST_AKTUELL_COL} <> '${IST_AKTUELL_GESCHLOSSEN}';
