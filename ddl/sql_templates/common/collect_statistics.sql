-- ============================================================================
-- Template: collect_statistics.sql
-- ============================================================================
-- Zweck: Sammelt Statistiken für eine Tabelle nach dem Laden
-- 
-- Parameter:
--   ${TARGET_DATABASE}  - Datenbank der Tabelle
--   ${TARGET_TABLE}     - Tabellen-Name
-- ============================================================================

COLLECT STATISTICS ON ${TARGET_DATABASE}.${TARGET_TABLE};
