"""
DDL Executor für Metadata-Driven ETL Framework
==============================================

Python Modul für STEP_CATEGORY='DDL'.
Führt DDL-Operationen (DROP/CREATE TABLE) basierend auf META_ETL_JOB_STEP.PARAMETERS aus.

Autor: DWH MVP Team
Datum: 2026-03-25
Version: 1.0

Usage in META_ETL_JOB_STEP:
    STEP_CATEGORY    = 'DDL'
    PYTHON_MODULE    = 'ddl_executor'
    PYTHON_FUNCTION  = 'drop_tables' | 'create_tables'
    PARAMETERS       = {
        "target_database": "<aus Job-Config>",
        "target_table": "Culture",
        "columns": [...],
        "use_staging": true,
        "staging_suffix": "_LOAD"
    }
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional

try:
    import teradatasql
except ImportError:
    teradatasql = None

# Zentrale Pfad-Konfiguration (gemäß PRINCIPLES.md)
try:
    from ..config import PATHS
except ImportError:
    # Fallback für direkte Ausführung
    PATHS = {
        "ddl_output": Path("/home/tdops/ps_toolbox/PS_ROOT/subsystem/metadaita/ddl/generated"),
    }

logger = logging.getLogger(__name__)

# DDL Output-Verzeichnis aus zentraler Config
DDL_OUTPUT_DIR = PATHS.get("ddl_output", Path("/tmp/ddl_generated"))


# =============================================================================
# DDL File Helpers
# =============================================================================

def _save_ddl_to_file(
    ddl_statements: List[str],
    table_name: str,
    operation: str,
    job_id: Optional[int] = None
) -> Path:
    """
    Speichert DDL-Statements in eine Datei für Nachvollziehbarkeit.
    
    Args:
        ddl_statements: Liste von DDL-Statements
        table_name: Name der Tabelle
        operation: 'CREATE' oder 'DROP'
        job_id: Optional ETL Job ID
    
    Returns:
        Pfad zur erstellten DDL-Datei
    """
    # Verzeichnis erstellen falls nicht vorhanden
    DDL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Dateiname: YYYYMMDD_HHMMSS_{table}_{operation}.sql
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_prefix = f"job{job_id}_" if job_id else ""
    filename = f"{timestamp}_{job_prefix}{table_name}_{operation}.sql"
    filepath = DDL_OUTPUT_DIR / filename
    
    # DDL-Content zusammenbauen
    header = f"""-- =============================================================================
-- DDL: {operation} {table_name}
-- Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
-- Job ID: {job_id or 'N/A'}
-- =============================================================================

"""
    
    content = header + "\n\n".join(ddl_statements)
    
    # Datei schreiben
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info(f"DDL gespeichert: {filepath}")
    return filepath

def drop_tables(
    conn: 'teradatasql.TeradataConnection',
    parameters: Dict[str, Any],
    context: Dict[str, Any] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Löscht Target- und Staging-Tabellen (optional).
    
    Workflow:
        1. DROP DDL generieren
        2. DDL in Datei speichern (für Nachvollziehbarkeit)
        3. DDL ausführen
    
    Diese Funktion wird vom Orchestrator aufgerufen wenn:
        STEP_CATEGORY    = 'DDL'
        PYTHON_MODULE    = 'ddl_executor'
        PYTHON_FUNCTION  = 'drop_tables'
    
    Args:
        conn: Teradata Connection
        parameters: Dict mit target_database, target_table, use_staging, staging_suffix
        context: Optional zusätzlicher Kontext (enthält job_id)
    
    Returns:
        Tuple (success: bool, result: Dict)
    """
    target_db = parameters.get('target_database')
    target_table = parameters.get('target_table')
    use_staging = parameters.get('use_staging', True)
    staging_suffix = parameters.get('staging_suffix', '_LOAD')
    
    # Job ID aus Kontext für Dateinamen
    job_id = context.get('job_id') if context else None
    
    if not target_db:
        return (False, {"error_message": "target_database nicht in parameters"})
    if not target_table:
        return (False, {"error_message": "target_table nicht in parameters"})
    
    # =========================================================================
    # SCHRITT 1: DROP DDL generieren
    # =========================================================================
    ddl_statements = []
    tables_to_drop = []
    
    # Target-Tabelle
    target_fqn = f"{target_db}.{target_table}"
    target_ddl = f"DROP TABLE {target_fqn};"
    ddl_statements.append(target_ddl)
    tables_to_drop.append(('target', target_fqn, target_ddl))
    
    # Staging-Tabelle (wenn use_staging=true)
    if use_staging:
        staging_fqn = f"{target_db}.{target_table}{staging_suffix}"
        staging_ddl = f"DROP TABLE {staging_fqn};"
        ddl_statements.append(staging_ddl)
        tables_to_drop.append(('staging', staging_fqn, staging_ddl))
    
    # =========================================================================
    # SCHRITT 2: DDL in Datei speichern
    # =========================================================================
    try:
        ddl_file = _save_ddl_to_file(
            ddl_statements=ddl_statements,
            table_name=target_table,
            operation='DROP',
            job_id=job_id
        )
        logger.info(f"DROP DDL für {target_table} gespeichert: {ddl_file}")
    except Exception as e:
        logger.error(f"Fehler beim Speichern der DDL-Datei: {e}")
        ddl_file = None
    
    # =========================================================================
    # SCHRITT 3: DDL ausführen
    # =========================================================================
    cursor = conn.cursor()
    dropped_tables = []
    errors = []
    
    for table_type, table_fqn, ddl in tables_to_drop:
        try:
            # Semikolon entfernen für Teradata execute
            ddl_clean = ddl.rstrip(';')
            cursor.execute(ddl_clean)
            conn.commit()  # COMMIT nach DDL erforderlich!
            dropped_tables.append(table_fqn)
            logger.info(f"Dropped {table_type} table: {table_fqn}")
        except Exception as e:
            if '3807' in str(e):  # Object does not exist
                logger.debug(f"{table_type.capitalize()} table not found (OK): {table_fqn}")
            else:
                errors.append(f"{table_fqn}: {str(e)}")
                logger.warning(f"Error dropping {table_fqn}: {e}")
    
    # Non-critical step - Fehler sind OK
    result = {
        "dropped_tables": dropped_tables,
        "ddl_file": str(ddl_file) if ddl_file else None,
        "errors": errors if errors else None,
        "message": f"Drop completed: {len(dropped_tables)} tables dropped"
    }
    
    return (True, result)  # Immer success, da non-critical


# =============================================================================
# Create Tables
# =============================================================================

def create_tables(
    conn: 'teradatasql.TeradataConnection',
    parameters: Dict[str, Any],
    context: Dict[str, Any] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Erstellt Target- und Staging-Tabellen.
    
    Workflow:
        1. DDL generieren
        2. DDL in Datei speichern (für Nachvollziehbarkeit)
        3. DDL ausführen
    
    Diese Funktion wird vom Orchestrator aufgerufen wenn:
        STEP_CATEGORY    = 'DDL'
        PYTHON_MODULE    = 'ddl_executor'
        PYTHON_FUNCTION  = 'create_tables'
    
    Args:
        conn: Teradata Connection
        parameters: Dict mit target_database, target_table, columns, use_staging, staging_suffix
        context: Optional zusätzlicher Kontext (enthält job_id)
    
    Returns:
        Tuple (success: bool, result: Dict)
    """
    target_db = parameters.get('target_database')
    target_table = parameters.get('target_table')
    columns = parameters.get('columns', [])
    use_staging = parameters.get('use_staging', True)
    staging_suffix = parameters.get('staging_suffix', '_LOAD')
    
    # Job ID aus Kontext für Dateinamen
    job_id = context.get('job_id') if context else None
    
    if not target_db:
        return (False, {"error_message": "target_database nicht in parameters"})
    if not target_table:
        return (False, {"error_message": "target_table nicht in parameters"})
    
    if not columns:
        return (False, {"error_message": "columns nicht in parameters"})
    
    # =========================================================================
    # SCHRITT 1: DDL generieren
    # =========================================================================
    column_defs = _generate_column_definitions(columns)
    ddl_statements = []
    tables_to_create = []
    
    # Target-Tabelle DDL
    target_fqn = f"{target_db}.{target_table}"
    target_ddl = f"""CREATE MULTISET TABLE {target_fqn}, NO FALLBACK
(
{column_defs}
)
NO PRIMARY INDEX;"""
    ddl_statements.append(target_ddl)
    tables_to_create.append(('target', target_fqn, target_ddl))
    
    # Staging-Tabelle DDL (wenn use_staging=true)
    if use_staging:
        staging_fqn = f"{target_db}.{target_table}{staging_suffix}"
        staging_ddl = f"""CREATE MULTISET TABLE {staging_fqn}, NO FALLBACK
(
{column_defs}
)
NO PRIMARY INDEX;"""
        ddl_statements.append(staging_ddl)
        tables_to_create.append(('staging', staging_fqn, staging_ddl))
    
    # =========================================================================
    # SCHRITT 2: DDL in Datei speichern
    # =========================================================================
    try:
        ddl_file = _save_ddl_to_file(
            ddl_statements=ddl_statements,
            table_name=target_table,
            operation='CREATE',
            job_id=job_id
        )
        logger.info(f"DDL für {target_table} gespeichert: {ddl_file}")
    except Exception as e:
        logger.error(f"Fehler beim Speichern der DDL-Datei: {e}")
        # Fahren fort, auch wenn Speichern fehlschlägt
        ddl_file = None
    
    # =========================================================================
    # SCHRITT 3: DDL ausführen
    # =========================================================================
    cursor = conn.cursor()
    created_tables = []
    errors = []
    
    for table_type, table_fqn, ddl in tables_to_create:
        try:
            # Semikolon entfernen für Teradata execute
            ddl_clean = ddl.rstrip(';')
            cursor.execute(ddl_clean)
            conn.commit()  # COMMIT nach DDL erforderlich!
            created_tables.append(table_fqn)
            logger.info(f"Created {table_type} table: {table_fqn}")
        except Exception as e:
            if '3803' in str(e):  # Table already exists
                logger.warning(f"{table_type.capitalize()} table already exists: {table_fqn}")
                created_tables.append(f"{table_fqn} (already exists)")
            else:
                error_msg = f"{table_fqn}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"Error creating {table_fqn}: {e}")
                # Bei Target-Tabelle Fehler -> Abbruch
                if table_type == 'target':
                    return (False, {
                        "error_message": str(e),
                        "ddl": ddl,
                        "ddl_file": str(ddl_file) if ddl_file else None
                    })
    
    # Ergebnis
    success = len(errors) == 0
    result = {
        "created_tables": created_tables,
        "ddl_file": str(ddl_file) if ddl_file else None,
        "errors": errors if errors else None,
        "message": f"Create completed: {len(created_tables)} tables created",
        "error_message": "; ".join(errors) if errors else None
    }
    
    return (success, result)


def _generate_column_definitions(columns: List[Dict]) -> str:
    """
    Generiert Spalten-Definitionen für CREATE TABLE.
    
    Args:
        columns: Liste von Spalten mit td_type, target_name, nullable
    
    Returns:
        Komma-separierte Spalten-Definitionen
    """
    defs = []
    
    for col in columns:
        col_name = col.get('target_name') or col.get('source_name') or col.get('column_name')
        col_type = col.get('td_type') or col.get('target_type') or 'VARCHAR(255)'
        nullable = col.get('nullable', True)
        
        if not col_name:
            continue
        
        null_clause = "" if nullable else " NOT NULL"
        defs.append(f"    {col_name} {col_type}{null_clause}")
    
    return ",\n".join(defs)
