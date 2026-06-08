"""
Metadata Sync Service
=====================

Service für den Abgleich zwischen:
- Physische Teradata-Strukturen (dbc.tablesV, dbc.columnsV)
- META_TABLE / META_COLUMN (Metadaten-Katalog)
- Job-Parameter (ETL-Jobs)

Funktionen:
- import_table_from_dbc(): Neue Tabelle aus dbc importieren
- sync_columns_from_dbc(): Spalten einer existierenden Tabelle aktualisieren
- compare_meta_with_dbc(): Abweichungen erkennen

Autor: DWH MVP Team
Datum: 2026-04-15
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    import teradatasql
except ImportError:
    raise ImportError("teradatasql not installed")

logger = logging.getLogger(__name__)


class MetadataSyncService:
    """Service für Metadaten-Synchronisation zwischen dbc und META-Schema"""
    
    def __init__(self, db_config: dict):
        """
        Initialisiert Service mit Datenbankverbindung.
        
        Args:
            db_config: Dict mit host, user, password
        """
        self.db_config = db_config
    
    def _get_connection(self):
        """Erstellt Teradata-Verbindung"""
        return teradatasql.connect(
            host=self.db_config.get("host", "192.168.114.21"),
            user=self.db_config.get("user", "dbc"),
            password=self.db_config.get("password", "dbc"),
            connect_timeout=self.db_config.get("connect_timeout", 10000)
        )
    
    # =========================================================================
    # Haupt-Methoden
    # =========================================================================
    
    def import_table_from_dbc(self, database_id: int, table_name: str) -> dict:
        """
        Importiert eine Tabelle mit Spalten aus dbc in META_TABLE/META_COLUMN.
        
        Args:
            database_id: ID der Datenbank in META_DATABASE
            table_name: Name der zu importierenden Tabelle
            
        Returns:
            dict mit success, table_id, table_name, columns_imported oder error
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Hole Database-Name und layer_id
            cursor.execute(
                "SELECT database_name, layer_id FROM MDP01_META.META_DATABASE WHERE database_id = ?", 
                (database_id,)
            )
            db_row = cursor.fetchone()
            if not db_row:
                return {"error": f"Database {database_id} nicht gefunden"}
            
            database_name = db_row[0]
            layer_id = db_row[1]
            
            # Prüfe ob Tabelle schon existiert
            cursor.execute("""
                SELECT table_id FROM MDP01_META.META_TABLE 
                WHERE database_id = ? AND UPPER(table_name) = UPPER(?)
            """, (database_id, table_name))
            if cursor.fetchone():
                return {"error": f"Tabelle {table_name} existiert bereits in META_TABLE"}
            
            # Hole Tabellen-Info aus dbc
            cursor.execute("""
                SELECT tablename, commentstring FROM dbc.tablesV 
                WHERE databasename = ? AND UPPER(tablename) = UPPER(?)
            """, (database_name, table_name))
            tbl_row = cursor.fetchone()
            if not tbl_row:
                return {"error": f"Tabelle {table_name} nicht in {database_name} gefunden"}
            
            actual_table_name = tbl_row[0]
            table_comment = tbl_row[1]
            
            # Nächste table_id
            cursor.execute("SELECT COALESCE(MAX(table_id), 0) + 1 FROM MDP01_META.META_TABLE")
            next_table_id = cursor.fetchone()[0]
            
            # Tabelle einfügen (korrekte Spaltennamen!)
            cursor.execute("""
                INSERT INTO MDP01_META.META_TABLE (
                    table_id, database_id, table_name, layer_id, is_historized,
                    comment_string, CREATE_TIMESTAMP, LAST_ALTER_TIMESTAMP
                ) VALUES (?, ?, ?, ?, 'N', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (next_table_id, database_id, actual_table_name, layer_id, table_comment))
            
            # Spalten aus dbc holen
            columns = self.get_actual_columns_from_dbc(database_name, actual_table_name)
            
            # Spalten einfügen
            inserted_columns = 0
            for col in columns:
                cursor.execute("SELECT COALESCE(MAX(column_id), 0) + 1 FROM MDP01_META.META_COLUMN")
                next_col_id = cursor.fetchone()[0]
                
                # Datatype lookup
                cursor.execute("""
                    SELECT datatype_id FROM MDP01_META.META_DATATYPE 
                    WHERE teradata_type = ? SAMPLE 1
                """, (col["column_type"],))
                dt_row = cursor.fetchone()
                datatype_id = dt_row[0] if dt_row else 1
                
                # Spalte einfügen (META_COLUMN hat andere Spaltennamen als META_TABLE!)
                cursor.execute("""
                    INSERT INTO MDP01_META.META_COLUMN (
                        column_id, table_id, column_name, column_position,
                        datatype_id, column_type, column_length, nullable,
                        ersterfassungsdatum, aenderungsdatum
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (next_col_id, next_table_id, col["column_name"], col["position"],
                      datatype_id, col["column_type"], col["length"],
                      'Y' if col["nullable"] else 'N'))
                inserted_columns += 1
            
            conn.commit()
            
            logger.info(f"Tabelle {actual_table_name} importiert: {inserted_columns} Spalten")
            
            return {
                "success": True,
                "table_id": next_table_id,
                "table_name": actual_table_name,
                "columns_imported": inserted_columns
            }
            
        except Exception as e:
            logger.error(f"Fehler beim Import von {table_name}: {e}")
            conn.rollback()
            return {"error": str(e)}
        finally:
            conn.close()
    
    def sync_columns_from_dbc(self, table_id: int) -> dict:
        """
        Synchronisiert die Spalten einer existierenden Tabelle mit dbc.
        
        - Neue Spalten werden hinzugefügt
        - Geänderte Spalten werden aktualisiert (Typ, Länge, Nullable)
        - Gelöschte Spalten werden markiert (nicht physisch gelöscht)
        
        Args:
            table_id: ID der Tabelle in META_TABLE
            
        Returns:
            dict mit added, updated, removed counts oder error
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Hole Tabellen-Info
            cursor.execute("""
                SELECT t.table_name, d.database_name
                FROM MDP01_META.META_TABLE t
                JOIN MDP01_META.META_DATABASE d ON t.database_id = d.database_id
                WHERE t.table_id = ?
            """, (table_id,))
            
            row = cursor.fetchone()
            if not row:
                return {"error": "Tabelle nicht gefunden"}
            
            table_name = row[0]
            database_name = row[1]
            
            # Aktuelle Spalten aus META_COLUMN
            cursor.execute("""
                SELECT column_id, column_name, column_type, column_length, nullable
                FROM MDP01_META.META_COLUMN
                WHERE table_id = ?
            """, (table_id,))
            
            meta_columns = {r[1].upper(): {
                "column_id": r[0],
                "column_name": r[1],
                "column_type": r[2],
                "column_length": r[3],
                "nullable": r[4]
            } for r in cursor.fetchall()}
            
            # Aktuelle Spalten aus dbc
            dbc_columns = self.get_actual_columns_from_dbc(database_name, table_name)
            dbc_column_names = {col["column_name"].upper() for col in dbc_columns}
            
            added = 0
            updated = 0
            removed = 0
            
            # Neue/geänderte Spalten verarbeiten
            for col in dbc_columns:
                col_name_upper = col["column_name"].upper()
                
                if col_name_upper not in meta_columns:
                    # Neue Spalte hinzufügen
                    cursor.execute("SELECT COALESCE(MAX(column_id), 0) + 1 FROM MDP01_META.META_COLUMN")
                    next_col_id = cursor.fetchone()[0]
                    
                    # Datatype lookup
                    cursor.execute("""
                        SELECT datatype_id FROM MDP01_META.META_DATATYPE 
                        WHERE teradata_type = ? SAMPLE 1
                    """, (col["column_type"],))
                    dt_row = cursor.fetchone()
                    datatype_id = dt_row[0] if dt_row else 1
                    
                    cursor.execute("""
                        INSERT INTO MDP01_META.META_COLUMN (
                            column_id, table_id, column_name, column_position,
                            datatype_id, column_type, column_length, nullable,
                            ersterfassungsdatum, aenderungsdatum
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """, (next_col_id, table_id, col["column_name"], col["position"],
                          datatype_id, col["column_type"], col["length"],
                          'Y' if col["nullable"] else 'N'))
                    added += 1
                    
                else:
                    # Prüfen ob Update nötig
                    meta_col = meta_columns[col_name_upper]
                    needs_update = False
                    
                    if meta_col["column_type"] != col["column_type"]:
                        needs_update = True
                    if meta_col["column_length"] != col["length"]:
                        needs_update = True
                    if (meta_col["nullable"] == 'Y') != col["nullable"]:
                        needs_update = True
                    
                    if needs_update:
                        cursor.execute("""
                            UPDATE MDP01_META.META_COLUMN
                            SET column_type = ?,
                                column_length = ?,
                                nullable = ?,
                                aenderungsdatum = CURRENT_TIMESTAMP
                            WHERE column_id = ?
                        """, (col["column_type"], col["length"],
                              'Y' if col["nullable"] else 'N',
                              meta_col["column_id"]))
                        updated += 1
            
            # Gelöschte Spalten markieren (in dbc nicht mehr vorhanden)
            for col_name_upper, meta_col in meta_columns.items():
                if col_name_upper not in dbc_column_names:
                    # Spalte existiert nicht mehr in dbc - markieren
                    cursor.execute("""
                        UPDATE MDP01_META.META_COLUMN
                        SET column_type = COLUMN_TYPE || ' [DELETED]',
                            aenderungsdatum = CURRENT_TIMESTAMP
                        WHERE column_id = ?
                          AND column_type NOT LIKE '%[DELETED]%'
                    """, (meta_col["column_id"],))
                    if cursor.rowcount > 0:
                        removed += 1
            
            conn.commit()
            
            logger.info(f"Sync für {table_name}: +{added} ~{updated} -{removed}")
            
            return {
                "success": True,
                "table_name": table_name,
                "added": added,
                "updated": updated,
                "removed": removed
            }
            
        except Exception as e:
            logger.error(f"Fehler beim Sync von table_id {table_id}: {e}")
            conn.rollback()
            return {"error": str(e)}
        finally:
            conn.close()
    
    def compare_meta_with_dbc(self, table_id: int) -> dict:
        """
        Vergleicht META_COLUMN mit dbc.columnsV für eine Tabelle.
        Zeigt Abweichungen auf ohne Änderungen vorzunehmen.
        
        Args:
            table_id: ID der Tabelle in META_TABLE
            
        Returns:
            dict mit differences (Liste von Abweichungen) oder error
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Hole Tabellen-Info
            cursor.execute("""
                SELECT t.table_name, d.database_name
                FROM MDP01_META.META_TABLE t
                JOIN MDP01_META.META_DATABASE d ON t.database_id = d.database_id
                WHERE t.table_id = ?
            """, (table_id,))
            
            row = cursor.fetchone()
            if not row:
                return {"error": "Tabelle nicht gefunden"}
            
            table_name = row[0]
            database_name = row[1]
            
            # META_COLUMN laden
            cursor.execute("""
                SELECT column_name, column_type, column_length, nullable, column_position
                FROM MDP01_META.META_COLUMN
                WHERE table_id = ?
                ORDER BY column_position
            """, (table_id,))
            
            meta_columns = {r[0].upper(): {
                "column_name": r[0],
                "column_type": r[1],
                "column_length": r[2],
                "nullable": r[3],
                "position": r[4],
                "source": "META"
            } for r in cursor.fetchall()}
            
            # dbc.columnsV laden
            dbc_columns_list = self.get_actual_columns_from_dbc(database_name, table_name)
            dbc_columns = {col["column_name"].upper(): {
                "column_name": col["column_name"],
                "column_type": col["column_type"],
                "column_length": col["length"],
                "nullable": 'Y' if col["nullable"] else 'N',
                "position": col["position"],
                "source": "DBC"
            } for col in dbc_columns_list}
            
            differences = []
            
            # Spalten die nur in META sind
            for col_name in meta_columns:
                if col_name not in dbc_columns:
                    differences.append({
                        "column_name": meta_columns[col_name]["column_name"],
                        "type": "ONLY_IN_META",
                        "message": "Spalte existiert nur in META_COLUMN, nicht in dbc"
                    })
            
            # Spalten die nur in dbc sind
            for col_name in dbc_columns:
                if col_name not in meta_columns:
                    differences.append({
                        "column_name": dbc_columns[col_name]["column_name"],
                        "type": "ONLY_IN_DBC",
                        "message": "Spalte existiert nur in dbc, nicht in META_COLUMN"
                    })
            
            # Spalten mit Unterschieden
            for col_name in meta_columns:
                if col_name in dbc_columns:
                    meta = meta_columns[col_name]
                    dbc = dbc_columns[col_name]
                    
                    diffs = []
                    if meta["column_type"] != dbc["column_type"]:
                        diffs.append(f"Typ: META={meta['column_type']} vs DBC={dbc['column_type']}")
                    if meta["column_length"] != dbc["column_length"]:
                        diffs.append(f"Länge: META={meta['column_length']} vs DBC={dbc['column_length']}")
                    if meta["nullable"] != dbc["nullable"]:
                        diffs.append(f"Nullable: META={meta['nullable']} vs DBC={dbc['nullable']}")
                    if meta["position"] != dbc["position"]:
                        diffs.append(f"Position: META={meta['position']} vs DBC={dbc['position']}")
                    
                    if diffs:
                        differences.append({
                            "column_name": meta["column_name"],
                            "type": "MISMATCH",
                            "message": "; ".join(diffs)
                        })
            
            return {
                "success": True,
                "table_name": table_name,
                "database_name": database_name,
                "meta_column_count": len(meta_columns),
                "dbc_column_count": len(dbc_columns),
                "differences": differences,
                "is_in_sync": len(differences) == 0
            }
            
        except Exception as e:
            logger.error(f"Fehler beim Vergleich von table_id {table_id}: {e}")
            return {"error": str(e)}
        finally:
            conn.close()
    
    # =========================================================================
    # Hilfs-Methoden
    # =========================================================================
    
    def get_actual_columns_from_dbc(self, database_name: str, table_name: str) -> list:
        """
        Liest die echten Spalten aus dbc.columnsV.
        
        Args:
            database_name: Teradata Database-Name
            table_name: Teradata Tabellen-Name
            
        Returns:
            Liste von dicts mit column_name, position, column_type, length, nullable etc.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    ColumnName,
                    ColumnId,
                    ColumnType,
                    ColumnLength,
                    DecimalTotalDigits,
                    DecimalFractionalDigits,
                    Nullable,
                    DefaultValue,
                    ColumnFormat,
                    CommentString
                FROM dbc.columnsV
                WHERE DatabaseName = ?
                  AND TableName = ?
                ORDER BY ColumnId
            """, (database_name.upper(), table_name.upper()))
            
            columns = []
            for row in cursor.fetchall():
                columns.append({
                    "column_name": row[0].strip() if row[0] else None,
                    "position": row[1],
                    "column_type": row[2].strip() if row[2] else None,
                    "length": row[3],
                    "decimal_total": row[4],
                    "decimal_fractional": row[5],
                    "nullable": row[6] == 'Y' if row[6] else True,
                    "default_value": row[7],
                    "format": row[8],
                    "comment": row[9]
                })
            
            return columns
            
        finally:
            conn.close()
    
    def get_tables_needing_sync(self, database_id: int = None) -> list:
        """
        Findet Tabellen die möglicherweise einen Sync brauchen.
        
        Args:
            database_id: Optional - nur Tabellen dieser Datenbank
            
        Returns:
            Liste von Tabellen mit Sync-Status
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            query = """
                SELECT t.table_id, t.table_name, d.database_name,
                       t.LAST_ALTER_TIMESTAMP as meta_last_alter
                FROM MDP01_META.META_TABLE t
                JOIN MDP01_META.META_DATABASE d ON t.database_id = d.database_id
            """
            params = []
            
            if database_id:
                query += " WHERE t.database_id = ?"
                params.append(database_id)
            
            query += " ORDER BY d.database_name, t.table_name"
            
            cursor.execute(query, params)
            
            tables = []
            for row in cursor.fetchall():
                tables.append({
                    "table_id": row[0],
                    "table_name": row[1],
                    "database_name": row[2],
                    "meta_last_alter": row[3].isoformat() if row[3] else None
                })
            
            return tables
            
        finally:
            conn.close()


# =============================================================================
# Service-Instanz erstellen
# =============================================================================

def create_metadata_sync_service(config_path: str = None) -> MetadataSyncService:
    """
    Factory-Funktion für MetadataSyncService.
    
    Args:
        config_path: Pfad zur database.yml (optional)
        
    Returns:
        MetadataSyncService Instanz
    """
    import yaml
    from pathlib import Path
    
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent.parent / "cfg" / "database.yml"
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    db_config = config.get("teradata", {})
    
    return MetadataSyncService(db_config)
