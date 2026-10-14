-- ============================================================================
-- TEMPLATE: Create Delta Staging Table (Reusable mit eigener Historie)
-- ============================================================================
-- Liest aus der Quell-View nur Versionen, die seit dem letzten Lauf entstanden
-- (Ladelauf > Ladestand) oder geändert wurden (geschlossen bzw. als gelöscht
-- markiert: Änderungs-Ladelauf > Ladestand). Obergrenze ist der kleinste
-- bestätigte Ladestand der vorgelagerten Jobs: So entsteht kein Ladestand
-- über einem Lauf, den eine der Quellen noch nicht geladen hat.
-- Die Business-Logik (Zuschnitt, Namen, Integration) steckt in der View;
-- dieses Template ist nur die technische Historisierung.
--
-- PARAMETER:
--   ${SOURCE_DATABASE}, ${SOURCE_TABLE} : Quell-View
--   ${STAGING_TABLE}                    : Volatile Tabelle
--   ${STG_SELECT}                       : Fachspalten der View (generiert, Alias src)
--   ${SRC_VALID_FROM}, ${SRC_VALID_TO}, ${SRC_DELETED},
--   ${SRC_LOAD_ID}, ${SRC_UPDATE_LOAD_ID} : Versionsspalten der View
--   ${HASH_EXPRESSION}, ${STG_HASH}     : Hash über die Fachspalten (generiert)
--   ${LOAD_WATERMARK}, ${LOAD_CAP}      : Ladestand, Obergrenze (generiert)
--   ${BUSINESS_KEY}                     : Business Key der View
-- ============================================================================

CREATE MULTISET VOLATILE TABLE ${STAGING_TABLE} AS (
    SELECT
        ${STG_SELECT},
        src.${SRC_VALID_FROM},
        src.${SRC_VALID_TO},
        src.${SRC_DELETED},
        src.${SRC_LOAD_ID},
        src.${SRC_UPDATE_LOAD_ID},
        ${HASH_EXPRESSION} AS ${STG_HASH}
    FROM ${SOURCE_DATABASE}.${SOURCE_TABLE} src
    WHERE (src.${SRC_LOAD_ID} > ${LOAD_WATERMARK} AND src.${SRC_LOAD_ID} <= ${LOAD_CAP})
       OR (src.${SRC_UPDATE_LOAD_ID} > ${LOAD_WATERMARK} AND src.${SRC_UPDATE_LOAD_ID} <= ${LOAD_CAP})
) WITH DATA
PRIMARY INDEX (${BUSINESS_KEY})
ON COMMIT PRESERVE ROWS;
