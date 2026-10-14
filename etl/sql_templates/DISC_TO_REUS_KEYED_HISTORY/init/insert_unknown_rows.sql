-- ============================================================================
-- TEMPLATE: Insert Unknown Rows (Zeile für "keine Angabe")
-- ============================================================================
-- Legt die festen Zeilen mit SK -1 an, falls sie fehlen (idempotent). Die
-- Werte (z.B. Texte je Sprache) kommen aus den Job-Parametern; die Zeile
-- gilt ab dem Beginn des initialen Stands und ist offen.
--
-- PARAMETER:
--   ${TARGET_DATABASE}, ${TARGET_TABLE}
--   ${UNKNOWN_COLUMNS}  : Spaltenliste
--   ${UNKNOWN_ROWS}     : SELECT ... [UNION ALL SELECT ...] mit den Werten (generiert)
--   ${UNKNOWN_MATCH}    : Vergleich t.<Schlüssel> = u.<Schlüssel> (generiert)
-- ============================================================================

INSERT INTO ${TARGET_DATABASE}.${TARGET_TABLE} (${UNKNOWN_COLUMNS})
SELECT ${UNKNOWN_COLUMNS_U}
FROM (${UNKNOWN_ROWS}) u
WHERE NOT EXISTS (
    SELECT 1 FROM ${TARGET_DATABASE}.${TARGET_TABLE} t
    WHERE ${UNKNOWN_MATCH}
);
