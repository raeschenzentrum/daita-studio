-- ============================================================================
-- TEMPLATE: Insert Versions (SCD2 aus RAW-Deltas)
-- ============================================================================
-- Fügt alle Versionen des Deltas ein (Löschungen sind keine Version):
--   VALID_FROM    = Snapshot-Zeit der Version; für den initialen Stand
--                   (IS_INITIAL_VERSION) der konfigurierte Gültigkeitsbeginn
--                   (ADR-0016, z.B. 1000-01-01)
--   VALID_TO      = Snapshot-Zeit der nächsten Zeile, sonst offen (halboffen)
--   IS_CURRENT    = aktuell, wenn keine nächste Zeile folgt
--   Lösch-Kennz.  = gesetzt, wenn die nächste Zeile eine Löschung ist
--   Ladelauf      = Ladelauf der RAW-Zeile
-- Surrogate Key und Parent-SKs kommen aus den KEY-Tabellen (KEY-Modus),
-- damit hängen sie nicht von der Version des Parents ab.
--
-- PARAMETER:
--   ${TARGET_DATABASE}, ${TARGET_TABLE}, ${VERSIONS_TABLE}
--   ${SK_COLUMN}, ${FK_INSERT_COLUMNS}, ${FK_SK_COLUMNS}, ${FK_JOINS}
--   ${INSERT_COLUMNS}, ${SELECT_COLUMNS} (Alias src)
--   ${KEY_DATABASE}, ${KEY_TABLE}, ${NATURAL_KEY_EXPRESSION_SRC}, ${DOMAIN}
--   ${LOAD_ID_COL}, ${SNAPSHOT_COL}, ${CHANGE_TYPE_COL}, ${CT_DELETE}, ${OPEN_VALID_TO},
--   ${INITIAL_VALID_FROM_EXPR}
--   ${GUELTIGVON_COL}, ${GUELTIGBIS_COL}, ${IST_AKTUELL_COL}, ${IST_AKTUELL_VAL},
--   ${IST_AKTUELL_GESCHLOSSEN}, ${DELETED_COL}, ${DELETED_VAL}, ${NOT_DELETED_VAL},
--   ${DWH_LOAD_ID_COL}, ${RECORD_HASH_COL}, ${CREATED_TS_COL}, ${UPDATED_TS_COL},
--   ${CREATED_BY_COL}, ${UPDATED_BY_COL}
-- ============================================================================

INSERT INTO ${TARGET_DATABASE}.${TARGET_TABLE}
(
    ${SK_COLUMN},
${FK_INSERT_COLUMNS}
    ${INSERT_COLUMNS},
    ${GUELTIGVON_COL},
    ${GUELTIGBIS_COL},
    ${IST_AKTUELL_COL},
    ${DELETED_COL},
    ${DWH_LOAD_ID_COL},
    ${RECORD_HASH_COL},
    ${CREATED_TS_COL},
    ${UPDATED_TS_COL},
    ${CREATED_BY_COL},
    ${UPDATED_BY_COL}
)
SELECT
    COALESCE(k.SURROGATE_KEY, -1) AS ${SK_COLUMN},
${FK_SK_COLUMNS}
    ${SELECT_COLUMNS},
    CASE WHEN src.IS_INITIAL_VERSION = 'Y'
         THEN ${INITIAL_VALID_FROM_EXPR} ELSE src.${SNAPSHOT_COL} END,
    COALESCE(src.NEXT_SNAPSHOT, TIMESTAMP '${OPEN_VALID_TO}'),
    CASE WHEN src.NEXT_SNAPSHOT IS NULL
         THEN '${IST_AKTUELL_VAL}' ELSE '${IST_AKTUELL_GESCHLOSSEN}' END,
    CASE WHEN src.NEXT_CHANGE_TYPE = '${CT_DELETE}'
         THEN '${DELETED_VAL}' ELSE '${NOT_DELETED_VAL}' END,
    src.${LOAD_ID_COL},
    src.${RECORD_HASH_COL},
    CURRENT_TIMESTAMP(6),
    CURRENT_TIMESTAMP(6),
    USER,
    USER
FROM ${VERSIONS_TABLE} src
LEFT JOIN ${KEY_DATABASE}.${KEY_TABLE} k
    ON ${NATURAL_KEY_EXPRESSION_SRC} = k.NATURAL_KEY_VALUE
   AND k.NATURAL_KEY_DOMAIN = '${DOMAIN}'
${FK_JOINS}
WHERE src.${CHANGE_TYPE_COL} <> '${CT_DELETE}';
