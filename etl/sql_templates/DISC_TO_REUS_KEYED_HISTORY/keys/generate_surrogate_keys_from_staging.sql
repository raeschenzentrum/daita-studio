-- ============================================================================
-- TEMPLATE: Generate Surrogate Keys (Natural Key -> SK in der KEY-Tabelle)
-- ============================================================================
-- Trägt neue Natural Keys aus der Staging-Tabelle in die KEY-Tabelle ein.
-- Mehrere Rollen eines Jobs (z.B. Code- und Texttabelle) teilen sich die
-- KEY-Tabelle; vorhandene Keys behalten ihre SK. Neue SK = MAX + DENSE_RANK
-- (nicht parallel-sicher: Jobs auf derselben KEY-Tabelle nacheinander).
--
-- PARAMETER:
--   ${STAGING_TABLE}, ${KEY_DATABASE}, ${KEY_TABLE}, ${DOMAIN}
--   ${NATURAL_KEY_COL}, ${NATURAL_KEY_EXPRESSION_STG}
-- ============================================================================

INSERT INTO ${KEY_DATABASE}.${KEY_TABLE} (
    SURROGATE_KEY,
    NATURAL_KEY_VALUE,
    NATURAL_KEY_DOMAIN,
    NATURAL_KEY_HASH,
    CREATED_TIMESTAMP,
    CREATED_BY
)
SELECT
    COALESCE((SELECT MAX(SURROGATE_KEY) FROM ${KEY_DATABASE}.${KEY_TABLE}), 0)
        + DENSE_RANK() OVER (ORDER BY src.natural_key),
    src.natural_key,
    '${DOMAIN}',
    HASHROW(src.natural_key),
    CURRENT_TIMESTAMP(6),
    'ETL_KEY_GEN_${DOMAIN}'
FROM (
    SELECT DISTINCT ${NATURAL_KEY_EXPRESSION_STG} AS natural_key
    FROM ${STAGING_TABLE} stg
    WHERE stg.${NATURAL_KEY_COL} IS NOT NULL
      AND ${NATURAL_KEY_EXPRESSION_STG} NOT IN (
          SELECT k.NATURAL_KEY_VALUE FROM ${KEY_DATABASE}.${KEY_TABLE} k
          WHERE k.NATURAL_KEY_DOMAIN = '${DOMAIN}'
      )
) src;
