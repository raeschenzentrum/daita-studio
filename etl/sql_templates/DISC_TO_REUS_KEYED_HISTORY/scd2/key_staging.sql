-- ============================================================================
-- TEMPLATE: Key Staging (SK zuordnen, Reihenfolge je Schlüssel)
-- ============================================================================
-- Ergänzt die Delta-Zeilen um die SK aus der KEY-Tabelle und nummeriert sie je
-- Zielschlüssel (SK + übrige Business-Key-Spalten) nach Gültigkeitsbeginn.
-- Die Nummer ersetzt LAG (Teradata erlaubt LAG nicht auf BYTE-Spalten).
--
-- PARAMETER:
--   ${STAGING_TABLE}, ${KEYED_TABLE}
--   ${KEY_DATABASE}, ${KEY_TABLE}, ${DOMAIN}, ${NATURAL_KEY_EXPRESSION_STG}
--   ${SK_COLUMN}, ${PART_KEY_STG} (generiert: k.SURROGATE_KEY[, stg.X]),
--   ${SRC_VALID_FROM}
-- ============================================================================

CREATE MULTISET VOLATILE TABLE ${KEYED_TABLE} AS (
    SELECT
        stg.*,
        k.SURROGATE_KEY AS ${SK_COLUMN},
        ROW_NUMBER() OVER (
            PARTITION BY ${PART_KEY_STG} ORDER BY stg.${SRC_VALID_FROM}
        ) AS SEQ_NO
    FROM ${STAGING_TABLE} stg
    JOIN ${KEY_DATABASE}.${KEY_TABLE} k
      ON ${NATURAL_KEY_EXPRESSION_STG} = k.NATURAL_KEY_VALUE
     AND k.NATURAL_KEY_DOMAIN = '${DOMAIN}'
) WITH DATA
PRIMARY INDEX (${SK_COLUMN})
ON COMMIT PRESERVE ROWS;
