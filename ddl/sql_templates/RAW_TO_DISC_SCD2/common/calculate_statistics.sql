-- ============================================================================
-- TEMPLATE: Calculate Statistics
-- ============================================================================
-- Sammelt Execution-Metriken für einen Job-Run
-- 
-- PARAMETER:
--   ${TARGET_DATABASE}     : Target Database (z.B. MDP01_DISCOVERABLE_LAYER)
--   ${TARGET_TABLE}        : Target History-Tabelle (z.B. TAAA_PERSON_HISTORY)
-- ============================================================================

-- Zähle aktuelle Records
SELECT 
    'Current Records' AS metric_name,
    COUNT(*) AS metric_value
FROM ${TARGET_DATABASE}.${TARGET_TABLE}
WHERE IS_CURRENT = 'Y';

-- Zähle historische Records
SELECT 
    'Historical Records' AS metric_name,
    COUNT(*) AS metric_value
FROM ${TARGET_DATABASE}.${TARGET_TABLE}
WHERE IS_CURRENT = 'N';

-- Zähle total Records
SELECT 
    'Total Records' AS metric_name,
    COUNT(*) AS metric_value
FROM ${TARGET_DATABASE}.${TARGET_TABLE};
