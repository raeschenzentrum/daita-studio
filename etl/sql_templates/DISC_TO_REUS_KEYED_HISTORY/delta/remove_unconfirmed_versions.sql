-- ============================================================================
-- TEMPLATE: Remove Unconfirmed Versions (Reusable mit eigener Historie)
-- ============================================================================
-- Entfernt Versionen, deren Ladelauf (Ladelauf der Quell-Version im
-- Discoverable) über dem bestätigten Ladestand liegt. Sie stammen aus einem
-- abgebrochenen Lauf: Der Orchestrator committet nach jedem Step, der
-- Ladestand rückt erst im letzten Step vor. Der folgende Lauf verarbeitet
-- dieselben Ladeläufe erneut. Vorgänger, die der abgebrochene Lauf schon
-- geschlossen oder verlängert hat, bekommen im erneuten Lauf dieselben Werte.
-- Zeilen ohne Ladelauf (z.B. die Zeile -1) bleiben.
--
-- PARAMETER:
--   ${TARGET_DATABASE}, ${TARGET_TABLE}
--   ${TGT_LOAD_ID_COL}   : Ladelauf der Version
--   ${LOAD_WATERMARK}    : bestätigter Ladestand (generiert)
-- ============================================================================

DELETE FROM ${TARGET_DATABASE}.${TARGET_TABLE}
WHERE ${TGT_LOAD_ID_COL} > ${LOAD_WATERMARK};
