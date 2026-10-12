-- ============================================================================
-- TEMPLATE: Calculate Statistics (SCD2 aus RAW-Deltas)
-- ============================================================================
-- Zählwerte der Zieltabelle nach dem Lauf.
--
-- PARAMETER:
--   ${TARGET_DATABASE}, ${TARGET_TABLE}
--   ${IST_AKTUELL_COL}, ${IST_AKTUELL_VAL}, ${DELETED_COL}, ${DELETED_VAL}
-- ============================================================================

SELECT
    COUNT(*) AS total_versions,
    SUM(CASE WHEN ${IST_AKTUELL_COL} = '${IST_AKTUELL_VAL}' THEN 1 ELSE 0 END) AS current_versions,
    SUM(CASE WHEN ${DELETED_COL} = '${DELETED_VAL}' THEN 1 ELSE 0 END) AS deleted_in_source
FROM ${TARGET_DATABASE}.${TARGET_TABLE};
