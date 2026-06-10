-- ============================================================================
-- TEMPLATE: Calculate Statistics — DISC TO REUS
-- ============================================================================
-- Zählt aktuelle, historische und totale Records für Monitoring.
--
-- UNTERSCHIED zu RAW→DISC: IS_CURRENT → ${IST_AKTUELL_COL}
--
-- PARAMETER:
--   ${TARGET_DATABASE}         : REUS-Datenbank       (z.B. MDP01_REUSABLE_LAYER)
--   ${TARGET_TABLE}            : REUS-Zieltabelle      (z.B. PART_PERSON)
--   ${IST_AKTUELL_COL}         : Aktuell-Flag Spalte   (z.B. REUS_IST_AKTUELL)
--   ${IST_AKTUELL_VAL}         : Aktuell-Flag Wert     (z.B. J)
--   ${IST_AKTUELL_GESCHLOSSEN} : Historisch-Flag Wert  (z.B. N)
-- ============================================================================

SELECT 'Current Records'    AS metric_name, COUNT(*) AS metric_value
FROM ${TARGET_DATABASE}.${TARGET_TABLE}
WHERE ${IST_AKTUELL_COL} = '${IST_AKTUELL_VAL}';

SELECT 'Historical Records' AS metric_name, COUNT(*) AS metric_value
FROM ${TARGET_DATABASE}.${TARGET_TABLE}
WHERE ${IST_AKTUELL_COL} = '${IST_AKTUELL_GESCHLOSSEN}';

SELECT 'Total Records'      AS metric_name, COUNT(*) AS metric_value
FROM ${TARGET_DATABASE}.${TARGET_TABLE};
