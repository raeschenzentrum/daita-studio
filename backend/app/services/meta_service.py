"""
MetaService – liest Metadaten aus dem konfigurierten META-Schema (Teradata).

Reale Spaltennamen (aus DDL ermittelt):
  META_TABLE:        table_id, database_id, table_name, comment_string, layer_id,
                     table_kind, is_historized  (kein DB_NAME, kein TABLE_DESC)
  META_DATABASE:     database_id, database_name, comment_string, layer_id
  META_COLUMN:       column_id, table_id, column_name, column_type, column_length,
                     column_position, nullable, is_technical_key, comment_string
  META_LAYER:        layer_id, layer_name, layer_code, layer_sequence, layer_beschreibung
  META_FOREIGN_KEY:  fk_id, fk_name, child_table_id, child_column_id,
                     parent_table_id, parent_column_id
  META_AREA:         area_id, area_name, area_code, area_category_id, layer_id, beschreibung

API-Aliases: Spalten werden mit stabilen JSON-Keys zurückgegeben
  (z. B. comment_string → table_desc) damit das Frontend nicht geändert werden muss.

Caching: 5 Minuten (time-based, in-memory).
"""

import time
import teradatasql
from typing import Optional

from app.config import DB_CONFIG, META_SCHEMA, META_TABLES

# ---------------------------------------------------------------------------
# Einfacher In-Memory-Cache (TTL-basiert)
# ---------------------------------------------------------------------------

_CACHE: dict = {}
_CACHE_TTL = 300  # Sekunden


def _cached(key: str, loader):
    entry = _CACHE.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    data = loader()
    _CACHE[key] = {"ts": time.time(), "data": data}
    return data


def _invalidate(key: Optional[str] = None):
    if key:
        _CACHE.pop(key, None)
    else:
        _CACHE.clear()


# ---------------------------------------------------------------------------
# Verbindungshelfer
# ---------------------------------------------------------------------------

def _connect():
    return teradatasql.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["username"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
    )


def _query(sql: str, params: tuple = ()) -> list[dict]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0].lower() for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# META-Abfragen
# ---------------------------------------------------------------------------

def get_layers() -> list[dict]:
    """Layer aus META_LAYER. Aliases: layer_code→layer_short, layer_beschreibung→layer_desc"""
    def _load():
        try:
            sql = f"""
                SELECT
                    layer_id,
                    layer_name,
                    layer_code        AS layer_short,
                    layer_sequence,
                    layer_beschreibung AS layer_desc
                FROM {META_SCHEMA}.{META_TABLES['layer']}
                ORDER BY layer_sequence
            """
            return _query(sql)
        except Exception as e:
            return [{"error": str(e)}]
    return _cached("layers", _load)


def get_databases() -> list[dict]:
    """Datenbanken aus META_DATABASE. Aliases: database_id→db_id, database_name→db_name"""
    def _load():
        try:
            sql = f"""
                SELECT
                    database_id   AS db_id,
                    database_name AS db_name,
                    comment_string AS db_desc,
                    layer_id
                FROM {META_SCHEMA}.{META_TABLES['database']}
                ORDER BY database_name
            """
            return _query(sql)
        except Exception as e:
            return [{"error": str(e)}]
    return _cached("databases", _load)


def get_tables(
    layer_id: Optional[int] = None,
    db_name:  Optional[str] = None,
    search:   Optional[str] = None,
) -> list[dict]:
    """
    Tabellen aus META_TABLE JOIN META_DATABASE.
    Filter: layer_id, db_name, search (LIKE auf table_name + comment_string).
    Aliases: comment_string→table_desc, database_name→db_name, table_kind→table_type
    """
    cache_key = f"tables|{layer_id}|{db_name}|{search}"

    def _load():
        try:
            where_parts = ["1=1"]
            params: list = []

            if layer_id is not None:
                where_parts.append("t.layer_id = ?")
                params.append(layer_id)
            if db_name:
                where_parts.append("d.database_name = ?")
                params.append(db_name)
            if search:
                where_parts.append(
                    "(UPPER(t.table_name) LIKE ? OR UPPER(t.comment_string) LIKE ?)"
                )
                s = f"%{search.upper()}%"
                params.extend([s, s])

            where = " AND ".join(where_parts)
            sql = f"""
                SELECT
                    t.table_id,
                    t.table_name,
                    t.comment_string  AS table_desc,
                    d.database_name   AS db_name,
                    t.layer_id,
                    t.table_kind      AS table_type,
                    t.is_historized
                FROM {META_SCHEMA}.{META_TABLES['tables']} t
                JOIN {META_SCHEMA}.{META_TABLES['database']} d
                  ON t.database_id = d.database_id
                WHERE {where}
                ORDER BY d.database_name, t.table_name
            """
            return _query(sql, tuple(params))
        except Exception as e:
            return [{"error": str(e)}]

    return _cached(cache_key, _load)


def get_columns(table_id: int) -> list[dict]:
    """
    Spalten aus META_COLUMN.
    Aliases: column_type→data_type, column_length→data_length,
             is_technical_key→pk_flag, column_position→column_order,
             comment_string→column_desc
    """
    cache_key = f"columns|{table_id}"

    def _load():
        try:
            sql = f"""
                SELECT
                    c.column_id,
                    c.table_id,
                    c.column_name,
                    c.comment_string   AS column_desc,
                    c.column_type      AS data_type,
                    c.column_length    AS data_length,
                    c.nullable,
                    c.is_technical_key AS pk_flag,
                    c.column_position  AS column_order
                FROM {META_SCHEMA}.{META_TABLES['columns']} c
                WHERE c.table_id = ?
                ORDER BY c.column_position
            """
            return _query(sql, (table_id,))
        except Exception as e:
            return [{"error": str(e)}]

    return _cached(cache_key, _load)


def get_foreign_keys(table_id: Optional[int] = None) -> list[dict]:
    """
    FK-Beziehungen aus META_FOREIGN_KEY.
    Aliases: child_table_id→from_table_id, parent_table_id→to_table_id usw.
    """
    cache_key = f"fk|{table_id}"

    def _load():
        try:
            where = f"WHERE fk.child_table_id = {int(table_id)}" if table_id else ""
            sql = f"""
                SELECT
                    fk.fk_id,
                    fk.fk_name,
                    fk.child_table_id   AS from_table_id,
                    fk.child_column_id  AS from_column_id,
                    fk.parent_table_id  AS to_table_id,
                    fk.parent_column_id AS to_column_id
                FROM {META_SCHEMA}.{META_TABLES['fk']} fk
                {where}
                ORDER BY fk.child_table_id
            """
            return _query(sql)
        except Exception as e:
            return [{"error": str(e)}]

    return _cached(cache_key, _load)


def get_areas() -> list[dict]:
    """Subject Areas aus META_AREA. Alias: beschreibung→area_desc"""
    def _load():
        try:
            sql = f"""
                SELECT
                    area_id,
                    area_name,
                    area_code,
                    area_category_id,
                    layer_id,
                    beschreibung AS area_desc
                FROM {META_SCHEMA}.{META_TABLES['area']}
                ORDER BY area_name
            """
            return _query(sql)
        except Exception as e:
            return [{"error": str(e)}]
    return _cached("areas", _load)


def clear_cache():
    """Cache komplett leeren (z. B. nach Import)."""
    _invalidate()


# ---------------------------------------------------------------------------
# DM3: FK-Relationen schreiben
# ---------------------------------------------------------------------------

def create_foreign_key(
    fk_name: str,
    child_table_id: int,
    parent_table_id: int,
    child_column_id: Optional[int] = None,
    parent_column_id: Optional[int] = None,
) -> dict:
    """Neuen FK in META_FOREIGN_KEY eintragen. Gibt den erstellten Datensatz zurück."""
    try:
        fk_tbl = f"{META_SCHEMA}.{META_TABLES['fk']}"
        with _connect() as conn:
            with conn.cursor() as cur:
                # Nächste ID ermitteln (kein AUTO_INCREMENT in Teradata)
                cur.execute(f"SELECT COALESCE(MAX(fk_id), 0) + 1 FROM {fk_tbl}")
                new_id = int(cur.fetchone()[0])

                if not fk_name:
                    fk_name = f"FK_{child_table_id}_{parent_table_id}"

                # NULL nicht erlaubt für column_id → 0 als Platzhalter
                child_col  = child_column_id  if child_column_id  is not None else 0
                parent_col = parent_column_id if parent_column_id is not None else 0

                cur.execute(
                    f"""
                    INSERT INTO {fk_tbl}
                        (fk_id, fk_name, child_table_id, child_column_id,
                         parent_table_id, parent_column_id,
                         ersterfassungsdatum, aenderungsdatum)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
                    """,
                    (new_id, fk_name, child_table_id, child_col,
                     parent_table_id, parent_col),
                )
                conn.commit()

        # FK-Cache + columns_full-Cache invalidieren
        for k in list(_CACHE.keys()):
            if k.startswith("fk|") or k.startswith("columns_full|"):
                _CACHE.pop(k, None)

        return {
            "fk_id":         new_id,
            "fk_name":       fk_name,
            "from_table_id": child_table_id,
            "to_table_id":   parent_table_id,
        }
    except Exception as e:
        return {"error": str(e)}


def update_foreign_key(
    fk_id: int,
    fk_name: str,
    child_column_id: Optional[int] = None,
    parent_column_id: Optional[int] = None,
) -> dict:
    """FK-Name und Spalten-Zuordnung aktualisieren."""
    try:
        fk_tbl     = f"{META_SCHEMA}.{META_TABLES['fk']}"
        child_col  = child_column_id  if child_column_id  is not None else 0
        parent_col = parent_column_id if parent_column_id is not None else 0
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {fk_tbl}
                    SET fk_name          = ?,
                        child_column_id  = ?,
                        parent_column_id = ?,
                        aenderungsdatum  = CURRENT_TIMESTAMP(6)
                    WHERE fk_id = ?
                    """,
                    (fk_name, child_col, parent_col, fk_id),
                )
                conn.commit()

        for k in list(_CACHE.keys()):
            if k.startswith("fk|") or k.startswith("columns_full|"):
                _CACHE.pop(k, None)

        return {"updated": fk_id, "fk_name": fk_name}
    except Exception as e:
        return {"error": str(e)}


def delete_foreign_key(fk_id: int) -> dict:
    """FK aus META_FOREIGN_KEY löschen."""
    try:
        fk_tbl = f"{META_SCHEMA}.{META_TABLES['fk']}"
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {fk_tbl} WHERE fk_id = ?", (fk_id,))
                conn.commit()

        for k in list(_CACHE.keys()):
            if k.startswith("fk|") or k.startswith("columns_full|"):
                _CACHE.pop(k, None)

        return {"deleted": fk_id}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# DM7: Tabellen / Spalten / Indizes bearbeiten + Reverse Engineering
# ---------------------------------------------------------------------------

def get_table_detail(table_id: int) -> dict:
    """Vollständige Tabellen-Details inkl. Historisierungs-Felder."""
    try:
        sql = f"""
            SELECT
                t.table_id,
                t.table_name,
                t.comment_string      AS table_desc,
                d.database_name       AS db_name,
                d.database_id,
                t.layer_id,
                t.table_kind          AS table_type,
                t.is_historized,
                t.historization_type,
                t.valid_from_column,
                t.valid_to_column,
                t.is_current_column
            FROM {META_SCHEMA}.{META_TABLES['tables']} t
            JOIN {META_SCHEMA}.{META_TABLES['database']} d
              ON t.database_id = d.database_id
            WHERE t.table_id = ?
        """
        rows = _query(sql, (table_id,))
        return rows[0] if rows else {"error": "Tabelle nicht gefunden"}
    except Exception as e:
        return {"error": str(e)}


def update_table(
    table_id: int,
    comment: Optional[str] = None,
    is_historized: Optional[str] = None,
    historization_type: Optional[str] = None,
    valid_from_column: Optional[str] = None,
    valid_to_column: Optional[str] = None,
    is_current_column: Optional[str] = None,
) -> dict:
    """Tabellen-Metadaten aktualisieren."""
    try:
        tbl = f"{META_SCHEMA}.{META_TABLES['tables']}"
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {tbl}
                    SET comment_string     = ?,
                        is_historized      = ?,
                        historization_type = ?,
                        valid_from_column  = ?,
                        valid_to_column    = ?,
                        is_current_column  = ?,
                        last_alter_timestamp = CURRENT_TIMESTAMP(6)
                    WHERE table_id = ?
                    """,
                    (comment, is_historized or 'N', historization_type,
                     valid_from_column, valid_to_column, is_current_column,
                     table_id),
                )
                conn.commit()

        # Table-Cache invalidieren
        for k in list(_CACHE.keys()):
            if k.startswith("tables|"):
                _CACHE.pop(k, None)

        return {"updated": table_id}
    except Exception as e:
        return {"error": str(e)}


def get_columns_full(table_id: int) -> list[dict]:
    """
    Erweiterte Spalten-Abfrage für den Editor (alle editierbaren Felder).
    """
    cache_key = f"columns_full|{table_id}"

    def _load():
        try:
            sql = f"""
                SELECT
                    c.column_id,
                    c.table_id,
                    c.column_name,
                    c.column_position  AS column_order,
                    c.column_type      AS data_type,
                    c.column_length    AS data_length,
                    c.decimal_total_digits     AS decimal_precision,
                    c.decimal_fractional_digits AS decimal_scale,
                    c.nullable,
                    c.default_value,
                    c.is_technical_key AS pk_flag,
                    c.is_business_key  AS bk_flag,
                    c.is_audit_column  AS audit_flag,
                    c.is_scd_column    AS scd_flag,
                    c.is_pii           AS pii_flag,
                    CASE WHEN pk_chk.column_id IS NOT NULL
                         THEN 'Y'
                         ELSE COALESCE(TRIM(c.is_pk), 'N')
                    END AS is_pk,
                    CASE WHEN fk_chk.column_id IS NOT NULL
                         THEN 'Y'
                         ELSE COALESCE(TRIM(c.is_fk), 'N')
                    END AS is_fk,
                    CASE WHEN pi_chk.column_id IS NOT NULL
                         THEN 'Y'
                         ELSE COALESCE(TRIM(c.is_pi), 'N')
                    END AS is_pi,
                    c.is_hash,
                    c.comment_string   AS column_desc,
                    c.business_name,
                    c.masking_rule,
                    c.charset,
                    c.is_casespecific,
                    c.datatype_id
                FROM {META_SCHEMA}.{META_TABLES['columns']} c
                LEFT JOIN (
                    SELECT DISTINCT parent_column_id AS column_id
                    FROM {META_SCHEMA}.{META_TABLES['fk']}
                    WHERE parent_column_id > 0
                ) pk_chk ON pk_chk.column_id = c.column_id
                LEFT JOIN (
                    SELECT DISTINCT child_column_id AS column_id
                    FROM {META_SCHEMA}.{META_TABLES['fk']}
                ) fk_chk ON fk_chk.column_id = c.column_id
                LEFT JOIN (
                    SELECT DISTINCT ic.column_id
                    FROM {META_SCHEMA}.{META_TABLES['index_col']} ic
                    JOIN {META_SCHEMA}.{META_TABLES['index']} i
                      ON ic.index_id = i.index_id
                    WHERE TRIM(i.index_type) LIKE '%PRIMARY%'
                      AND TRIM(i.index_type) NOT LIKE '%SECONDARY%'
                ) pi_chk ON pi_chk.column_id = c.column_id
                WHERE c.table_id = ?
                ORDER BY c.column_position
            """
            return _query(sql, (table_id,))
        except Exception as e:
            return [{"error": str(e)}]

    return _cached(cache_key, _load)


def update_column(
    column_id: int,
    data_type: Optional[str] = None,
    data_length: Optional[int] = None,
    decimal_precision: Optional[int] = None,
    decimal_scale: Optional[int] = None,
    nullable: Optional[str] = None,
    pk_flag: Optional[str] = None,
    bk_flag: Optional[str] = None,
    audit_flag: Optional[str] = None,
    comment: Optional[str] = None,
    default_value: Optional[str] = None,
    is_pk: Optional[str] = None,
    is_fk: Optional[str] = None,
    is_pi: Optional[str] = None,
    is_hash: Optional[str] = None,
    charset: Optional[str] = None,
    is_casespecific: Optional[str] = None,
    business_name: Optional[str] = None,
    masking_rule: Optional[str] = None,
    is_pii: Optional[str] = None,
) -> dict:
    """Einzelne Spalten-Metadaten aktualisieren."""
    try:
        col_tbl = f"{META_SCHEMA}.{META_TABLES['columns']}"
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {col_tbl}
                    SET column_type              = ?,
                        column_length            = ?,
                        decimal_total_digits     = ?,
                        decimal_fractional_digits = ?,
                        nullable                 = ?,
                        is_technical_key         = ?,
                        is_business_key          = ?,
                        is_audit_column          = ?,
                        comment_string           = ?,
                        default_value            = ?,
                        is_pk                    = ?,
                        is_fk                    = ?,
                        is_pi                    = ?,
                        is_hash                  = ?,
                        charset                  = ?,
                        is_casespecific          = ?,
                        business_name            = ?,
                        masking_rule             = ?,
                        is_pii                   = ?,
                        aenderungsdatum          = CURRENT_TIMESTAMP(6)
                    WHERE column_id = ?
                    """,
                    (data_type, data_length, decimal_precision, decimal_scale,
                     nullable or 'Y', pk_flag or 'N', bk_flag or 'N',
                     audit_flag or 'N', comment, default_value,
                     is_pk or 'N', is_fk or 'N', is_pi or 'N', is_hash or 'N',
                     charset, is_casespecific or 'N', business_name, masking_rule,
                     is_pii or 'N',
                     column_id),
                )
                conn.commit()

        # Spalten-Caches invalidieren
        for k in list(_CACHE.keys()):
            if k.startswith("columns"):
                _CACHE.pop(k, None)

        return {"updated": column_id}
    except Exception as e:
        return {"error": str(e)}


def get_indexes(table_id: int) -> list[dict]:
    """META_INDEX + META_INDEX_COLUMN für eine Tabelle."""
    try:
        sql = f"""
            SELECT
                i.index_id,
                i.table_id,
                i.index_name,
                i.index_type,
                i.index_number,
                i.is_unique,
                i.is_clustered,
                i.comment_string AS index_desc,
                ic.index_column_id,
                ic.column_id,
                ic.column_position,
                c.column_name
            FROM {META_SCHEMA}.{META_TABLES['index']} i
            JOIN {META_SCHEMA}.{META_TABLES['index_col']} ic
              ON i.index_id = ic.index_id
            JOIN {META_SCHEMA}.{META_TABLES['columns']} c
              ON ic.column_id = c.column_id
            WHERE i.table_id = ?
            ORDER BY i.index_number, ic.column_position
        """
        rows = _query(sql, (table_id,))

        # Zu Index-Objekten zusammenfassen
        indexes: dict = {}
        for r in rows:
            iid = r["index_id"]
            if iid not in indexes:
                indexes[iid] = {
                    "index_id":    iid,
                    "index_name":  r["index_name"],
                    "index_type":  r["index_type"],
                    "index_number": r["index_number"],
                    "is_unique":   r["is_unique"],
                    "is_clustered": r["is_clustered"],
                    "index_desc":  r["index_desc"],
                    "columns":     [],
                }
            indexes[iid]["columns"].append({
                "column_id":       r["column_id"],
                "column_name":     r["column_name"],
                "column_position": r["column_position"],
            })
        return list(indexes.values())
    except Exception as e:
        return [{"error": str(e)}]


def save_indexes(table_id: int, indexes: list) -> dict:
    """
    Alle Indizes einer Tabelle ersetzen (vollständiger Replace).
    indexes = [{ index_type, is_unique, columns: [{column_id, column_position}] }]
    """
    try:
        idx_tbl = f"{META_SCHEMA}.{META_TABLES['index']}"
        ic_tbl  = f"{META_SCHEMA}.{META_TABLES['index_col']}"

        with _connect() as conn:
            with conn.cursor() as cur:
                # Bestehende Index-Columns löschen
                cur.execute(
                    f"""
                    DELETE FROM {ic_tbl}
                    WHERE index_id IN (
                        SELECT index_id FROM {idx_tbl} WHERE table_id = ?
                    )
                    """,
                    (table_id,),
                )
                # Bestehende Indizes löschen
                cur.execute(f"DELETE FROM {idx_tbl} WHERE table_id = ?", (table_id,))

                # Neue ID-Basis ermitteln
                cur.execute(f"SELECT COALESCE(MAX(index_id), 0) + 1 FROM {idx_tbl}")
                next_idx_id = int(cur.fetchone()[0])

                cur.execute(f"SELECT COALESCE(MAX(index_column_id), 0) + 1 FROM {ic_tbl}")
                next_ic_id = int(cur.fetchone()[0])

                for idx_num, idx in enumerate(indexes, start=1):
                    cur.execute(
                        f"""
                        INSERT INTO {idx_tbl}
                            (index_id, table_id, index_name, index_type, index_number,
                             is_unique, is_clustered, ersterfassungsdatum, aenderungsdatum)
                        VALUES (?, ?, ?, ?, ?, ?, 'N',
                                CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
                        """,
                        (next_idx_id, table_id,
                         idx.get("index_name") or None,
                         idx.get("index_type", "PRIMARY INDEX"),
                         idx_num,
                         idx.get("is_unique", "N")),
                    )
                    for col in idx.get("columns", []):
                        cur.execute(
                            f"""
                            INSERT INTO {ic_tbl}
                                (index_column_id, index_id, column_id, column_position,
                                 ersterfassungsdatum, aenderungsdatum)
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
                            """,
                            (next_ic_id, next_idx_id,
                             col["column_id"], col["column_position"]),
                        )
                        next_ic_id += 1
                    next_idx_id += 1

                conn.commit()

        return {"saved": len(indexes)}
    except Exception as e:
        return {"error": str(e)}


_TD_TYPE_LABELS = {
    "I8": "BIGINT", "I ": "INTEGER", "I1": "BYTEINT", "I2": "SMALLINT",
    "F ": "FLOAT", "D ": "DECIMAL", "N ": "NUMBER",
    "CV": "VARCHAR", "CF": "CHAR", "CO": "CLOB",
    "DA": "DATE", "TS": "TIMESTAMP", "TI": "TIME",
    "BV": "VARBYTE", "BF": "BYTE", "BO": "BLOB",
}


def reverse_engineer(table_id: int, db_name: str, table_name: str) -> dict:
    """
    Vergleicht DBC.ColumnsV + DBC.IndicesV mit META_COLUMN + META_INDEX.
    Gibt Diff-Listen zurück: columns_diff, indexes_diff.
    """
    try:
        # DBC-Daten abrufen
        dbc_cols_sql = """
            SELECT ColumnName, TRIM(ColumnType) AS ColumnType,
                   ColumnLength, DecimalTotalDigits, DecimalFractionalDigits,
                   Nullable
            FROM DBC.ColumnsV
            WHERE DatabaseName = ? AND TableName = ?
            ORDER BY ColumnId
        """
        dbc_idx_sql = """
            SELECT TRIM(IndexType) AS IndexType, TRIM(UniqueFlag) AS UniqueFlag,
                   TRIM(ColumnName) AS ColumnName, ColumnPosition
            FROM DBC.IndicesV
            WHERE TRIM(DatabaseName) = TRIM(?)
              AND TRIM(TableName)    = TRIM(?)
            ORDER BY IndexNumber, ColumnPosition
        """
        dbc_cols = _query(dbc_cols_sql, (db_name.strip(), table_name.strip()))
        dbc_idx  = _query(dbc_idx_sql,  (db_name.strip(), table_name.strip()))

        # META-Daten
        meta_cols = get_columns_full(table_id)
        meta_idx  = get_indexes(table_id)

        dbc_col_map  = {r["columnname"].strip().upper(): r for r in dbc_cols}
        meta_col_map = {r["column_name"].strip().upper(): r for r in meta_cols
                        if not r.get("error")}

        columns_diff = []

        # Alle DBC-Spalten prüfen
        for name, dc in dbc_col_map.items():
            mc = meta_col_map.get(name)
            dbc_type   = (dc.get("columntype") or "").strip()
            dbc_len    = dc.get("columnlength")
            dbc_prec   = dc.get("decimaltotaldigits")
            dbc_scale  = dc.get("decimalfractionaldigits")
            dbc_null   = (dc.get("nullable") or "").strip()

            if not mc:
                columns_diff.append({
                    "column_name": name,
                    "status":      "new_in_db",
                    "label":       "Nur in DB",
                    "dbc":  {"type": dbc_type, "length": dbc_len, "nullable": dbc_null},
                    "meta": None,
                })
            else:
                meta_type = (mc.get("data_type") or "").strip()
                meta_len  = mc.get("data_length")
                meta_null = (mc.get("nullable") or "").strip()
                diffs = []
                if meta_type != dbc_type:
                    diffs.append(f"Typ: META={meta_type} DB={dbc_type}")
                if meta_len != dbc_len:
                    diffs.append(f"Länge: META={meta_len} DB={dbc_len}")
                if meta_null.rstrip() != dbc_null.rstrip():
                    diffs.append(f"Nullable: META={meta_null} DB={dbc_null}")
                columns_diff.append({
                    "column_name": name,
                    "status":      "diff" if diffs else "ok",
                    "label":       "; ".join(diffs) if diffs else "gleich",
                    "dbc":  {"type": dbc_type, "length": dbc_len, "nullable": dbc_null},
                    "meta": {"type": meta_type, "length": meta_len, "nullable": meta_null,
                             "column_id": mc["column_id"]},
                })

        # Spalten nur in META
        for name in meta_col_map:
            if name not in dbc_col_map:
                mc = meta_col_map[name]
                columns_diff.append({
                    "column_name": name,
                    "status":      "only_in_meta",
                    "label":       "Nur in META",
                    "dbc":  None,
                    "meta": {"type": mc.get("data_type"), "length": mc.get("data_length"),
                             "column_id": mc["column_id"]},
                })

        # PI aus DBC  (P = non-unique PI, Q = unique PI / UPI, K = PK-based PI)
        _PI_TYPES = {"P", "Q", "K"}
        dbc_pi_cols  = sorted(
            [r for r in dbc_idx if r.get("indextype", "").strip().upper() in _PI_TYPES],
            key=lambda r: r.get("columnposition", 0)
        )
        meta_pi = next((i for i in meta_idx if "PRIMARY" in (i.get("index_type") or "").upper()), None)

        indexes_diff = {
            "dbc_pi":  [r["columnname"] for r in dbc_pi_cols],
            "meta_pi": [c["column_name"] for c in meta_pi["columns"]] if meta_pi else [],
            "status":  "ok",
        }
        if indexes_diff["dbc_pi"] != indexes_diff["meta_pi"]:
            indexes_diff["status"] = "diff"

        return {
            "table_id":     table_id,
            "db_name":      db_name,
            "table_name":   table_name,
            "columns_diff": columns_diff,
            "indexes_diff": indexes_diff,
        }
    except Exception as e:
        return {"error": str(e)}


def sync_columns_from_dbc(table_id: int, db_name: str, table_name: str) -> dict:
    """
    Übernimmt Typ/Länge/Nullable für alle Spalten aus DBC.ColumnsV in META_COLUMN.
    Nur für Spalten die SOWOHL in DBC als auch META existieren.
    """
    try:
        diff = reverse_engineer(table_id, db_name, table_name)
        if "error" in diff:
            return diff

        updated = 0
        skipped = 0
        for col in diff["columns_diff"]:
            if col["status"] in ("diff",) and col["meta"] and col["dbc"]:
                result = update_column(
                    column_id  = col["meta"]["column_id"],
                    data_type  = col["dbc"]["type"],
                    data_length= col["dbc"]["length"],
                    nullable   = col["dbc"]["nullable"],
                )
                if result.get("updated"):
                    updated += 1
                else:
                    skipped += 1

        return {"updated": updated, "skipped": skipped}
    except Exception as e:
        return {"error": str(e)}


def get_column_panel(table_id: int) -> dict:
    """
    Bottom-Panel-Daten: DBC-Spalten (physisch, read-only) +
    META-Spalten (editierbar) nebeneinander.
    """
    try:
        # 1. Tabellen-Detail für db_name + table_name
        tbl = get_table_detail(table_id)
        if "error" in tbl:
            return tbl
        db_name    = tbl.get("db_name", "") or ""
        table_name = tbl.get("table_name", "") or ""

        # 2. META-Spalten (vollständig, inkl. neuer Flags)
        meta_cols = get_columns_full(table_id)

        # 3. PI-Spalten aus META_INDEX ableiten
        meta_idx = get_indexes(table_id)
        pi_col_ids: set = set()
        for idx in meta_idx:
            ix_type = (idx.get("index_type") or "").upper()
            if "PRIMARY" in ix_type and "SECONDARY" not in ix_type:
                for c in idx.get("columns", []):
                    pi_col_ids.add(c["column_id"])

        # 4. FK/PK aus META_FOREIGN_KEY ableiten
        fk_tbl  = f"{META_SCHEMA}.{META_TABLES['fk']}"
        fk_rows = _query(
            f"SELECT child_column_id FROM {fk_tbl} WHERE child_table_id = ?",
            (table_id,)
        )
        pk_rows = _query(
            f"SELECT parent_column_id FROM {fk_tbl} WHERE parent_table_id = ?",
            (table_id,)
        )
        fk_col_ids = {r["child_column_id"]  for r in fk_rows if r.get("child_column_id")}
        pk_col_ids = {r["parent_column_id"] for r in pk_rows if r.get("parent_column_id")}

        # 5. Abgeleitete DBC-Flags in META-Spalten eintragen
        #    Und META is_pk/is_fk/is_pi anreichern (abgeleiteter Wert hat Vorrang,
        #    weil PKs/FKs physisch nicht existieren aber logisch immer korrekt sind)
        for col in meta_cols:
            cid = col.get("column_id")
            col["_dbc_pi"] = "Y" if cid in pi_col_ids else "N"
            col["_dbc_fk"] = "Y" if cid in fk_col_ids else "N"
            col["_dbc_pk"] = "Y" if cid in pk_col_ids else "N"
            # META-Flags: gespeicherter Wert ODER abgeleiteter Wert (max)
            if col.get("_dbc_fk") == "Y":
                col["is_fk"] = "Y"
            if col.get("_dbc_pk") == "Y":
                col["is_pk"] = "Y"
            if col.get("_dbc_pi") == "Y":
                col["is_pi"] = "Y"

        # 6. DBC-Spalten aus DBC.ColumnsV (wenn db_name + table_name vorhanden)
        dbc_cols  = []
        dbc_error = None
        if db_name and table_name:
            try:
                dbc_sql = """
                    SELECT
                        TRIM(ColumnName)            AS column_name,
                        TRIM(ColumnType)            AS column_type,
                        ColumnLength                AS column_length,
                        DecimalTotalDigits          AS decimal_precision,
                        DecimalFractionalDigits     AS decimal_scale,
                        TRIM(Nullable)              AS nullable,
                        ColumnId                    AS column_position,
                        TRIM(CharType)              AS char_type
                    FROM DBC.ColumnsV
                    WHERE TRIM(DatabaseName) = TRIM(?)
                      AND TRIM(TableName)    = TRIM(?)
                    ORDER BY ColumnId
                """
                dbc_cols = _query(dbc_sql, (db_name.strip(), table_name.strip()))
                # DBC PI-Flags aus META_INDEX setzen
                pi_names = {
                    c["column_name"].upper()
                    for idx in meta_idx
                    for c in idx.get("columns", [])
                    if "PRIMARY" in (idx.get("index_type") or "").upper()
                    and "SECONDARY" not in (idx.get("index_type") or "").upper()
                }
                _CHARSET_MAP = {'L': 'LATIN', 'U': 'UNICODE'}
                for dc in dbc_cols:
                    dc["charset"] = _CHARSET_MAP.get(dc.pop("char_type", "") or "", None)
                    dc["_pi"] = "Y" if dc.get("column_name", "").upper() in pi_names else "N"
                    dc["_fk"] = "Y" if dc.get("column_name", "").upper() in {
                        c.get("column_name", "").upper()
                        for col in meta_cols if col.get("column_id") in fk_col_ids
                        for c in [col]
                    } else "N"
                    dc["_pk"] = "Y" if dc.get("column_name", "").upper() in {
                        c.get("column_name", "").upper()
                        for col in meta_cols if col.get("column_id") in pk_col_ids
                        for c in [col]
                    } else "N"
            except Exception as e:
                dbc_error = str(e)

        return {
            "table_id":   table_id,
            "table_name": table_name,
            "db_name":    db_name,
            "meta_cols":  meta_cols,
            "dbc_cols":   dbc_cols,
            "dbc_error":  dbc_error,
        }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# DM12 – DDL generieren + ausführen
# ---------------------------------------------------------------------------

def generate_ddl(table_id: int) -> dict:
    """CREATE TABLE DDL aus META_TABLE + META_COLUMN + META_INDEX generieren."""
    try:
        tbl = get_table_detail(table_id)
        if "error" in tbl:
            return tbl

        db_name    = (tbl.get("db_name")    or "").strip()
        table_name = (tbl.get("table_name") or "").strip()
        if not db_name or not table_name:
            return {"error": "db_name oder table_name fehlt"}

        cols    = get_columns_full(table_id)
        indexes = get_indexes(table_id)

        col_defs = []
        for c in cols:
            dtype = (c.get("data_type") or "").strip()
            parts = [f"    {c['column_name']}  {dtype}"]

            cs = (c.get("charset") or "").strip()
            if cs:
                parts.append(f"CHARACTER SET {cs}")
            if cs:
                cs_flag = (c.get("is_casespecific") or "N").strip()
                parts.append("CASESPECIFIC" if cs_flag == "Y" else "NOT CASESPECIFIC")

            null_flag = (c.get("nullable") or "Y").strip()
            parts.append("NULL" if null_flag == "Y" else "NOT NULL")

            dv = c.get("default_value")
            if dv:
                parts.append(f"DEFAULT {dv}")

            col_defs.append(" ".join(parts))

        # PI ermitteln
        pi_clause = "NO PRIMARY INDEX"
        for idx in indexes:
            it = (idx.get("index_type") or "").upper()
            if "PRIMARY" in it and "SECONDARY" not in it:
                unique = "UNIQUE " if (idx.get("is_unique") or "N").strip() == "Y" else ""
                cols_str = ", ".join(c["column_name"] for c in sorted(
                    idx.get("columns", []), key=lambda x: x.get("column_position", 0)
                ))
                pi_clause = f"{unique}PRIMARY INDEX ({cols_str})"
                break

        ddl = (
            f"CREATE MULTISET TABLE {db_name}.{table_name},\n"
            f"     NO FALLBACK,\n"
            f"     NO BEFORE JOURNAL,\n"
            f"     NO AFTER JOURNAL\n"
            f"(\n"
            + ",\n".join(col_defs)
            + f"\n)\n{pi_clause};"
        )

        return {"ddl": ddl, "table_name": table_name, "db_name": db_name}
    except Exception as e:
        return {"error": str(e)}


def execute_ddl(ddl_text: str) -> dict:
    """Beliebiges DDL-Statement gegen Teradata ausführen."""
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl_text)
                conn.commit()
        return {"ok": True, "message": "DDL erfolgreich ausgeführt"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# DM13 – Maintenance
# ---------------------------------------------------------------------------

def get_table_stats(table_id: int) -> dict:
    """Row-Count + CurrentPerm für eine Tabelle abfragen."""
    try:
        tbl = get_table_detail(table_id)
        if "error" in tbl:
            return tbl
        db_name    = (tbl.get("db_name")    or "").strip()
        table_name = (tbl.get("table_name") or "").strip()
        if not db_name or not table_name:
            return {"error": "db_name oder table_name fehlt"}

        row_count = None
        try:
            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) FROM {db_name}.{table_name}")
                    row_count = int(cur.fetchone()[0])
        except Exception as e:
            row_count = f"Fehler: {e}"

        perm_bytes = None
        try:
            rows = _query(
                "SELECT SUM(CurrentPerm) AS perm FROM DBC.TableSizeV "
                "WHERE TRIM(DatabaseName)=TRIM(?) AND TRIM(TableName)=TRIM(?)",
                (db_name, table_name),
            )
            if rows:
                perm_bytes = rows[0].get("perm")
        except Exception:
            pass

        return {
            "row_count":  row_count,
            "perm_bytes": perm_bytes,
            "db_name":    db_name,
            "table_name": table_name,
        }
    except Exception as e:
        return {"error": str(e)}


def delete_from_meta(table_id: int) -> dict:
    """Tabelle + alle abhängigen META-Einträge vollständig löschen (CASCADE)."""
    try:
        fk_tbl  = f"{META_SCHEMA}.{META_TABLES['fk']}"
        ic_tbl  = f"{META_SCHEMA}.{META_TABLES['index_col']}"
        idx_tbl = f"{META_SCHEMA}.{META_TABLES['index']}"
        col_tbl = f"{META_SCHEMA}.{META_TABLES['columns']}"
        tbl_tbl = f"{META_SCHEMA}.{META_TABLES['tables']}"

        with _connect() as conn:
            with conn.cursor() as cur:
                # 1. FKs (als Child UND Parent)
                cur.execute(
                    f"DELETE FROM {fk_tbl} WHERE child_table_id=? OR parent_table_id=?",
                    (table_id, table_id),
                )
                # 2. Index-Columns
                cur.execute(
                    f"DELETE FROM {ic_tbl} WHERE index_id IN "
                    f"(SELECT index_id FROM {idx_tbl} WHERE table_id=?)",
                    (table_id,),
                )
                # 3. Indexes
                cur.execute(f"DELETE FROM {idx_tbl} WHERE table_id=?", (table_id,))
                # 4. Columns
                cur.execute(f"DELETE FROM {col_tbl} WHERE table_id=?", (table_id,))
                # 5. Table
                cur.execute(f"DELETE FROM {tbl_tbl} WHERE table_id=?", (table_id,))
                conn.commit()

        # Alle relevanten Caches leeren
        for k in list(_CACHE.keys()):
            _CACHE.pop(k, None)

        return {"ok": True, "message": f"table_id {table_id} vollständig aus META gelöscht"}
    except Exception as e:
        return {"error": str(e)}


def drop_from_db(table_id: int) -> dict:
    """DROP TABLE in Teradata ausführen (irreversibel!)."""
    try:
        tbl = get_table_detail(table_id)
        if "error" in tbl:
            return tbl
        db_name    = (tbl.get("db_name")    or "").strip()
        table_name = (tbl.get("table_name") or "").strip()
        if not db_name or not table_name:
            return {"error": "db_name oder table_name fehlt"}

        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE {db_name}.{table_name}")
                conn.commit()
        return {"ok": True, "message": f"DROP TABLE {db_name}.{table_name} ausgeführt"}
    except Exception as e:
        return {"error": str(e)}


def truncate_table(table_id: int) -> dict:
    """Alle Zeilen einer Tabelle löschen (DELETE ALL)."""
    try:
        tbl = get_table_detail(table_id)
        if "error" in tbl:
            return tbl
        db_name    = (tbl.get("db_name")    or "").strip()
        table_name = (tbl.get("table_name") or "").strip()
        if not db_name or not table_name:
            return {"error": "db_name oder table_name fehlt"}

        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {db_name}.{table_name} ALL")
                conn.commit()
        return {"ok": True, "message": f"DELETE ALL {db_name}.{table_name} ausgeführt"}
    except Exception as e:
        return {"error": str(e)}

