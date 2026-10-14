-- ============================================================================
-- TEMPLATE: Insert Versions (Reusable mit eigener Historie)
-- ============================================================================
-- Fügt je neuer Version (IS_KEPT = 1) eine Zeile ein:
--   Gültigkeitsbeginn, Ladelauf, Hash  = aus der Delta-Zeile, die die Version beginnt
--   Ende, Aktuell, gelöscht, Änderungs-Ladelauf = aus der letzten Delta-Zeile
--                                        desselben Laufs (RUN_NO)
-- Verweise (FK) werden über die KEY-Tabelle des Ziels zur SK; -1 nur bei NULL
-- (fehlende Keys hat der Step "Late Arriving Keys" schon angelegt).
--
-- PARAMETER:
--   ${TARGET_DATABASE}, ${TARGET_TABLE}, ${VERSIONS_TABLE}
--   ${SK_COLUMN}, ${INSERT_COLUMNS}, ${INSERT_SELECT}, ${FK_INSERT_COLUMNS},
--   ${FK_SK_COLUMNS}, ${FK_JOINS} (Alias st), ${KEY_COLS_V_EN}, ${JOIN_KEY_ST_EN},
--   ${PART_KEY_V} (generiert)
--   ${SRC_*}, ${STG_HASH}, ${TGT_*_COL}
--   ${OPEN_VALID_TO}, ${IS_CURRENT_OPEN}, ${IS_CURRENT_CLOSED} : aktuell = Ende offen
-- ============================================================================

INSERT INTO ${TARGET_DATABASE}.${TARGET_TABLE}
(
    ${SK_COLUMN},
${FK_INSERT_COLUMNS}
    ${INSERT_COLUMNS},
    ${TGT_VALID_FROM_COL},
    ${TGT_VALID_TO_COL},
    ${TGT_IS_CURRENT_COL},
    ${TGT_DELETED_COL},
    ${TGT_LOAD_ID_COL},
    ${TGT_UPDATE_LOAD_ID_COL},
    ${TGT_HASH_COL},
    ${TGT_CREATED_TS_COL},
    ${TGT_UPDATED_TS_COL}
)
SELECT
    st.${SK_COLUMN},
${FK_SK_COLUMNS}
    ${INSERT_SELECT},
    st.${SRC_VALID_FROM},
    en.${SRC_VALID_TO},
    en.E_IS_CURRENT,
    en.${SRC_DELETED},
    st.${SRC_LOAD_ID},
    en.${SRC_UPDATE_LOAD_ID},
    st.${STG_HASH},
    CURRENT_TIMESTAMP(6),
    CURRENT_TIMESTAMP(6)
FROM (
    SELECT * FROM ${VERSIONS_TABLE} WHERE IS_KEPT = 1
) st
JOIN (
    SELECT ${KEY_COLS_V}, v.RUN_NO,
           v.${SRC_VALID_TO}, v.${SRC_DELETED}, v.${SRC_UPDATE_LOAD_ID},
           CASE WHEN v.${SRC_VALID_TO} = TIMESTAMP '${OPEN_VALID_TO}'
                THEN '${IS_CURRENT_OPEN}' ELSE '${IS_CURRENT_CLOSED}' END AS E_IS_CURRENT
    FROM ${VERSIONS_TABLE} v
    QUALIFY ROW_NUMBER() OVER (PARTITION BY ${PART_KEY_V}, v.RUN_NO ORDER BY v.SEQ_NO DESC) = 1
) en
  ON ${JOIN_KEY_ST_EN}
 AND en.RUN_NO = st.RUN_NO
${FK_JOINS};
