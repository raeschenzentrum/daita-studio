-- ============================================================================
-- TEMPLATE: generate_surrogate_keys.sql
-- ============================================================================
-- Jaffle Pattern: Generiert neue Surrogate Keys für Natural Keys die noch 
--                 nicht in der Key-Tabelle existieren.
--
-- Wird als PRE-HOOK vor Light Integration (DISCOVERABLE Layer) ausgeführt.
--
-- Parameter:
--   ${SOURCE_TABLE}     - Quelltabelle mit Natural Keys (z.B. SIM_TAAA_PERSON)
--   ${SOURCE_DATABASE}  - Quell-Datenbank (z.B. MDP01_RAW_LAYER)
--   ${KEY_TABLE}        - Ziel Key-Tabelle (z.B. KEY_PERSON)
--   ${KEY_DATABASE}     - Key-Datenbank (z.B. MDP01_META)
--   ${NATURAL_KEY_COL}      - Erste PK-Spalte (für NULL-Check; bei Composite Key alle Teile in NATURAL_KEY_EXPRESSION_SRC)
--   ${NATURAL_KEY_EXPRESSION_SRC} - SQL-Ausdruck für Natural Key Lookup (generiert)
--                            Single:    CAST(src.PERSON_ID AS VARCHAR(255))
--                            Composite: TRIM(CAST(src.COL1 AS VARCHAR(100))) || '~|~' || TRIM(CAST(src.COL2 AS VARCHAR(100)))
--   ${DOMAIN}               - Domain-Identifier (z.B. ZEMIS)
--
-- Algorithmus:
--   1. Finde alle Natural Keys in Quelle die noch nicht in Key-Tabelle sind
--   2. Generiere neue Surrogate Keys via DENSE_RANK (startend nach MAX)
--   3. INSERT in Key-Tabelle (in einer Transaktion für Thread-Safety)
--
-- Hinweis: DENSE_RANK statt IDENTITY für:
--   - Parallelitäts-Sicherheit
--   - Portabilität
--   - Restore/Recovery-Fähigkeit
-- ============================================================================

-- Step 1: Generiere neue Keys in einer Transaktion (Thread-Safe!)
INSERT INTO ${KEY_DATABASE}.${KEY_TABLE} (
    SURROGATE_KEY,
    NATURAL_KEY_VALUE,
    NATURAL_KEY_DOMAIN,
    NATURAL_KEY_HASH,
    CREATED_TIMESTAMP,
    CREATED_BY
)
SELECT 
    -- DENSE_RANK über alle neuen Keys, startend nach MAX existierendem Key
    COALESCE(
        (SELECT MAX(SURROGATE_KEY) FROM ${KEY_DATABASE}.${KEY_TABLE}), 
        0
    ) + DENSE_RANK() OVER (ORDER BY src.natural_key),
    
    src.natural_key,
    '${DOMAIN}',
    
    -- Hash für schnellen Lookup
    HASHROW(src.natural_key),
    
    CURRENT_TIMESTAMP(6),
    'ETL_KEY_GEN'
    
FROM (
    -- Nur neue Natural Keys die noch nicht in Key-Tabelle sind
    SELECT DISTINCT ${NATURAL_KEY_EXPRESSION_SRC} AS natural_key
    FROM ${SOURCE_DATABASE}.${SOURCE_TABLE} src
    WHERE ${NATURAL_KEY_EXPRESSION_SRC} NOT IN (
        SELECT NATURAL_KEY_VALUE 
        FROM ${KEY_DATABASE}.${KEY_TABLE}
        WHERE NATURAL_KEY_DOMAIN = '${DOMAIN}'
    )
) src;

-- Logging: Wie viele Keys wurden generiert?
-- SELECT COUNT(*) FROM ${KEY_DATABASE}.${KEY_TABLE} WHERE CREATED_TIMESTAMP > CURRENT_TIMESTAMP - INTERVAL '1' MINUTE;
