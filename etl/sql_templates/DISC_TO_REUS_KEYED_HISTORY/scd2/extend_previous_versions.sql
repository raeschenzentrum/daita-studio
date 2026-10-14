-- ============================================================================
-- TEMPLATE: Extend / Close Previous Versions (Reusable mit eigener Historie)
-- ============================================================================
-- 1. Fortsetzung (RUN_NO = 0): die letzte Version im Ziel übernimmt Ende,
--    Aktuell-Kennzeichen, Lösch-Kennzeichen und Änderungs-Ladelauf der letzten
--    Delta-Zeile ihres Laufs (schließt sie z.B., wenn die Discoverable-Version
--    geschlossen oder in der Quelle gelöscht wurde).
-- 2. Absicherung: beginnt das Delta eines Schlüssels mit einer neuen Version,
--    wird eine noch offene letzte Version zu deren Beginn geschlossen.
--
-- PARAMETER:
--   ${TARGET_DATABASE}, ${TARGET_TABLE}, ${VERSIONS_TABLE}
--   ${PART_KEY_V}, ${KEY_COLS_V}, ${JOIN_KEY_T_E} (generiert)
--   ${SRC_VALID_FROM}, ${SRC_VALID_TO}, ${SRC_DELETED}, ${SRC_LOAD_ID}, ${SRC_UPDATE_LOAD_ID}
--   ${OPEN_VALID_TO}, ${IS_CURRENT_OPEN} : aktuell = Ende offen
--   ${TGT_VALID_FROM_COL}, ${TGT_VALID_TO_COL}, ${TGT_IS_CURRENT_COL},
--   ${TGT_DELETED_COL}, ${TGT_UPDATE_LOAD_ID_COL}, ${TGT_UPDATED_TS_COL},
--   ${IS_CURRENT_CLOSED}
-- ============================================================================

UPDATE t
FROM ${TARGET_DATABASE}.${TARGET_TABLE} t,
     (
        SELECT ${KEY_COLS_V}, v.L_VALID_FROM,
               v.${SRC_VALID_TO}       AS E_VALID_TO,
               CASE WHEN v.${SRC_VALID_TO} = TIMESTAMP '${OPEN_VALID_TO}'
                    THEN '${IS_CURRENT_OPEN}' ELSE '${IS_CURRENT_CLOSED}' END AS E_IS_CURRENT,
               v.${SRC_DELETED}        AS E_DELETED,
               v.${SRC_UPDATE_LOAD_ID} AS E_UPDATE_LOAD_ID
        FROM ${VERSIONS_TABLE} v
        WHERE v.RUN_NO = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY ${PART_KEY_V} ORDER BY v.SEQ_NO DESC) = 1
     ) e
SET
    ${TGT_VALID_TO_COL}       = e.E_VALID_TO,
    ${TGT_IS_CURRENT_COL}     = e.E_IS_CURRENT,
    ${TGT_DELETED_COL}        = e.E_DELETED,
    ${TGT_UPDATE_LOAD_ID_COL} = e.E_UPDATE_LOAD_ID,
    ${TGT_UPDATED_TS_COL}     = CURRENT_TIMESTAMP(6)
WHERE ${JOIN_KEY_T_E}
  AND t.${TGT_VALID_FROM_COL} = e.L_VALID_FROM;

UPDATE t
FROM ${TARGET_DATABASE}.${TARGET_TABLE} t,
     (
        SELECT ${KEY_COLS_V}, v.L_VALID_FROM,
               v.${SRC_VALID_FROM} AS F_VALID_FROM,
               v.${SRC_LOAD_ID}    AS F_LOAD_ID
        FROM ${VERSIONS_TABLE} v
        WHERE v.SEQ_NO = 1 AND v.IS_KEPT = 1 AND v.L_VALID_FROM IS NOT NULL
     ) e
SET
    ${TGT_VALID_TO_COL}       = e.F_VALID_FROM,
    ${TGT_IS_CURRENT_COL}     = '${IS_CURRENT_CLOSED}',
    ${TGT_UPDATE_LOAD_ID_COL} = e.F_LOAD_ID,
    ${TGT_UPDATED_TS_COL}     = CURRENT_TIMESTAMP(6)
WHERE ${JOIN_KEY_T_E}
  AND t.${TGT_VALID_FROM_COL} = e.L_VALID_FROM
  AND t.${TGT_VALID_TO_COL} > e.F_VALID_FROM;
