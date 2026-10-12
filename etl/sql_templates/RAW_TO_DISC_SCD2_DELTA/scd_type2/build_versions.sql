-- ============================================================================
-- TEMPLATE: Build Versions (SCD2 aus RAW-Deltas)
-- ============================================================================
-- Bildet aus den Delta-Zeilen die Versionsfolge je Business Key:
--   1. Vorgänger-Hash = Hash der vorherigen Delta-Zeile, für die erste
--      Delta-Zeile die letzte Version im Ziel (sofern nicht in der Quelle
--      gelöscht). Teradata erlaubt LAG nicht auf BYTE-Spalten, daher wird der
--      vorherige Ladelauf per LAG bestimmt und die Zeile per Join geholt.
--   2. Behalten werden Löschungen, Zeilen mit anderem Hash als der Vorgänger
--      und Zeilen nach einer Löschung. Hashgleiche Folgezeilen entfallen.
--   3. Für die behaltenen Zeilen: Snapshot-Zeit und Art der nächsten Zeile
--      (ergibt VALID_TO, IS_CURRENT und das Lösch-Kennzeichen im Insert).
-- Löschungen werden keine Version; sie schließen ihren Vorgänger.
--
-- PARAMETER:
--   ${STAGING_TABLE}, ${VERSIONS_TABLE} : Volatile Tabellen
--   ${TARGET_DATABASE}, ${TARGET_TABLE} : Target History-Tabelle
--   ${BUSINESS_KEY}           : Business Key, ohne Alias
--   ${BUSINESS_KEY_STG}       : Business Key mit Alias stg (generiert)
--   ${BUSINESS_KEY_HIST}      : Business Key mit Alias hist (generiert)
--   ${BUSINESS_KEY_JOIN}      : stg.X = hist.X (generiert)
--   ${BUSINESS_KEY_JOIN_PREV} : stg.X = prev.X (generiert)
--   ${LOAD_ID_COL}, ${SNAPSHOT_COL}, ${CHANGE_TYPE_COL}, ${CT_DELETE}
--   ${RECORD_HASH_COL}, ${DELETED_COL}, ${DELETED_VAL}, ${GUELTIGVON_COL}
--   ${PRIMARY_INDEX_COLS}
-- ============================================================================

CREATE MULTISET VOLATILE TABLE ${VERSIONS_TABLE} AS (
    SELECT
        v.*,
        LEAD(v.${SNAPSHOT_COL}) OVER (
            PARTITION BY ${BUSINESS_KEY} ORDER BY v.${LOAD_ID_COL}
        ) AS NEXT_SNAPSHOT,
        LEAD(v.${CHANGE_TYPE_COL}) OVER (
            PARTITION BY ${BUSINESS_KEY} ORDER BY v.${LOAD_ID_COL}
        ) AS NEXT_CHANGE_TYPE
    FROM (
        SELECT
            stg.*,
            CASE
                WHEN stg.PREV_LOAD_ID IS NOT NULL THEN prev.${RECORD_HASH_COL}
                WHEN hist.CUR_DELETED = '${DELETED_VAL}' THEN NULL
                ELSE hist.CUR_HASH
            END AS PREV_HASH
        FROM (
            SELECT
                stg.*,
                LAG(stg.${LOAD_ID_COL}) OVER (
                    PARTITION BY ${BUSINESS_KEY_STG} ORDER BY stg.${LOAD_ID_COL}
                ) AS PREV_LOAD_ID,
                LAG(stg.${CHANGE_TYPE_COL}) OVER (
                    PARTITION BY ${BUSINESS_KEY_STG} ORDER BY stg.${LOAD_ID_COL}
                ) AS PREV_CHANGE_TYPE
            FROM ${STAGING_TABLE} stg
        ) stg
        LEFT JOIN ${STAGING_TABLE} prev
            ON ${BUSINESS_KEY_JOIN_PREV}
           AND prev.${LOAD_ID_COL} = stg.PREV_LOAD_ID
        LEFT JOIN (
            SELECT
                ${BUSINESS_KEY_HIST},
                hist.${RECORD_HASH_COL} AS CUR_HASH,
                hist.${DELETED_COL} AS CUR_DELETED
            FROM ${TARGET_DATABASE}.${TARGET_TABLE} hist
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY ${BUSINESS_KEY_HIST} ORDER BY hist.${GUELTIGVON_COL} DESC
            ) = 1
        ) hist
            ON ${BUSINESS_KEY_JOIN}
    ) v
    WHERE v.${CHANGE_TYPE_COL} = '${CT_DELETE}'
       OR v.PREV_HASH IS NULL
       OR v.${RECORD_HASH_COL} <> v.PREV_HASH
       OR v.PREV_CHANGE_TYPE = '${CT_DELETE}'
) WITH DATA
PRIMARY INDEX (${PRIMARY_INDEX_COLS})
ON COMMIT PRESERVE ROWS;
