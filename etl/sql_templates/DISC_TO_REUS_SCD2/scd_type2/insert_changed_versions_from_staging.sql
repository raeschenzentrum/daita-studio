-- ============================================================================
-- TEMPLATE: Insert Changed Versions from Staging (SCD Type 2) — DISC TO REUS
-- ============================================================================
-- Fügt geänderte Versionen ein. SK kommt direkt aus der Staging-Tabelle
-- (wird bereits durch die DISC Business View mitgeliefert — kein KEY-Join nötig).
--
-- IDENTISCH zu insert_new_versions_from_staging.sql, ABER Quelle ist die
-- CHANGED-VT (${CHANGED_RECORDS_TABLE}) statt der NEW-VT. Notwendig, weil der
-- Generator NEW_RECORDS_TABLE fix auf temp_*_new setzt und der "Insert Changed"
-- Step die temp_*_changed-Tabelle braucht.
--
-- PARAMETER:
--   ${TARGET_DATABASE}       : REUS-Datenbank          (z.B. MDP01_REUSABLE_LAYER)
--   ${TARGET_TABLE}          : REUS-Zieltabelle         (z.B. PART_PERSON)
--   ${CHANGED_RECORDS_TABLE} : Input-VT                 (temp_*_changed)
--   ${INSERT_COLUMNS}        : Spalten-Liste für INSERT  (generiert)
--   ${SELECT_COLUMNS}        : SELECT-Liste mit src.     (generiert)
--   ${HASH_EXPRESSION}       : HASHROW()-Ausdruck        (generiert, TABLE_ALIAS='src')
--   ${SK_COLUMN}             : SK-Spaltenname            (z.B. PART_PERSON_SK)
--   ${GUELTIGVON_COL}        : Gültig-Von Spalte         (z.B. REUS_GUELTIGVON)
--   ${GUELTIGBIS_COL}        : Gültig-Bis Spalte         (z.B. REUS_GUELTIGBIS)
--   ${IST_AKTUELL_COL}       : Aktuell-Flag Spalte       (z.B. REUS_IST_AKTUELL)
--   ${IST_AKTUELL_VAL}       : Aktuell-Flag Wert         (z.B. J)
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
FROM ${CHANGED_RECORDS_TABLE} src;
