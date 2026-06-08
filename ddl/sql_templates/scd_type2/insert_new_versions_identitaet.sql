-- ============================================================================
-- TEMPLATE: Insert New Versions for TAAA_IDENTITAET with Double SK Lookup
-- ============================================================================
-- Speziell für TAAA_IDENTITAET_HISTORY, die ZWEI Surrogate Keys braucht:
--   1. IDENTITAET_SK (Natural Key: IDENTITAET_ID → KEY_IDENTITAET)
--   2. PERSON_SK     (Natural Key: PERSON_ID → KEY_PERSON via ZEMIS_NR Mapping)
--
-- ACHTUNG: PERSON_ID in IDENTITAET ≠ ZEMIS_NR!
--          Wir müssen über TAAA_PERSON joinen um PERSON_ID → ZEMIS_NR zu mappen.
-- 
-- PARAMETER:
--   ${TARGET_DATABASE}         : MDP01_DISCOVERABLE_LAYER
--   ${TARGET_TABLE}            : TAAA_IDENTITAET_HISTORY
--   ${NEW_RECORDS_TABLE}       : temp_new_records oder temp_changed_records
--   ${INSERT_COLUMNS}          : Business-Spalten
--   ${SELECT_COLUMNS}          : SELECT mit 'src.' Prefix
--   ${HASH_EXPRESSION}         : HASHROW Expression
--   ${KEY_DATABASE}            : MDP01_META
--   ${KEY_TABLE_IDENTITAET}    : KEY_IDENTITAET
--   ${KEY_TABLE_PERSON}        : KEY_PERSON
--   ${PERSON_TABLE}            : MDP01_RAW_LAYER.TAAA_PERSON
--   ${DOMAIN}                  : ZEMIS
-- ============================================================================

INSERT INTO ${TARGET_DATABASE}.${TARGET_TABLE}
(
    -- Surrogate Keys (aus KEY-Tabellen)
    IDENTITAET_SK,
    PERSON_SK,
    
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
    -- IDENTITAET_SK: Direkt aus KEY_IDENTITAET (IDENTITAET_ID)
    COALESCE(k_ident.SURROGATE_KEY, -1) AS IDENTITAET_SK,
    
    -- PERSON_SK: Über TAAA_PERSON.ZEMIS_NR → KEY_PERSON
    COALESCE(person_sk_map.PERSON_SK, -1) AS PERSON_SK,
    
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

-- JOIN 1: IDENTITAET_SK direkt aus KEY_IDENTITAET
LEFT JOIN ${KEY_DATABASE}.${KEY_TABLE_IDENTITAET} k_ident
    ON CAST(src.IDENTITAET_ID AS VARCHAR(255)) = k_ident.NATURAL_KEY_VALUE
   AND k_ident.NATURAL_KEY_DOMAIN = '${DOMAIN}'

-- JOIN 2: PERSON_SK über TAAA_PERSON (PERSON_ID → ZEMIS_NR → KEY_PERSON)
-- Subquery: Mappt PERSON_ID auf den entsprechenden PERSON_SK
LEFT JOIN (
    SELECT p.PERSON_ID, kp.SURROGATE_KEY AS PERSON_SK
    FROM ${PERSON_TABLE} p
    INNER JOIN ${KEY_DATABASE}.${KEY_TABLE_PERSON} kp
        ON CAST(p.ZEMIS_NR AS VARCHAR(255)) = kp.NATURAL_KEY_VALUE
       AND kp.NATURAL_KEY_DOMAIN = '${DOMAIN}'
    -- Bei mehreren Versionen in TAAA_PERSON: Nur eine nehmen (alle haben gleiche ZEMIS_NR)
    QUALIFY ROW_NUMBER() OVER (PARTITION BY p.PERSON_ID ORDER BY p.PERSON_ID) = 1
) person_sk_map
    ON src.PERSON_ID = person_sk_map.PERSON_ID;

-- Hinweis: COALESCE auf -1 ist bereits im SELECT für PERSON_SK
