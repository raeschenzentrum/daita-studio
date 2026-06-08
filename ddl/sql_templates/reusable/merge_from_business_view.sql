-- ============================================================================
-- Template: merge_from_business_view.sql
-- ============================================================================
-- Zweck: Incremental MERGE von Business View in REUSABLE Layer Tabelle
-- Pattern: SCD Type 2 (Full History) aus DISCOVERABLE nach REUSABLE
-- 
-- Die Business View enthält bereits die fachlichen Transformationen.
-- Dieses Template fügt nur die technische SCD-Mechanik hinzu.
-- 
-- Parameter:
--   ${SOURCE_VIEW}         - Voll qualifizierte Business View
--   ${TARGET_DATABASE}     - Ziel-Datenbank
--   ${TARGET_TABLE}        - Ziel-Tabelle (ohne DB)
--   ${BUSINESS_KEY}        - Business Key Spalte (z.B. PERSON_ID)
--   ${SURROGATE_KEY}       - SK Spalte in Ziel (z.B. PART_PERSON_SK)
--   ${SOURCE_SK_COLUMN}    - SK Spalte in View (z.B. PART_PERSON_KEY)
--   ${ROW_KEY}             - Row Key (IDENTITY, z.B. PART_PERSON_ROW_ID)
--   ${INSERT_COLUMNS}      - Spalten-Liste für INSERT (aus Metadaten)
--   ${SELECT_COLUMNS}      - SELECT-Liste mit src. Prefix (aus Metadaten)
--
-- Hinweis: ETL_JOB_RUN_ID wird mit -1 als Platzhalter gesetzt.
--          Das ETL-Framework ersetzt dies zur Laufzeit mit der aktuellen Job Run ID.
-- ============================================================================

-- Incremental Load: Nur neue/geänderte Records seit letztem Load
-- Prüft ob Record bereits existiert (via Business Key + VALID_FROM)

INSERT INTO ${TARGET_DATABASE}.${TARGET_TABLE} (
    ${SURROGATE_KEY},
    ${INSERT_COLUMNS},
    -- SCD Type 2 Fields (bereits aus View)
    VALID_FROM,
    VALID_TO,
    IS_CURRENT,
    -- Audit Fields
    CREATED_TIMESTAMP,
    LAST_UPDATED_TIMESTAMP,
    ETL_JOB_RUN_ID
)
SELECT 
    COALESCE(src.${SOURCE_SK_COLUMN}, -1) AS ${SURROGATE_KEY},
    ${SELECT_COLUMNS},
    -- SCD Type 2 Fields
    src.VALID_FROM,
    src.VALID_TO,
    src.IS_CURRENT,
    -- Audit Fields
    CURRENT_TIMESTAMP(6),
    CURRENT_TIMESTAMP(6),
    COALESCE(${ETL_JOB_RUN_ID}, -1)
FROM ${SOURCE_VIEW} src
LEFT JOIN ${TARGET_DATABASE}.${TARGET_TABLE} tgt
    ON src.${BUSINESS_KEY} = tgt.${BUSINESS_KEY}
   AND src.VALID_FROM = tgt.VALID_FROM
WHERE tgt.${ROW_KEY} IS NULL;  -- Nur neue Records (die noch nicht existieren)
