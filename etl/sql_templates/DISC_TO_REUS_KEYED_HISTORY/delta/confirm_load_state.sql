-- ============================================================================
-- TEMPLATE: Confirm Load State (Reusable mit eigener Historie)
-- ============================================================================
-- Schreibt den Ladestand fort, wenn das Delta (über alle Rollen des Jobs)
-- Zeilen hatte: höchster verarbeiteter Ladelauf (Entstehen oder Änderung einer
-- Quell-Version, bis zur Obergrenze). Letzter Step des Jobs; beide Anweisungen
-- laufen als ein Request und damit in einer Transaktion.
--
-- PARAMETER:
--   ${META_DATABASE}, ${LOAD_STATE_TABLE}, ${ETL_JOB_ID}, ${SOURCE_TABLE_ID}
--   ${DELTA_EVENTS} : SELECT ... AS EVT FROM <Staging je Rolle> UNION ALL ... (generiert)
-- ============================================================================

DELETE FROM ${META_DATABASE}.${LOAD_STATE_TABLE}
WHERE ETL_JOB_ID = ${ETL_JOB_ID}
  AND EXISTS (SELECT 1 FROM (${DELTA_EVENTS}) x);

INSERT INTO ${META_DATABASE}.${LOAD_STATE_TABLE}
    (ETL_JOB_ID, SOURCE_TABLE_ID, LAST_LOAD_ID, LAST_SNAPSHOT_TS, UPDATED_TIMESTAMP, UPDATED_BY)
SELECT
    ${ETL_JOB_ID},
    ${SOURCE_TABLE_ID},
    MAX(x.EVT),
    NULL,
    CURRENT_TIMESTAMP(6),
    USER
FROM (${DELTA_EVENTS}) x
HAVING COUNT(*) > 0;
