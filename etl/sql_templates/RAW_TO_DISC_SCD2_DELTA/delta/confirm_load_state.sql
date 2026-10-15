-- ============================================================================
-- TEMPLATE: Confirm Load State (SCD2 aus RAW-Deltas)
-- ============================================================================
-- Schreibt den verarbeiteten Ladestand fort. Letzter Step des Jobs: Erst
-- danach gelten die Versionen dieses Deltas als bestätigt (siehe
-- remove_unconfirmed_versions.sql). Beide Anweisungen laufen als ein Request
-- und damit in einer Transaktion.
--
-- Neuer Ladestand:
--   - Lauf ohne Obergrenze: höchster Ladelauf des Deltas; ohne Delta bleibt
--     der Ladestand stehen.
--   - Lauf mit Obergrenze (${LOAD_BOUND}, z. B. Simulation täglicher Läufe):
--     die Obergrenze, auch wenn die Tabelle bis dahin nichts geliefert hat –
--     alle Ladeläufe bis zur Obergrenze sind verarbeitet. Dadurch rückt die
--     Obergrenze der Folgeschicht (kleinster Ladestand der Vorgänger-Jobs)
--     auch für Tabellen ohne Lieferung an diesem Tag vor. Eine Obergrenze
--     unter dem Ladestand ändert nichts.
--
-- PARAMETER:
--   ${META_DATABASE}, ${LOAD_STATE_TABLE} : Tabelle mit dem Ladestand
--   ${ETL_JOB_ID}, ${SOURCE_TABLE_ID}
--   ${STAGING_TABLE}, ${LOAD_ID_COL}, ${SNAPSHOT_COL}
--   ${LOAD_BOUND}       : Obergrenze des Laufs als BIGINT-Ausdruck oder
--                         CAST(NULL AS BIGINT) (Laufzeitparameter)
-- ============================================================================

UPDATE st
FROM ${META_DATABASE}.${LOAD_STATE_TABLE} st,
     (SELECT MAX(stg.${LOAD_ID_COL}), MAX(stg.${SNAPSHOT_COL}), COUNT(*)
      FROM ${STAGING_TABLE} stg) d (MAX_LOAD_ID, MAX_SNAPSHOT_TS, ANZAHL)
SET LAST_LOAD_ID      = COALESCE(${LOAD_BOUND}, d.MAX_LOAD_ID),
    LAST_SNAPSHOT_TS  = COALESCE(d.MAX_SNAPSHOT_TS, st.LAST_SNAPSHOT_TS),
    UPDATED_TIMESTAMP = CURRENT_TIMESTAMP(6),
    UPDATED_BY        = USER
WHERE st.ETL_JOB_ID = ${ETL_JOB_ID}
  AND (d.ANZAHL > 0 OR COALESCE(${LOAD_BOUND}, 0) > st.LAST_LOAD_ID);

INSERT INTO ${META_DATABASE}.${LOAD_STATE_TABLE}
    (ETL_JOB_ID, SOURCE_TABLE_ID, LAST_LOAD_ID, LAST_SNAPSHOT_TS, UPDATED_TIMESTAMP, UPDATED_BY)
SELECT
    ${ETL_JOB_ID},
    ${SOURCE_TABLE_ID},
    COALESCE(${LOAD_BOUND}, MAX(stg.${LOAD_ID_COL})),
    MAX(stg.${SNAPSHOT_COL}),
    CURRENT_TIMESTAMP(6),
    USER
FROM ${STAGING_TABLE} stg
HAVING (COUNT(*) > 0 OR COALESCE(${LOAD_BOUND}, 0) > 0)
   AND NOT EXISTS (SELECT 1 FROM ${META_DATABASE}.${LOAD_STATE_TABLE}
                   WHERE ETL_JOB_ID = ${ETL_JOB_ID});
