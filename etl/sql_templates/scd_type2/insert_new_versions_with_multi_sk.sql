-- ============================================================================
-- TEMPLATE: Insert New Versions with Multiple Surrogate Key Lookups (SCD Type 2)
-- ============================================================================
-- Speziell für Tabellen mit MEHREREN Surrogate Keys (z.B. IDENTITAET → IDENTITAET_SK + PERSON_SK)
-- 
-- Jaffle Pattern: Beide SKs werden zur Laufzeit per JOIN aus KEY-Tabellen geholt.
--
-- PARAMETER:
--   ${TARGET_DATABASE}       : Target Database
--   ${TARGET_TABLE}          : Target History-Tabelle
--   ${NEW_RECORDS_TABLE}     : Temp-Tabelle mit Records
--   ${INSERT_COLUMNS}        : Spalten-Liste für INSERT (generiert)
--   ${SELECT_COLUMNS}        : SELECT-Liste mit Alias 'src.' (generiert)
--   ${HASH_EXPRESSION}       : HASHROW-Expression (generiert)
--   
--   -- Primary SK (für diese Entität selbst)
--   ${KEY_DATABASE}          : Key-Datenbank (z.B. MDP01_META)
--   ${KEY_TABLE}             : Key-Tabelle (z.B. KEY_IDENTITAET)
--   ${NATURAL_KEY_COL}       : Natural Key Spalte (z.B. IDENTITAET_ID)
--   ${DOMAIN}                : Domain für KEY-Lookup (z.B. ZEMIS)
--   ${SK_COLUMN}             : Name der SK-Spalte in Ziel (z.B. IDENTITAET_SK)
--   
--   -- Secondary SK (für referenzierte Entität, z.B. PERSON)
--   ${KEY_DATABASE_2}        : Key-Datenbank 2 (z.B. MDP01_META)
--   ${KEY_TABLE_2}           : Key-Tabelle 2 (z.B. KEY_PERSON)
--   ${NATURAL_KEY_COL_2}     : Natural Key Spalte 2 (z.B. PERSON_ID via ZEMIS_NR Lookup)
--   ${DOMAIN_2}              : Domain für KEY-Lookup 2 (z.B. ZEMIS)
--   ${SK_COLUMN_2}           : Name der SK-Spalte 2 in Ziel (z.B. PERSON_SK)
-- ============================================================================

INSERT INTO ${TARGET_DATABASE}.${TARGET_TABLE}
(
    -- Surrogate Keys (aus KEY-Tabellen, NICHT aus Quelle!)
    ${SK_COLUMN},
    ${SK_COLUMN_2},
    
    -- Business Columns
    ${INSERT_COLUMNS},
    
    -- SCD Type 2 Fields
    VALID_FROM,
    VALID_TO,
    IS_CURRENT,
    
    -- DWH Technical Fields
    RECORD_HASH,
    CREATED_TIMESTAMP,
    LAST_UPDATED_TIMESTAMP,
    CREATED_BY,
    LAST_UPDATED_BY
)
SELECT
    -- Primary SK aus KEY-Tabelle 1
    COALESCE(k1.SURROGATE_KEY, -1) AS ${SK_COLUMN},
    
    -- Secondary SK aus KEY-Tabelle 2
    COALESCE(k2.SURROGATE_KEY, -1) AS ${SK_COLUMN_2},
    
    -- Business Columns
    ${SELECT_COLUMNS},
    
    -- SCD Type 2 Fields
    CURRENT_TIMESTAMP(6) AS VALID_FROM,
    TIMESTAMP '9999-12-31 23:59:59.999999' AS VALID_TO,
    'Y' AS IS_CURRENT,
    
    -- DWH Technical Fields
    ${HASH_EXPRESSION} AS RECORD_HASH,
    CURRENT_TIMESTAMP(6) AS CREATED_TIMESTAMP,
    CURRENT_TIMESTAMP(6) AS LAST_UPDATED_TIMESTAMP,
    USER AS CREATED_BY,
    USER AS LAST_UPDATED_BY

FROM ${NEW_RECORDS_TABLE} src

-- JOIN 1: Primary SK (z.B. IDENTITAET_SK)
LEFT JOIN ${KEY_DATABASE}.${KEY_TABLE} k1
    ON CAST(src.${NATURAL_KEY_COL} AS VARCHAR(255)) = k1.NATURAL_KEY_VALUE
   AND k1.NATURAL_KEY_DOMAIN = '${DOMAIN}'

-- JOIN 2: Secondary SK (z.B. PERSON_SK)
-- Hinweis: Hier wird PERSON_ID aus IDENTITAET auf ZEMIS_NR in KEY_PERSON gemappt
-- Das funktioniert NUR wenn PERSON_ID in IDENTITAET === ZEMIS_NR Referenz ist!
-- Falls nicht: Subquery über TAAA_PERSON für Mapping nötig
LEFT JOIN ${KEY_DATABASE_2}.${KEY_TABLE_2} k2
    ON CAST(src.${NATURAL_KEY_COL_2} AS VARCHAR(255)) = k2.NATURAL_KEY_VALUE
   AND k2.NATURAL_KEY_DOMAIN = '${DOMAIN_2}';

-- Hinweis: LEFT JOINs + COALESCE(-1) → Records werden auch ohne Key geladen
