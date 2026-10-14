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
--   3. Für die behaltenen Zeilen: Snapshot-Zeit, Art und Ladelauf der nächsten
--      Zeile (ergibt VALID_TO, IS_CURRENT, das Lösch-Kennzeichen und den
--      schließenden Ladelauf im Insert).
--   4. IS_INITIAL_VERSION = 'Y' für die erste Version eines Keys aus dem ersten
--      Ladelauf des Jobs (Ladestand 0, kleinster Ladelauf im Staging, Key noch
--      nicht im Ziel). Sie bekommt im Insert den Gültigkeitsbeginn des
--      initialen Stands (ADR-0016).
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
--   ${PRIMARY_INDEX_COLS}, ${LOAD_WATERMARK}
-- ============================================================================

CREATE MULTISET VOLATILE TABLE ${VERSIONS_TABLE} AS (
    SELECT
        v.*,
        LEAD(v.${SNAPSHOT_COL}) OVER (
            PARTITION BY ${BUSINESS_KEY} ORDER BY v.${LOAD_ID_COL}
        ) AS NEXT_SNAPSHOT,
        LEAD(v.${CHANGE_TYPE_COL}) OVER (
            PARTITION BY ${BUSINESS_KEY} ORDER BY v.${LOAD_ID_COL}
        ) AS NEXT_CHANGE_TYPE,
        LEAD(v.${LOAD_ID_COL}) OVER (
            PARTITION BY ${BUSINESS_KEY} ORDER BY v.${LOAD_ID_COL}
        ) AS NEXT_LOAD_ID
    FROM (
        SELECT
            stg.*,
            CASE
                WHEN stg.PREV_LOAD_ID IS NOT NULL THEN prev.${RECORD_HASH_COL}
                WHEN hist.CUR_DELETED = '${DELETED_VAL}' THEN NULL
                ELSE hist.CUR_HASH
            END AS PREV_HASH,
            CASE
                WHEN stg.PREV_LOAD_ID IS NULL
                 AND hist.CUR_EXISTS IS NULL
                 AND ${LOAD_WATERMARK} = 0
                 AND stg.${LOAD_ID_COL} = (SELECT MIN(s0.${LOAD_ID_COL}) FROM ${STAGING_TABLE} s0)
                THEN 'Y' ELSE 'N'
            END AS IS_INITIAL_VERSION
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
                hist.${DELETED_COL} AS CUR_DELETED,
                1 AS CUR_EXISTS
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
