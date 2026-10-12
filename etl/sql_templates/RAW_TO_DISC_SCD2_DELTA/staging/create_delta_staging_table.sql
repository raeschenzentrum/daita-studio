-- ============================================================================
-- TEMPLATE: Create Delta Staging Table (SCD2 aus RAW-Deltas)
-- ============================================================================
-- Liest alle RAW-Zeilen der noch nicht verarbeiteten Ladeläufe
-- (Ladestand < Ladelauf <= Obergrenze) mit Fachspalten, den drei
-- Technikspalten und dem Hash der Fachspalten.
-- Initial Load = Lauf mit Ladestand 0.
--
-- PARAMETER:
--   ${SOURCE_DATABASE}, ${SOURCE_TABLE} : RAW-Tabelle
--   ${STAGING_TABLE}    : Volatile Staging-Tabelle
--   ${SELECT_COLUMNS}   : Fachspalten (generiert, Alias src)
--   ${HASH_EXPRESSION}  : Hash über HASH_COLUMNS (generiert, Alias src)
--   ${LOAD_ID_COL}, ${SNAPSHOT_COL}, ${CHANGE_TYPE_COL} : RAW-Technikspalten
--   ${RECORD_HASH_COL}  : Name der Hash-Spalte
--   ${LOAD_WATERMARK}   : Ausdruck für den bestätigten Ladestand (generiert)
--   ${MAX_LOAD_ID}      : Obergrenze (für Tests und Nachholläufe)
--   ${BUSINESS_KEY}     : Business Key (Primary Index)
-- ============================================================================

CREATE MULTISET VOLATILE TABLE ${STAGING_TABLE} AS (
    SELECT
        ${SELECT_COLUMNS},
        src.${LOAD_ID_COL},
        src.${SNAPSHOT_COL},
        src.${CHANGE_TYPE_COL},
        ${HASH_EXPRESSION} AS ${RECORD_HASH_COL}
    FROM ${SOURCE_DATABASE}.${SOURCE_TABLE} src
    WHERE src.${LOAD_ID_COL} > ${LOAD_WATERMARK}
      AND src.${LOAD_ID_COL} <= ${MAX_LOAD_ID}
) WITH DATA
PRIMARY INDEX (${BUSINESS_KEY})
ON COMMIT PRESERVE ROWS;
