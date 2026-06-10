-- ============================================================================
-- TEMPLATE: Insert New Versions from Staging (SCD Type 2) — DISC TO REUS
-- ============================================================================
-- Fügt neue Versionen ein. SK kommt direkt aus der Staging-Tabelle
-- (wird bereits durch die DISC Business View mitgeliefert — kein KEY-Join nötig).
--
-- UNTERSCHIED zu RAW→DISC:
--   - Kein LEFT JOIN auf KEY-Tabelle: SK_SOURCE=STAGING → src.${SK_COLUMN} direkt
--   - VALID_FROM   → ${GUELTIGVON_COL}  (z.B. REUS_GUELTIGVON)
--   - VALID_TO     → ${GUELTIGBIS_COL}  (z.B. REUS_GUELTIGBIS)
--   - IS_CURRENT   → ${IST_AKTUELL_COL} (z.B. REUS_IST_AKTUELL)
--
-- PARAMETER:
--   ${TARGET_DATABASE}    : REUS-Datenbank          (z.B. MDP01_REUSABLE_LAYER)
--   ${TARGET_TABLE}       : REUS-Zieltabelle         (z.B. PART_PERSON)
--   ${NEW_RECORDS_TABLE}  : Input-VT                 (temp_*_new oder temp_*_changed)
--   ${INSERT_COLUMNS}     : Spalten-Liste für INSERT  (generiert)
--   ${SELECT_COLUMNS}     : SELECT-Liste mit src.     (generiert)
--   ${HASH_EXPRESSION}    : HASHROW()-Ausdruck        (generiert, TABLE_ALIAS='src')
--   ${SK_COLUMN}          : SK-Spaltenname            (z.B. PART_PERSON_SK)
--   ${GUELTIGVON_COL}     : Gültig-Von Spalte         (z.B. REUS_GUELTIGVON)
--   ${GUELTIGBIS_COL}     : Gültig-Bis Spalte         (z.B. REUS_GUELTIGBIS)
--   ${IST_AKTUELL_COL}    : Aktuell-Flag Spalte       (z.B. REUS_IST_AKTUELL)
--   ${IST_AKTUELL_VAL}    : Aktuell-Flag Wert         (z.B. J)
-- ============================================================================

INSERT INTO ${TARGET_DATABASE}.${TARGET_TABLE}
(
    ${INSERT_COLUMNS},
    ${GUELTIGVON_COL},
    ${GUELTIGBIS_COL},
    ${IST_AKTUELL_COL},
    RECORD_HASH,
    CREATED_TIMESTAMP,
    LAST_UPDATED_TIMESTAMP,
    CREATED_BY,
    LAST_UPDATED_BY
)
SELECT
    ${SELECT_COLUMNS},
    CURRENT_TIMESTAMP(6)                      AS ${GUELTIGVON_COL},
    TIMESTAMP '9999-12-31 23:59:59.999999'    AS ${GUELTIGBIS_COL},
    '${IST_AKTUELL_VAL}'                      AS ${IST_AKTUELL_COL},
    ${HASH_EXPRESSION}                        AS RECORD_HASH,
    CURRENT_TIMESTAMP(6)                      AS CREATED_TIMESTAMP,
    CURRENT_TIMESTAMP(6)                      AS LAST_UPDATED_TIMESTAMP,
    USER                                      AS CREATED_BY,
    USER                                      AS LAST_UPDATED_BY
FROM ${NEW_RECORDS_TABLE} src;
