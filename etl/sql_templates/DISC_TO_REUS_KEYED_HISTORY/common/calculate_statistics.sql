-- ============================================================================
-- TEMPLATE: Calculate Statistics (Reusable mit eigener Historie)
-- ============================================================================
-- PARAMETER:
--   ${TARGET_DATABASE}, ${TARGET_TABLE}, ${TGT_IS_CURRENT_COL}, ${IS_CURRENT_OPEN},
--   ${TGT_DELETED_COL}, ${DELETED_VAL}
-- ============================================================================

SELECT
    COUNT(*) AS total_versions,
    SUM(CASE WHEN ${TGT_IS_CURRENT_COL} = '${IS_CURRENT_OPEN}' THEN 1 ELSE 0 END) AS current_versions,
    SUM(CASE WHEN ${TGT_DELETED_COL} = '${DELETED_VAL}' THEN 1 ELSE 0 END) AS deleted_in_source
FROM ${TARGET_DATABASE}.${TARGET_TABLE};
