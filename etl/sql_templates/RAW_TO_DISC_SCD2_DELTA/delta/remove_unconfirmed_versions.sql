-- ============================================================================
-- TEMPLATE: Remove Unconfirmed Versions (SCD2 aus RAW-Deltas)
-- ============================================================================
-- Entfernt Versionen, deren Ladelauf über dem bestätigten Ladestand liegt.
-- Solche Versionen stammen aus einem abgebrochenen Lauf: Der Orchestrator
-- committet nach jedem Step, der Ladestand rückt aber erst im letzten Step vor.
-- Der folgende Lauf verarbeitet dieselben Ladeläufe erneut und baut diese
-- Versionen deterministisch neu auf.
--
-- PARAMETER:
--   ${TARGET_DATABASE}  : Target Database
--   ${TARGET_TABLE}     : Target History-Tabelle
--   ${DWH_LOAD_ID_COL}  : Zielspalte mit dem Ladelauf der Version
--   ${LOAD_WATERMARK}   : Ausdruck für den bestätigten Ladestand (generiert)
-- ============================================================================

DELETE FROM ${TARGET_DATABASE}.${TARGET_TABLE}
WHERE ${DWH_LOAD_ID_COL} > ${LOAD_WATERMARK};
