-- ============================================================================
-- TEMPLATE: Confirm Load State (SCD2 aus RAW-Deltas)
-- ============================================================================
-- Schreibt den verarbeiteten Ladestand fort, wenn das Delta Zeilen hatte.
-- Letzter Step des Jobs: Erst danach gelten die Versionen dieses Deltas als
-- bestätigt (siehe remove_unconfirmed_versions.sql).
-- Beide Anweisungen laufen als ein Request und damit in einer Transaktion.
--
-- PARAMETER:
--   ${META_DATABASE}, ${LOAD_STATE_TABLE} : Tabelle mit dem Ladestand
--   ${ETL_JOB_ID}, ${SOURCE_TABLE_ID}
--   ${STAGING_TABLE}, ${LOAD_ID_COL}, ${SNAPSHOT_COL}
-- ============================================================================

DELETE FROM ${META_DATABASE}.${LOAD_STATE_TABLE}
WHERE ETL_JOB_ID = ${ETL_JOB_ID}
  AND EXISTS (SELECT 1 FROM ${STAGING_TABLE});

INSERT INTO ${META_DATABASE}.${LOAD_STATE_TABLE}
    (ETL_JOB_ID, SOURCE_TABLE_ID, LAST_LOAD_ID, LAST_SNAPSHOT_TS, UPDATED_TIMESTAMP, UPDATED_BY)
SELECT
    ${ETL_JOB_ID},
    ${SOURCE_TABLE_ID},
    MAX(stg.${LOAD_ID_COL}),
    MAX(stg.${SNAPSHOT_COL}),
    CURRENT_TIMESTAMP(6),
    USER
FROM ${STAGING_TABLE} stg
HAVING COUNT(*) > 0;
