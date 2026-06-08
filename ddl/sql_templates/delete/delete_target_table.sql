-- ==============================================================================
-- Delete Target Table Template
-- ==============================================================================
-- 
-- Purpose: Löscht alle Daten aus einer Zieltabelle (Initial Load Mode)
--
-- Parameters (JSON):
--   {
--     "target_database": "MDP01_DISCOVERABLE_LAYER",
--     "target_table": "TAAA_PERSON_HISTORY"
--   }
--
-- Author: DWH MVP Team
-- Date: 2026-01-23
-- ==============================================================================

DELETE FROM ${target_database}.${target_table} ALL;