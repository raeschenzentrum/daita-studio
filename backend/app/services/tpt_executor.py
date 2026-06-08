"""
TPT Executor für Metadata-Driven ETL Framework
==============================================

Python Modul für STEP_CATEGORY='TPT_LOAD'.
Führt TPT (tbuild) Jobs aus basierend auf META_ETL_JOB_STEP.PARAMETERS.

Autor: DWH MVP Team
Datum: 2026-03-18
Version: 1.0

Usage in META_ETL_JOB_STEP:
    STEP_CATEGORY    = 'TPT_LOAD'
    PYTHON_MODULE    = 'tpt_executor'
    PYTHON_FUNCTION  = 'run_tpt_load'
    PARAMETERS       = {
        "source_system_id": 1,
        "source_table": "TAAA_PERSON",
        "target_database": "<aus META_LAYER>",
        "target_table": "TAAA_PERSON",
        "tpt_script_path": "/path/to/script.tpt",  -- ODER generate=true
        "tpt_generate": false,
        "tpt_operator_type": "UPDATE",
        "tpt_max_sessions": 4,
        "tpt_min_sessions": 1,
        "use_staging": true,
        "staging_suffix": "_LOAD"
    }
"""

import subprocess
import logging
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

try:
    import teradatasql
except ImportError:
    teradatasql = None

# Zentrale Pfad-Konfiguration
try:
    from ..config import PATHS
except ImportError:
    # Fallback für direkte Ausführung
    PATHS = {
        "ddl_output": Path("/home/tdops/ps_toolbox/PS_ROOT/subsystem/metadaita/ddl/generated"),
    }

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

DEFAULT_TPT_SCRIPT_DIR = '/tmp/tpt_scripts'
DEFAULT_TPT_LOG_DIR = '/tmp/tpt_logs'


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TPTResult:
    """Ergebnis einer TPT-Ausführung."""
    success: bool
    return_code: int
    rows_loaded: int = 0
    rows_rejected: int = 0
    duration_seconds: float = 0.0
    tpt_log_path: Optional[str] = None
    error_message: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    tpt_command: Optional[str] = None
    tpt_script_path: Optional[str] = None


@dataclass
class SourceSystemInfo:
    """Verbindungsinfos aus META_SOURCE_SYSTEM."""
    source_system_id: int
    source_system_name: str
    source_system_code: str
    source_type: str
    odbc_dsn_name: Optional[str]
    default_schema: Optional[str]
    credential_user_wallet: Optional[str]
    credential_password_wallet: Optional[str]


# =============================================================================
# Main Function (called by Orchestrator)
# =============================================================================

def run_tpt_load(
    conn: 'teradatasql.TeradataConnection',
    parameters: Dict[str, Any],
    context: Dict[str, Any] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Führt einen TPT Load aus.
    
    Diese Funktion wird vom Orchestrator aufgerufen wenn:
        STEP_CATEGORY = 'TPT_LOAD'
        PYTHON_MODULE = 'tpt_executor'
        PYTHON_FUNCTION = 'run_tpt_load'
    
    Args:
        conn: Teradata Connection (für META_SOURCE_SYSTEM Lookup)
        parameters: Parameter aus META_ETL_JOB_STEP.PARAMETERS (JSON)
        context: Zusätzlicher Kontext vom Orchestrator (job_id, step_id, etc.)
    
    Returns:
        Tuple (success: bool, metrics: Dict)
        metrics enthält: rows_loaded, rows_rejected, tpt_return_code, etc.
    
    Required Parameters:
        - source_system_id: ID in META_SOURCE_SYSTEM
        - source_table: Tabellenname auf Source (ohne Schema)
        - target_database: Teradata Ziel-Datenbank
        - target_table: Teradata Zieltabelle
    
    Optional Parameters:
        - tpt_script_path: Pfad zu existierendem TPT Script
        - tpt_generate: true = TPT Script generieren (default: false)
        - tpt_operator_type: UPDATE, STREAM, LOAD (default: UPDATE)
        - tpt_max_sessions: Max Sessions (default: 4)
        - tpt_min_sessions: Min Sessions (default: 1)
        - use_staging: Staging Tabelle nutzen (default: true)
        - staging_suffix: Suffix für Staging (default: _LOAD)
        - tpt_log_dir: Verzeichnis für TPT Logs
        - tpt_tdpid: Teradata System ID (default aus config)
        - tpt_target_user_wallet: Wallet Key für TD User
        - tpt_target_pwd_wallet: Wallet Key für TD Password
    """
    logger.info("=" * 60)
    logger.info("TPT Executor: run_tpt_load")
    logger.info("=" * 60)
    
    start_time = datetime.now()
    
    # Validate required parameters
    required = ['source_system_id', 'source_table', 'target_database', 'target_table']
    for param in required:
        if param not in parameters:
            raise ValueError(f"Missing required parameter: {param}")
    
    # Get Source System Info
    source_system = _get_source_system(conn, parameters['source_system_id'])
    logger.info(f"Source System: {source_system.source_system_name} ({source_system.source_type})")
    
    # Determine TPT script path
    tpt_script_path = parameters.get('tpt_script_path')
    tpt_generate = parameters.get('tpt_generate', False)
    
    if tpt_script_path and Path(tpt_script_path).exists():
        logger.info(f"Using existing TPT script: {tpt_script_path}")
    elif tpt_generate:
        # Generate TPT script
        logger.info("Generating TPT script...")
        tpt_script_path = _generate_tpt_script(conn, source_system, parameters)
        logger.info(f"Generated TPT script: {tpt_script_path}")
    else:
        raise ValueError(
            "Either tpt_script_path must exist or tpt_generate must be true"
        )
    
    # HINWEIS: Target-Tabelle und Staging-Tabelle werden in separaten Job-Steps
    # angelegt (DDL_DROP, DDL_CREATE). Hier nur tbuild ausführen.
    
    # Execute TPT
    logger.info(f"Executing tbuild: {tpt_script_path}")
    result = _run_tbuild(tpt_script_path, parameters.get('tpt_log_dir'))
    
    # Calculate duration
    result.duration_seconds = (datetime.now() - start_time).total_seconds()
    
    # Parse TPT output for row counts
    if result.stdout:
        result.rows_loaded = _parse_rows_loaded(result.stdout)
        result.rows_rejected = _parse_rows_rejected(result.stdout)
    
    logger.info(f"TPT Result: rc={result.return_code}, rows_loaded={result.rows_loaded}, "
                f"rows_rejected={result.rows_rejected}, duration={result.duration_seconds:.2f}s")
    
    # Build metrics dict
    # staging_table aus Parametern ableiten (wird in separatem DDL-Step angelegt)
    staging_table = None
    if parameters.get('use_staging', True):
        target_db = parameters['target_database']
        target_table = parameters['target_table']
        suffix = parameters.get('staging_suffix', '_LOAD')
        staging_table = f"{target_db}.{target_table}{suffix}"
    
    metrics = {
        'rows_inserted': result.rows_loaded,
        'rows_rejected': result.rows_rejected,
        'tpt_return_code': result.return_code,
        'tpt_log_path': result.tpt_log_path,
        'duration_seconds': result.duration_seconds,
        'staging_table': staging_table,
        'tpt_command': result.tpt_command,
        'tpt_script_path': result.tpt_script_path
    }
    
    if not result.success:
        # Error message mit TPT-Kommando für manuelles Debugging
        error_parts = []
        if result.tpt_command:
            error_parts.append(f"TPT-Kommando: {result.tpt_command}")
        if result.tpt_script_path:
            error_parts.append(f"Script: {result.tpt_script_path}")
        if result.error_message:
            error_parts.append(f"Fehler: {result.error_message}")
        elif result.stderr:
            error_parts.append(f"Fehler: {result.stderr[:500]}")
        
        metrics['error_message'] = "\n".join(error_parts) if error_parts else "Unbekannter Fehler"
    
    return (result.success, metrics)


# =============================================================================
# Helper Functions
# =============================================================================

def _get_source_system(
    conn: 'teradatasql.TeradataConnection',
    source_system_id: int
) -> SourceSystemInfo:
    """Lädt Source System Info aus META_SOURCE_SYSTEM."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            SOURCE_SYSTEM_ID,
            SOURCE_SYSTEM_NAME,
            SOURCE_SYSTEM_CODE,
            SOURCE_TYPE,
            ODBC_DSN_NAME,
            DEFAULT_SCHEMA,
            CREDENTIAL_USER_WALLET,
            CREDENTIAL_PASSWORD_WALLET
        FROM MDP01_META.META_SOURCE_SYSTEM
        WHERE SOURCE_SYSTEM_ID = ?
          AND IS_ACTIVE = 'Y'
    """, (source_system_id,))
    
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Source System not found or inactive: {source_system_id}")
    
    return SourceSystemInfo(
        source_system_id=row[0],
        source_system_name=row[1],
        source_system_code=row[2],
        source_type=row[3],
        odbc_dsn_name=row[4],
        default_schema=row[5],
        credential_user_wallet=row[6],
        credential_password_wallet=row[7]
    )


def _ensure_target_table_exists(
    conn: 'teradatasql.TeradataConnection',
    parameters: Dict[str, Any]
) -> None:
    """Erstellt die Zieltabelle falls sie nicht existiert."""
    target_db = parameters['target_database']
    target_table = parameters['target_table']
    columns = parameters.get('columns', [])
    
    if not columns:
        raise ValueError("No columns defined in parameters - cannot create target table")
    
    # Check if table exists
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM DBC.TablesV
        WHERE DatabaseName = ?
          AND TableName = ?
          AND TableKind = 'T'
    """, (target_db, target_table))
    
    if cursor.fetchone():
        logger.info(f"Target table {target_db}.{target_table} already exists")
        return
    
    # Generate CREATE TABLE DDL
    logger.info(f"Creating target table: {target_db}.{target_table}")
    
    col_defs = []
    for col in columns:
        # Neues Format: target_name/source_name, oder Fallback auf name
        col_name = col.get('target_name') or col.get('name')
        td_type = col.get('td_type', 'VARCHAR(255)')
        nullable = col.get('nullable', True)
        
        col_def = f"    {col_name} {td_type}"
        if not nullable:
            col_def += " NOT NULL"
        col_defs.append(col_def)
    
    # Add ETL audit columns
    col_defs.append("    ETL_LOAD_ID BIGINT")
    col_defs.append("    ETL_LOAD_TIMESTAMP TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6)")
    
    # Primary Index auf erste Spalte
    first_col = columns[0].get('target_name') or columns[0].get('name')
    
    ddl = f"""
CREATE MULTISET TABLE {target_db}.{target_table}, NO FALLBACK
(
{','.join(chr(10) + c for c in col_defs)}
)
PRIMARY INDEX ({first_col})
"""
    
    logger.debug(f"DDL:\n{ddl}")
    
    try:
        # DDL ist vollqualifiziert (database.table) - kein DATABASE Statement nötig
        cursor.execute(ddl)
        conn.commit()
        logger.info(f"Created target table {target_db}.{target_table} with {len(columns)} columns")
    except Exception as e:
        logger.error(f"Failed to create target table: {e}")
        raise


def _create_staging_table(
    conn: 'teradatasql.TeradataConnection',
    parameters: Dict[str, Any]
) -> str:
    """Erstellt Staging Tabelle (LOAD Tabelle) basierend auf Target-Struktur."""
    target_db = parameters['target_database']
    target_table = parameters['target_table']
    suffix = parameters.get('staging_suffix', '_LOAD')
    columns = parameters.get('columns', [])
    
    staging_table = f"{target_db}.{target_table}{suffix}"
    
    cursor = conn.cursor()
    
    # Drop if exists
    try:
        cursor.execute(f"DROP TABLE {staging_table}")
        conn.commit()
        logger.debug(f"Dropped existing staging table: {staging_table}")
    except Exception:
        pass  # Table doesn't exist
    
    # Explizites DDL statt CREATE AS (vermeidet DBC Default-Database Problem)
    if columns:
        col_defs = []
        for col in columns:
            # Neues Format: target_name/source_name, oder Fallback auf name
            col_name = col.get('target_name') or col.get('name')
            td_type = col.get('td_type', 'VARCHAR(255)')
            col_defs.append(f"    {col_name} {td_type}")
        
        # ETL Audit Columns
        col_defs.append("    ETL_LOAD_ID BIGINT")
        col_defs.append("    ETL_LOAD_TIMESTAMP TIMESTAMP(6)")
        
        # Primary Index auf erste Spalte
        first_col = columns[0].get('target_name') or columns[0].get('name')
        
        ddl = f"""CREATE MULTISET TABLE {staging_table}, NO FALLBACK
(
{','.join(chr(10) + c for c in col_defs)}
)
PRIMARY INDEX ({first_col})"""
        
        logger.debug(f"Staging DDL:\n{ddl}")
        cursor.execute(ddl)
    else:
        # Fallback: Copy from target (aber mit expliziter Database)
        cursor.execute(f"DATABASE {target_db}")
        conn.commit()
        cursor.execute(f"""
            CREATE TABLE {staging_table} AS {target_db}.{target_table} WITH NO DATA
        """)
    
    conn.commit()
    logger.info(f"Created staging table: {staging_table}")
    
    return staging_table


def _run_tbuild(
    tpt_script_path: str,
    log_dir: Optional[str] = None
) -> TPTResult:
    """Führt tbuild aus und gibt Result zurück."""
    # Default Log-Verzeichnis verwenden wenn keines angegeben
    if not log_dir:
        log_dir = DEFAULT_TPT_LOG_DIR
    
    # Log-Verzeichnis erstellen falls nicht vorhanden
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger.info(f"TPT logs will be written to: {log_dir}")
    
    cmd = ["tbuild", "-f", tpt_script_path, "-L", log_dir]
    
    cmd_str = ' '.join(cmd)
    logger.debug(f"Running command: {cmd_str}")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(timeout=7200)  # 2h timeout
        
        return TPTResult(
            success=(process.returncode == 0),
            return_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            tpt_log_path=log_dir,
            error_message=stderr if process.returncode != 0 else None,
            tpt_command=cmd_str,
            tpt_script_path=tpt_script_path
        )
    
    except subprocess.TimeoutExpired:
        process.kill()
        return TPTResult(
            success=False,
            return_code=-1,
            error_message="TPT execution timed out after 2 hours",
            tpt_command=cmd_str,
            tpt_script_path=tpt_script_path
        )
    except Exception as e:
        return TPTResult(
            success=False,
            return_code=-1,
            error_message=str(e),
            tpt_command=cmd_str,
            tpt_script_path=tpt_script_path
        )


def _parse_rows_loaded(stdout: str) -> int:
    """Extrahiert Anzahl geladener Zeilen aus TPT Output."""
    # Typical TPT output: "Total Rows Sent To RDBMS:      12345"
    patterns = [
        r'Total Rows Sent To RDBMS:\s*(\d+)',
        r'Rows Inserted:\s*(\d+)',
        r'(\d+) rows? (sent|loaded|inserted)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, stdout, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    return 0


def _parse_rows_rejected(stdout: str) -> int:
    """Extrahiert Anzahl abgelehnter Zeilen aus TPT Output."""
    patterns = [
        r'Total Rows Rejected:\s*(\d+)',
        r'Rows Rejected:\s*(\d+)',
        r'(\d+) rows? rejected',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, stdout, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    return 0


def _generate_tpt_script(
    conn: 'teradatasql.TeradataConnection',
    source_system: SourceSystemInfo,
    parameters: Dict[str, Any]
) -> str:
    """
    Generiert TPT Script basierend auf Parametern und Spalten-Metadaten.
    
    Holt Spalten aus META_COLUMN für die Zieltabelle und generiert
    entsprechendes TPT Script.
    """
    from .tpt_generator import TPTGenerator
    
    generator = TPTGenerator(conn)
    return generator.generate(source_system, parameters)


# =============================================================================
# Cleanup Functions
# =============================================================================

def _save_cleanup_sql(
    statements: list,
    table_name: str,
    job_id: Optional[int] = None
) -> Path:
    """
    Speichert CLEANUP-SQL-Statements in eine Datei (gemäß PRINCIPLES.md).
    
    Args:
        statements: Liste von SQL-Statements
        table_name: Name der Tabelle
        job_id: Optional ETL Job ID
    
    Returns:
        Pfad zur erstellten SQL-Datei
    """
    output_dir = PATHS.get("ddl_output", Path("/tmp"))
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_prefix = f"job{job_id}_" if job_id else ""
    filename = f"{timestamp}_{job_prefix}{table_name}_CLEANUP.sql"
    filepath = output_dir / filename
    
    header = f"""-- =============================================================================
-- CLEANUP: {table_name}
-- Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
-- Job ID: {job_id or 'N/A'}
-- =============================================================================
-- Diese Befehle bereinigen TPT-Artefakte vor einem neuen Load.
-- Fehler bei nicht existierenden Objekten sind OK und werden ignoriert.
-- =============================================================================

"""
    
    content = header + "\n".join(statements)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info(f"CLEANUP SQL gespeichert: {filepath}")
    return filepath


def cleanup_tpt(
    conn: 'teradatasql.TeradataConnection',
    parameters: Dict[str, Any],
    context: Dict[str, Any] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Bereinigt TPT-Artefakte vor einem neuen Load.
    
    Workflow (gemäß PRINCIPLES.md):
        1. SQL-Statements GENERIEREN
        2. SQL-Datei SPEICHERN (ddl/generated/)
        3. SQL-Statements AUSFÜHREN
        4. Ergebnisse ZURÜCKGEBEN
    
    Diese Funktion wird vom Orchestrator aufgerufen wenn:
        STEP_CATEGORY    = 'CLEANUP'
        PYTHON_MODULE    = 'tpt_executor'
        PYTHON_FUNCTION  = 'cleanup_tpt'
    
    WICHTIG: CLEANUP ist NON-CRITICAL!
    Diese Funktion gibt IMMER success=True zurück, auch bei Fehlern.
    Fehler werden als Warnings geloggt aber blockieren den Job nicht.
    
    Aktionen:
        1. Drop TPT-Artefakt-Tabellen (_ET, _UV, _WT, _LG)
        2. Release MLOAD falls blockiert
        3. Löscht Checkpoint-Dateien
    
    Args:
        conn: Teradata Connection
        parameters: Dict mit target_database, target_table
        context: Optional zusätzlicher Kontext (enthält job_id)
    
    Returns:
        Tuple (success: bool, result: Dict) - success ist immer True
    """
    try:
        target_db = parameters.get('target_database')
        target_table = parameters.get('target_table')
        job_id = context.get('job_id') if context else None
        
        # Parameter validieren - bei Fehlen: Warnung, aber weiter
        if not target_db or not target_table:
            msg = f"target_database oder target_table nicht in parameters: db={target_db}, table={target_table}"
            logger.warning(f"Cleanup skip: {msg}")
            return (True, {
                "warnings": [msg],
                "message": "Cleanup übersprungen - fehlende Parameter"
            })
        
        # =====================================================================
        # SCHRITT 1: SQL-Statements GENERIEREN
        # =====================================================================
        sql_statements = []
        
        # TPT-Artefakt-Tabellen
        artifact_suffixes = ['_ET', '_UV', '_WT', '_LG']
        for suffix in artifact_suffixes:
            sql_statements.append(f"DROP TABLE {target_db}.{target_table}{suffix};")
        
        # MLOAD Release
        sql_statements.append(f"RELEASE MLOAD {target_db}.{target_table};")
        
        # =====================================================================
        # SCHRITT 2: SQL-Datei SPEICHERN
        # =====================================================================
        try:
            sql_file = _save_cleanup_sql(sql_statements, target_table, job_id)
        except Exception as e:
            logger.error(f"Fehler beim Speichern der CLEANUP-SQL: {e}")
            sql_file = None
        
        # =====================================================================
        # SCHRITT 3: SQL-Statements AUSFÜHREN
        # =====================================================================
        cursor = conn.cursor()
        dropped_tables = []
        warnings = []
        
        # Drop TPT-Artefakt-Tabellen
        for suffix in artifact_suffixes:
            artifact_table = f"{target_db}.{target_table}{suffix}"
            try:
                cursor.execute(f"DROP TABLE {artifact_table}")
                dropped_tables.append(artifact_table)
                logger.info(f"Dropped artifact table: {artifact_table}")
            except Exception as e:
                error_str = str(e)
                if '3807' in error_str or '3802' in error_str:
                    logger.debug(f"Artifact table/database not found (OK): {artifact_table}")
                else:
                    warnings.append(f"{artifact_table}: {error_str}")
                    logger.warning(f"Error dropping {artifact_table}: {e}")
        
        # Release MLOAD
        try:
            cursor.execute(f"RELEASE MLOAD {target_db}.{target_table}")
            logger.info(f"Released MLOAD on {target_db}.{target_table}")
        except Exception as e:
            error_str = str(e)
            if any(code in error_str for code in ['2652', '2574', '3802', '3807']):
                logger.debug(f"No MLOAD lock to release (OK)")
            else:
                warnings.append(f"RELEASE MLOAD: {error_str}")
                logger.warning(f"Error releasing MLOAD: {e}")
        
        # Checkpoint-Dateien löschen
        checkpoint_dir = Path(DEFAULT_TPT_LOG_DIR)
        checkpoint_pattern = f"*{target_table}*.chk"
        deleted_checkpoints = []
        
        if checkpoint_dir.exists():
            for chk_file in checkpoint_dir.glob(checkpoint_pattern):
                try:
                    chk_file.unlink()
                    deleted_checkpoints.append(str(chk_file))
                    logger.info(f"Deleted checkpoint: {chk_file}")
                except Exception as e:
                    warnings.append(f"Checkpoint {chk_file}: {str(e)}")
        
        # =====================================================================
        # SCHRITT 4: Ergebnis ZURÜCKGEBEN
        # =====================================================================
        if warnings:
            logger.warning(f"Cleanup completed with warnings: {warnings}")
        
        result = {
            "sql_file": str(sql_file) if sql_file else None,
            "dropped_tables": dropped_tables,
            "deleted_checkpoints": deleted_checkpoints,
            "warnings": warnings if warnings else None,
            "message": f"Cleanup completed: {len(dropped_tables)} tables dropped, {len(deleted_checkpoints)} checkpoints deleted"
        }
        
        return (True, result)  # CLEANUP ist non-critical → immer success
    
    except Exception as e:
        logger.error(f"Unexpected error in cleanup_tpt: {e}")
        return (True, {
            "warnings": [f"Unexpected error: {str(e)}"],
            "message": "Cleanup abgebrochen - unerwarteter Fehler (non-critical)"
        })


# =============================================================================
# Alias for Orchestrator
# =============================================================================

# run_tpt ist ein Alias für run_tpt_load (für META_ETL_JOB_STEP Kompatibilität)
run_tpt = run_tpt_load
