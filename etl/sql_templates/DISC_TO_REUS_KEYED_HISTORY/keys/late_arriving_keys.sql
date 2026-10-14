-- ============================================================================
-- TEMPLATE: Late Arriving Keys (Verweise auf noch unbekannte Keys)
-- ============================================================================
-- Für jeden Verweis (FK) der Rolle: Natural Keys aus der Staging-Tabelle, die
-- in der KEY-Tabelle des Ziels fehlen, dort eintragen (neue SK, CREATED_BY =
-- Job). Danach findet der Insert jeden Verweis mit Wert; -1 bleibt für NULL.
-- Die Zeile im Ziel entsteht erst, wenn der Key dort aus der Quelle ankommt.
-- Je KEY-Tabelle ein INSERT (mehrere Verweise auf dieselbe Tabelle gebündelt).
--
-- PARAMETER:
--   ${LATE_ARRIVING_INSERTS} : INSERT-Anweisungen je KEY-Tabelle (generiert
--                              aus keys/late_arriving_key.part)
-- ============================================================================

${LATE_ARRIVING_INSERTS}
