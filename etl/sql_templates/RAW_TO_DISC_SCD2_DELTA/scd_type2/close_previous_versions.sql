-- ============================================================================
-- TEMPLATE: Close Previous Versions (SCD2 aus RAW-Deltas)
-- ============================================================================
-- Schließt je Business Key die letzte Version vor diesem Delta:
--   VALID_TO      = Snapshot-Zeit der ersten Delta-Version (halboffen)
--   IS_CURRENT    = geschlossen
--   Lösch-Kennz.  = gesetzt, wenn die erste Delta-Zeile eine Löschung ist
-- Betroffen ist nur die Version, deren VALID_TO noch offen ist oder die ein
-- abgebrochener Lauf bereits auf denselben Zeitpunkt geschlossen hat
-- (VALID_TO >= erste Delta-Snapshot-Zeit). Ältere Versionen und Versionen,
-- die eine frühere Löschung geschlossen hat, bleiben unberührt.
-- Wiederholbar: dasselbe Delta setzt dieselben Werte.
--
-- PARAMETER:
--   ${TARGET_DATABASE}, ${TARGET_TABLE}, ${VERSIONS_TABLE}
--   ${BUSINESS_KEY}          : Business Key, ohne Alias
--   ${BUSINESS_KEY_JOIN_TGT} : tgt.X = f.X (generiert)
--   ${LOAD_ID_COL}, ${SNAPSHOT_COL}, ${CHANGE_TYPE_COL}, ${CT_DELETE}
--   ${GUELTIGVON_COL}, ${GUELTIGBIS_COL}, ${IST_AKTUELL_COL}, ${IST_AKTUELL_GESCHLOSSEN}
--   ${DELETED_COL}, ${DELETED_VAL}, ${NOT_DELETED_VAL}
--   ${UPDATED_TS_COL}, ${UPDATED_BY_COL}
-- ============================================================================

UPDATE tgt
FROM ${TARGET_DATABASE}.${TARGET_TABLE} tgt,
     (
        SELECT
            ${BUSINESS_KEY},
            v.${SNAPSHOT_COL} AS FIRST_SNAPSHOT,
            v.${CHANGE_TYPE_COL} AS FIRST_CHANGE_TYPE
        FROM ${VERSIONS_TABLE} v
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY ${BUSINESS_KEY} ORDER BY v.${LOAD_ID_COL}
        ) = 1
     ) f
SET
    ${GUELTIGBIS_COL} = f.FIRST_SNAPSHOT,
    ${IST_AKTUELL_COL} = '${IST_AKTUELL_GESCHLOSSEN}',
    ${DELETED_COL} = CASE WHEN f.FIRST_CHANGE_TYPE = '${CT_DELETE}'
                          THEN '${DELETED_VAL}' ELSE '${NOT_DELETED_VAL}' END,
    ${UPDATED_TS_COL} = CURRENT_TIMESTAMP(6),
    ${UPDATED_BY_COL} = USER
WHERE ${BUSINESS_KEY_JOIN_TGT}
  AND tgt.${GUELTIGVON_COL} < f.FIRST_SNAPSHOT
  AND tgt.${GUELTIGBIS_COL} >= f.FIRST_SNAPSHOT;
