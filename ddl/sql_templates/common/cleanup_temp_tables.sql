-- ============================================================================
-- TEMPLATE: Cleanup Temporary Tables
-- ============================================================================
-- Löscht alle temporären VOLATILE Tables
-- Wird am Ende eines Jobs ausgeführt
-- 
-- HINWEIS: In Teradata werden VOLATILE Tables automatisch beim DISCONNECT gelöscht
-- Dieses Template dient zur expliziten Bereinigung während der Session
-- ============================================================================

-- Cleanup wird automatisch durch ON COMMIT PRESERVE ROWS + Session-Ende gemacht
-- Keine expliziten DROP Statements nötig (würde in ANSI Transaction Mode Fehler werfen)

-- Falls manuelle Bereinigung gewünscht:
-- DROP TABLE temp_taaa_person_staging;
-- DROP TABLE temp_new_records;
-- DROP TABLE temp_changed_records;

SELECT 'Cleanup completed - VOLATILE tables will be dropped on disconnect' AS status;
