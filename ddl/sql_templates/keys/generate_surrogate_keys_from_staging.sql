-- ============================================================================
-- TEMPLATE: generate_surrogate_keys_from_staging.sql
-- ============================================================================
-- Jaffle Pattern: Generiert neue Surrogate Keys aus VOLATILE Staging Table.
--
-- WICHTIG: Dieses Template nutzt die bereits erstellte Volatile Staging Table
--          (temp_*_staging) anstatt direkt aus der Quelltabelle zu lesen.
--          → Dieselben Daten, keine doppelten Ressourcen!
--
-- Ausführung: Als Step 2 NACH create_staging_table.sql, VOR SCD2 Steps
--
-- Parameter:
--   ${STAGING_TABLE}    - Name der existierenden VT (z.B. temp_taaa_person_staging)
--   ${KEY_DATABASE}     - Key-Datenbank (z.B. MDP01_META)
--   ${KEY_TABLE}        - Ziel Key-Tabelle (z.B. KEY_PERSON)
--   ${NATURAL_KEY_COL}  - Erste PK-Spalte (für NOT NULL Check)
--   ${NATURAL_KEY_EXPRESSION_STG} - SQL-Ausdruck für Natural Key Lookup (generiert)
--                         Single:    CAST(stg.PERSON_ID AS VARCHAR(255))
--                         Composite: TRIM(CAST(stg.COL1 AS VARCHAR(100))) || '~|~' || TRIM(CAST(stg.COL2 AS VARCHAR(100)))
--   ${DOMAIN}           - Domain-Identifier (z.B. ZEMIS)
--
-- Algorithmus:
--   1. Lese DISTINCT Natural Keys aus existierender Volatile Staging Table
--   2. Filtere nur Keys die noch nicht in Key-Tabelle existieren
--   3. Generiere neue Surrogate Keys via DENSE_RANK (startend nach MAX)
--   4. INSERT in Key-Tabelle
--
-- Thread-Safety: DENSE_RANK in einer Transaktion gewährleistet Konsistenz
-- ============================================================================

-- Generiere neue Surrogate Keys für Natural Keys aus Staging
INSERT INTO ${KEY_DATABASE}.${KEY_TABLE} (
    SURROGATE_KEY,
    NATURAL_KEY_VALUE,
    NATURAL_KEY_DOMAIN,
    NATURAL_KEY_HASH,
    CREATED_TIMESTAMP,
    CREATED_BY
)
SELECT 
    -- Neuer SK = MAX existierender SK + DENSE_RANK über neue Keys
    COALESCE(
        (SELECT MAX(SURROGATE_KEY) FROM ${KEY_DATABASE}.${KEY_TABLE}), 
        0
    ) + DENSE_RANK() OVER (ORDER BY src.natural_key),
    
    src.natural_key,
    '${DOMAIN}',
    
    -- Hash für schnellen Lookup (Teradata HASHROW Funktion)
    HASHROW(src.natural_key),
    
    CURRENT_TIMESTAMP(6),
    'ETL_KEY_GEN_${DOMAIN}'
    
FROM (
    -- DISTINCT Natural Keys aus der bereits existierenden Staging Table
    -- die noch NICHT in der Key-Tabelle vorhanden sind
    SELECT DISTINCT 
        ${NATURAL_KEY_EXPRESSION_STG} AS natural_key
    FROM ${STAGING_TABLE} stg
    WHERE stg.${NATURAL_KEY_COL} IS NOT NULL
      AND ${NATURAL_KEY_EXPRESSION_STG} NOT IN (
          SELECT k.NATURAL_KEY_VALUE 
          FROM ${KEY_DATABASE}.${KEY_TABLE} k
          WHERE k.NATURAL_KEY_DOMAIN = '${DOMAIN}'
      )
) src;

-- Optional: Log-Statement für Monitoring (kann aktiviert werden)
-- SELECT 
--     '${KEY_TABLE}' AS KEY_TABLE,
--     '${DOMAIN}' AS DOMAIN,
--     COUNT(*) AS KEYS_GENERATED,
--     CURRENT_TIMESTAMP AS GENERATED_AT
-- FROM ${KEY_DATABASE}.${KEY_TABLE} 
-- WHERE CREATED_TIMESTAMP > CURRENT_TIMESTAMP - INTERVAL '1' MINUTE
--   AND NATURAL_KEY_DOMAIN = '${DOMAIN}';
