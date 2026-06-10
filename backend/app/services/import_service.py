"""
ImportService – Teradata DBC.TablesV / DBC.ColumnsV → META_TABLE / META_COLUMN

Importiert physische Tabellen aus dem Teradata Data Dictionary in das
META-Schema des daita-modelers.
"""

from collections import defaultdict

import teradatasql
from app.config import DB_CONFIG, META_SCHEMA, META_TABLES

# ---------------------------------------------------------------------------
# IndexType-Code → lesbarer String (DBC.IndicesV)
# ---------------------------------------------------------------------------

_IX_TYPE_MAP: dict[tuple, str] = {
    ("P", "Y"): "UNIQUE PRIMARY INDEX",
    ("P", "N"): "PRIMARY INDEX",
    ("Q", "Y"): "UNIQUE PRIMARY INDEX",   # Partitioned Primary Index
    ("Q", "N"): "PRIMARY INDEX",
    ("K", "Y"): "UNIQUE PRIMARY INDEX",   # PI on SET table
    ("K", "N"): "PRIMARY INDEX",
    ("U", "Y"): "UNIQUE SECONDARY INDEX",
    ("U", "N"): "SECONDARY INDEX",
    ("S", "Y"): "UNIQUE SECONDARY INDEX",
    ("S", "N"): "SECONDARY INDEX",
}

# ---------------------------------------------------------------------------
# Teradata Type-Code → lesbarer String
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    "I":  "INTEGER",    "I1": "BYTEINT",   "I2": "SMALLINT",  "I8": "BIGINT",
    "F":  "FLOAT",      "D":  "DECIMAL",   "N":  "NUMBER",
    "CV": "VARCHAR",    "CF": "CHAR",      "CO": "CLOB",      "BO": "BLOB",
    "BF": "BYTE",       "BV": "VARBYTE",
    "DA": "DATE",       "TS": "TIMESTAMP", "AT": "TIME",
    "TZ": "TIME WITH TIME ZONE",           "SZ": "TIMESTAMP WITH TIME ZONE",
    "YR": "INTERVAL YEAR",                 "YM": "INTERVAL YEAR TO MONTH",
    "MO": "INTERVAL MONTH",                "DY": "INTERVAL DAY",
    "DH": "INTERVAL DAY TO HOUR",          "DM": "INTERVAL DAY TO MINUTE",
    "DS": "INTERVAL DAY TO SECOND",        "HR": "INTERVAL HOUR",
    "HM": "INTERVAL HOUR TO MINUTE",       "HS": "INTERVAL HOUR TO SECOND",
    "MI": "INTERVAL MINUTE",               "MS": "INTERVAL MINUTE TO SECOND",
    "SC": "INTERVAL SECOND",               "UT": "UDT",
}


def _type_str(code: str, length, dec_total, dec_frac) -> str:
    """Konvertiert Teradata Type-Code + Länge/Präzision in lesbaren String."""
    name = _TYPE_MAP.get((code or "").strip(), (code or "").strip())
    if name in ("VARCHAR", "CHAR", "BYTE", "VARBYTE") and length:
        return f"{name}({int(length)})"
    if name in ("DECIMAL", "NUMBER") and dec_total is not None:
        if dec_frac is not None and int(dec_frac) > 0:
            return f"{name}({int(dec_total)},{int(dec_frac)})"
        return f"{name}({int(dec_total)})"
    if name in ("TIMESTAMP", "TIMESTAMP WITH TIME ZONE") and dec_frac is not None:
        return f"{name}({int(dec_frac)})"
    if name in ("TIME", "TIME WITH TIME ZONE") and dec_frac is not None:
        return f"{name}({int(dec_frac)})"
    return name


def _connect():
    return teradatasql.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["username"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
    )


# ---------------------------------------------------------------------------
# Öffentliche Funktionen
# ---------------------------------------------------------------------------

def get_candidates(db_name: str) -> list[dict]:
    """
    Liefert alle Tabellen und Views in DBC.TablesV für db_name.
    Jeder Eintrag enthält das Flag 'in_meta' (True/False), ob die Tabelle
    bereits in META_TABLE eingetragen ist.
    """
    tbl     = f"{META_SCHEMA}.{META_TABLES['tables']}"
    meta_db = f"{META_SCHEMA}.{META_TABLES['database']}"
    try:
        sql = f"""
            SELECT
                t.DatabaseName  AS db_name,
                t.TableName     AS table_name,
                t.TableKind     AS table_kind,
                t.CommentString AS comment_string,
                CASE WHEN m.table_id IS NOT NULL THEN 'Y' ELSE 'N' END AS in_meta
            FROM DBC.TablesV t
            LEFT JOIN {tbl} m
                   ON m.table_name  = t.TableName
                  AND m.database_id = (
                      SELECT database_id FROM {meta_db}
                       WHERE database_name = t.DatabaseName
                  )
            WHERE t.DatabaseName = ?
              AND t.TableKind IN ('T', 'V')
            ORDER BY in_meta ASC, t.TableName
        """
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (db_name,))
                result = []
                for row in cur.fetchall():
                    result.append({
                        "db_name":       str(row[0]),
                        "table_name":    str(row[1]),
                        "table_kind":    str(row[2]),
                        "comment_string": str(row[3]) if row[3] else "",
                        "in_meta":       str(row[4]).strip() == "Y",
                    })
                return result
    except Exception as e:
        return [{"error": str(e)}]


def import_table(db_name: str, table_name: str, layer_id: int = 1) -> dict:
    """
    Importiert eine Tabelle aus DBC.TablesV / DBC.ColumnsV in
    META_TABLE + META_COLUMN.

    Gibt zurück: {table_id, table_name, db_name, cols_imported}
    oder         {error: "..."}
    """
    tbl      = f"{META_SCHEMA}.{META_TABLES['tables']}"
    col_tbl  = f"{META_SCHEMA}.{META_TABLES['columns']}"
    meta_db  = f"{META_SCHEMA}.{META_TABLES['database']}"

    try:
        with _connect() as conn:
            with conn.cursor() as cur:

                # 1. DATABASE_ID aus META_DATABASE
                cur.execute(
                    f"SELECT database_id FROM {meta_db} WHERE database_name = ?",
                    (db_name,)
                )
                row = cur.fetchone()
                if not row:
                    return {"error": f"Datenbank '{db_name}' nicht in META_DATABASE – bitte zuerst anlegen"}
                database_id = int(row[0])

                # 2. Duplikat-Check
                cur.execute(
                    f"SELECT table_id FROM {tbl} WHERE database_id = ? AND table_name = ?",
                    (database_id, table_name.upper())
                )
                if cur.fetchone():
                    return {"error": f"Tabelle '{table_name}' bereits in META_TABLE vorhanden"}

                # 3. Nächste TABLE_ID
                cur.execute(f"SELECT COALESCE(MAX(table_id), 0) + 1 FROM {tbl}")
                table_id = int(cur.fetchone()[0])

                # 4. DBC-Infos
                cur.execute(
                    "SELECT CommentString, TableKind FROM DBC.TablesV "
                    "WHERE DatabaseName = ? AND TableName = ?",
                    (db_name, table_name)
                )
                dbc_row    = cur.fetchone()
                comment    = (str(dbc_row[0]) if dbc_row and dbc_row[0] else "")
                table_kind = (str(dbc_row[1]) if dbc_row and dbc_row[1] else "T")

                # 5. INSERT META_TABLE (CREATE_TIMESTAMP + LAST_ALTER_TIMESTAMP haben DEFAULT)
                cur.execute(
                    f"""
                    INSERT INTO {tbl}
                        (table_id, database_id, table_name, layer_id,
                         table_kind, comment_string)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (table_id, database_id, table_name.upper(),
                     layer_id, table_kind, comment)
                )
                conn.commit()

                # 6. Spalten aus DBC.ColumnsV
                cur.execute(
                    """
                    SELECT TRIM(ColumnName), ColumnId, TRIM(ColumnType), ColumnLength,
                           DecimalTotalDigits, DecimalFractionalDigits,
                           TRIM(Nullable), DefaultValue, CommentString,
                           TRIM(CharType)
                    FROM DBC.ColumnsV
                    WHERE TRIM(DatabaseName) = TRIM(?) AND TRIM(TableName) = TRIM(?)
                    ORDER BY ColumnId
                    """,
                    (db_name.strip(), table_name.strip())
                )
                dbc_cols = cur.fetchall()

                # 7. Nächste COLUMN_ID
                cur.execute(f"SELECT COALESCE(MAX(column_id), 0) FROM {col_tbl}")
                next_col_id = int(cur.fetchone()[0]) + 1

                # 8. INSERT META_COLUMN je Spalte
                for col in dbc_cols:
                    col_name, col_pos, col_type, col_len, dec_total, dec_frac, \
                        nullable, default_val, col_comment, char_type = col
                    _CHARSET_MAP = {'L': 'LATIN', 'U': 'UNICODE'}
                    charset_val = _CHARSET_MAP.get(str(char_type or '').strip())

                    type_str = _type_str(col_type, col_len, dec_total, dec_frac)

                    cur.execute(
                        f"""
                        INSERT INTO {col_tbl}
                            (column_id, table_id, column_name, column_position,
                             datatype_id, column_type, column_length,
                             decimal_total_digits, decimal_fractional_digits,
                             nullable, default_value, comment_string, charset,
                             ersterfassungsdatum, aenderungsdatum)
                        VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?,
                                CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
                        """,
                        (
                            next_col_id,
                            table_id,
                            str(col_name).upper(),
                            int(col_pos or 0),
                            type_str,
                            int(col_len)     if col_len    is not None else None,
                            int(dec_total)   if dec_total  is not None else None,
                            int(dec_frac)    if dec_frac   is not None else None,
                            "Y"              if str(nullable or "").strip() == "Y" else "N",
                            str(default_val) if default_val  else None,
                            str(col_comment) if col_comment  else None,
                            charset_val,
                        )
                    )
                    next_col_id += 1

                conn.commit()

                # 9. Indizes aus DBC.IndicesV → META_INDEX + META_INDEX_COLUMN
                idx_tbl     = f"{META_SCHEMA}.{META_TABLES['index']}"
                idx_col_tbl = f"{META_SCHEMA}.{META_TABLES['index_col']}"

                # TRIM() wegen CHAR(128)-Padding in DBC-Views nötig
                cur.execute(
                    """
                    SELECT IndexNumber, TRIM(IndexType) AS IndexType,
                           TRIM(UniqueFlag) AS UniqueFlag,
                           TRIM(IndexName)  AS IndexName,
                           TRIM(ColumnName) AS ColumnName, ColumnPosition
                    FROM DBC.IndicesV
                    WHERE TRIM(DatabaseName) = TRIM(?)
                      AND TRIM(TableName)    = TRIM(?)
                    ORDER BY IndexNumber, ColumnPosition
                    """,
                    (db_name.strip(), table_name.strip())
                )
                dbc_idx_rows = cur.fetchall()

                # Gruppieren nach IndexNumber
                idx_meta_map: dict = {}
                idx_col_map: dict  = defaultdict(list)
                for row in dbc_idx_rows:
                    ix_num, ix_type_code, uniq, ix_name, col_name, col_pos = row
                    ix_num = int(ix_num or 0)
                    if ix_num not in idx_meta_map:
                        idx_meta_map[ix_num] = (
                            str(ix_type_code or "").strip(),
                            str(uniq         or "N").strip(),
                            str(ix_name      or "").strip(),
                        )
                    idx_col_map[ix_num].append(
                        (str(col_name).upper().strip(), int(col_pos or 0))
                    )

                cur.execute(f"SELECT COALESCE(MAX(index_id), 0) FROM {idx_tbl}")
                next_idx_id = int(cur.fetchone()[0]) + 1
                cur.execute(f"SELECT COALESCE(MAX(index_column_id), 0) FROM {idx_col_tbl}")
                next_idx_col_id = int(cur.fetchone()[0]) + 1

                idx_imported = 0
                for ix_num, cols in idx_col_map.items():
                    ix_type_code, uniq, ix_name = idx_meta_map[ix_num]
                    index_type = _IX_TYPE_MAP.get(
                        (ix_type_code, uniq),
                        "PRIMARY INDEX" if "P" in ix_type_code.upper() else "SECONDARY INDEX"
                    )
                    is_unique = "Y" if uniq == "Y" else "N"

                    cur.execute(
                        f"""
                        INSERT INTO {idx_tbl}
                            (index_id, table_id, index_name, index_type,
                             index_number, is_unique,
                             ersterfassungsdatum, aenderungsdatum)
                        VALUES (?, ?, ?, ?, ?, ?,
                                CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
                        """,
                        (
                            next_idx_id, table_id,
                            ix_name if ix_name else None,
                            index_type, ix_num, is_unique,
                        )
                    )

                    for col_name, col_pos in cols:
                        # column_id aus META_COLUMN nachschlagen
                        cur.execute(
                            f"SELECT column_id FROM {col_tbl}"
                            f" WHERE table_id = ? AND column_name = ?",
                            (table_id, col_name)
                        )
                        col_row = cur.fetchone()
                        if col_row:
                            cur.execute(
                                f"""
                                INSERT INTO {idx_col_tbl}
                                    (index_column_id, index_id, column_id,
                                     column_position,
                                     ersterfassungsdatum, aenderungsdatum)
                                VALUES (?, ?, ?, ?,
                                        CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
                                """,
                                (next_idx_col_id, next_idx_id,
                                 int(col_row[0]), col_pos)
                            )
                            next_idx_col_id += 1

                    next_idx_id  += 1
                    idx_imported += 1

                conn.commit()

                return {
                    "table_id":        table_id,
                    "table_name":      table_name.upper(),
                    "db_name":         db_name,
                    "cols_imported":   len(dbc_cols),
                    "indexes_imported": idx_imported,
                }

    except Exception as e:
        return {"error": str(e)}


def import_indexes_from_dbc(table_id: int, db_name: str, table_name: str) -> dict:
    """
    Liest DBC.IndicesV und befüllt META_INDEX + META_INDEX_COLUMN für eine
    bereits importierte Tabelle nach (z.B. nach dem PI-Import-Bug-Fix).

    Bestehende Indizes in META werden NICHT gelöscht – nur neue hinzugefügt.
    Gibt zurück: {indexes_imported, skipped_existing}
    """
    idx_tbl     = f"{META_SCHEMA}.{META_TABLES['index']}"
    idx_col_tbl = f"{META_SCHEMA}.{META_TABLES['index_col']}"
    col_tbl     = f"{META_SCHEMA}.{META_TABLES['columns']}"

    try:
        with _connect() as conn:
            with conn.cursor() as cur:

                # Verwaiste META_INDEX-Zeilen (ohne zugehörige META_INDEX_COLUMN) löschen
                cur.execute(
                    f"""
                    DELETE FROM {idx_tbl}
                    WHERE table_id = ?
                      AND index_id NOT IN (
                          SELECT DISTINCT index_id FROM {idx_col_tbl}
                      )
                    """,
                    (table_id,)
                )
                conn.commit()

                # Vorhandene Indizes für diese Tabelle ermitteln (nur solche MIT Spalten)
                cur.execute(
                    f"""
                    SELECT DISTINCT i.index_number
                    FROM {idx_tbl} i
                    JOIN {idx_col_tbl} ic ON i.index_id = ic.index_id
                    WHERE i.table_id = ?
                    """,
                    (table_id,)
                )
                existing_numbers = {int(r[0]) for r in cur.fetchall() if r[0] is not None}

                # DBC-Indizes laden – TRIM() wegen CHAR(128)-Padding in DBC-Views
                cur.execute(
                    """
                    SELECT IndexNumber, TRIM(IndexType) AS IndexType,
                           TRIM(UniqueFlag) AS UniqueFlag,
                           TRIM(IndexName)  AS IndexName,
                           TRIM(ColumnName) AS ColumnName, ColumnPosition
                    FROM DBC.IndicesV
                    WHERE TRIM(DatabaseName) = TRIM(?)
                      AND TRIM(TableName)    = TRIM(?)
                    ORDER BY IndexNumber, ColumnPosition
                    """,
                    (db_name.strip(), table_name.strip())
                )
                dbc_idx_rows = cur.fetchall()

                idx_meta_map: dict = {}
                idx_col_map: dict  = defaultdict(list)
                for row in dbc_idx_rows:
                    ix_num, ix_type_code, uniq, ix_name, col_name, col_pos = row
                    ix_num = int(ix_num or 0)
                    if ix_num not in idx_meta_map:
                        idx_meta_map[ix_num] = (
                            str(ix_type_code or "").strip(),
                            str(uniq         or "N").strip(),
                            str(ix_name      or "").strip(),
                        )
                    idx_col_map[ix_num].append(
                        (str(col_name).upper().strip(), int(col_pos or 0))
                    )

                cur.execute(f"SELECT COALESCE(MAX(index_id), 0) FROM {idx_tbl}")
                next_idx_id = int(cur.fetchone()[0]) + 1
                cur.execute(f"SELECT COALESCE(MAX(index_column_id), 0) FROM {idx_col_tbl}")
                next_idx_col_id = int(cur.fetchone()[0]) + 1

                imported = 0
                skipped  = 0
                missed_cols: list[str] = []
                for ix_num, cols in idx_col_map.items():
                    if ix_num in existing_numbers:
                        skipped += 1
                        continue

                    ix_type_code, uniq, ix_name = idx_meta_map[ix_num]
                    index_type = _IX_TYPE_MAP.get(
                        (ix_type_code, uniq),
                        "PRIMARY INDEX" if "P" in ix_type_code.upper() else "SECONDARY INDEX"
                    )

                    cur.execute(
                        f"""
                        INSERT INTO {idx_tbl}
                            (index_id, table_id, index_name, index_type,
                             index_number, is_unique,
                             ersterfassungsdatum, aenderungsdatum)
                        VALUES (?, ?, ?, ?, ?, ?,
                                CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
                        """,
                        (
                            next_idx_id, table_id,
                            ix_name if ix_name else None,
                            index_type, ix_num,
                            "Y" if uniq == "Y" else "N",
                        )
                    )

                    for col_name, col_pos in cols:
                        cur.execute(
                            f"SELECT column_id FROM {col_tbl}"
                            f" WHERE table_id = ? AND UPPER(TRIM(column_name)) = UPPER(TRIM(?))",
                            (table_id, col_name)
                        )
                        col_row = cur.fetchone()
                        if col_row:
                            cur.execute(
                                f"""
                                INSERT INTO {idx_col_tbl}
                                    (index_column_id, index_id, column_id,
                                     column_position,
                                     ersterfassungsdatum, aenderungsdatum)
                                VALUES (?, ?, ?, ?,
                                        CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
                                """,
                                (next_idx_col_id, next_idx_id, int(col_row[0]), col_pos)
                            )
                            next_idx_col_id += 1
                        else:
                            missed_cols.append(col_name)

                    next_idx_id += 1
                    imported    += 1

                conn.commit()
                return {
                    "indexes_imported":  imported,
                    "skipped_existing":  skipped,
                    "dbc_rows_found":    len(dbc_idx_rows),
                    "db_name_used":      db_name.strip(),
                    "table_name_used":   table_name.strip(),
                    "missed_cols":       missed_cols if missed_cols else None,
                }

    except Exception as e:
        return {"error": str(e)}
