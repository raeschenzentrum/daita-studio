-- ============================================================================
-- TEMPLATE: Build Versions (Reusable mit eigener Historie)
-- ============================================================================
-- Bildet aus den Delta-Zeilen die Reusable-Versionen. Die Zeitpunkte kommen
-- unverändert aus der Quelle (Gültigkeit der Discoverable-Version), nie aus der
-- Ladezeit. Weil der Gültigkeitsbeginn im Discoverable monoton wächst, setzt
-- jede Delta-Zeile am Ende der Zeitachse an (keine rückdatierten Versionen).
--
-- Je Zielschlüssel, in der Reihenfolge SEQ_NO:
--   IS_KEPT = 1  beginnt eine neue Reusable-Version: es gibt noch keine
--                (L = letzte Version im Ziel fehlt), L bzw. die vorige Zeile
--                ist in der Quelle gelöscht, oder der Hash ändert sich
--   IS_KEPT = 0  setzt die vorige Version fort (gleicher Hash, z.B. dieselbe
--                Discoverable-Version, die jetzt geschlossen wurde, oder eine
--                Änderung nur in Spalten, die das Reusable nicht führt)
--   RUN_NO       laufende Nummer der Version im Delta; 0 = Fortsetzung von L
--
-- PARAMETER:
--   ${KEYED_TABLE}, ${VERSIONS_TABLE}, ${TARGET_DATABASE}, ${TARGET_TABLE}
--   ${SK_COLUMN}, ${PART_KEY_R}, ${JOIN_KEY_S_P}, ${JOIN_KEY_S_L},
--   ${TGT_KEY_COLS_T}, ${PART_KEY_T} (generiert)
--   ${SRC_VALID_FROM}, ${SRC_DELETED}, ${STG_HASH}, ${DELETED_VAL}
--   ${TGT_VALID_FROM_COL}, ${TGT_VALID_TO_COL}, ${TGT_DELETED_COL}, ${TGT_HASH_COL}
-- ============================================================================

CREATE MULTISET VOLATILE TABLE ${VERSIONS_TABLE} AS (
    SELECT
        r.*,
        SUM(r.IS_KEPT) OVER (
            PARTITION BY ${PART_KEY_R} ORDER BY r.SEQ_NO ROWS UNBOUNDED PRECEDING
        ) AS RUN_NO
    FROM (
        SELECT
            s.*,
            l.L_VALID_FROM,
            l.L_VALID_TO,
            CASE
                WHEN s.SEQ_NO = 1 AND l.L_VALID_FROM IS NULL THEN 1
                WHEN s.SEQ_NO = 1 AND s.${SRC_VALID_FROM} = l.L_VALID_FROM THEN 0
                WHEN s.SEQ_NO = 1 AND l.L_DELETED = '${DELETED_VAL}' THEN 1
                WHEN s.SEQ_NO = 1 AND s.${STG_HASH} <> l.L_HASH THEN 1
                WHEN s.SEQ_NO = 1 THEN 0
                WHEN p.${SRC_DELETED} = '${DELETED_VAL}' THEN 1
                WHEN s.${STG_HASH} <> p.${STG_HASH} THEN 1
                ELSE 0
            END AS IS_KEPT
        FROM ${KEYED_TABLE} s
        LEFT JOIN ${KEYED_TABLE} p
          ON ${JOIN_KEY_S_P}
         AND p.SEQ_NO = s.SEQ_NO - 1
        LEFT JOIN (
            SELECT
                ${TGT_KEY_COLS_T},
                t.${TGT_VALID_FROM_COL} AS L_VALID_FROM,
                t.${TGT_VALID_TO_COL}   AS L_VALID_TO,
                t.${TGT_DELETED_COL}    AS L_DELETED,
                t.${TGT_HASH_COL}       AS L_HASH
            FROM ${TARGET_DATABASE}.${TARGET_TABLE} t
            WHERE t.${SK_COLUMN} <> -1
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY ${PART_KEY_T} ORDER BY t.${TGT_VALID_FROM_COL} DESC
            ) = 1
        ) l
          ON ${JOIN_KEY_S_L}
    ) r
) WITH DATA
PRIMARY INDEX (${SK_COLUMN})
ON COMMIT PRESERVE ROWS;
