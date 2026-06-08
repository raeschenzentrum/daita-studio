"""
ETL Service Layer
=================

Business Logic für ETL Orchestrator Dashboard.
Wrapper für Orchestrator + DB Queries.

Autor: DWH MVP Team
Datum: 2026-01-19
"""
import sys
import yaml
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

# Teradata SQL Driver
try:
    import teradatasql
except ImportError:
    raise ImportError("teradatasql not installed")

# Import Orchestrator (lokal aus services/)
try:
    from .orchestrator import MetadataETLOrchestrator
except ImportError:
    # Fallback für Originalstruktur
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "daita-lakehouse-db" / "tools" / "etl"))
    from orchestrator import MetadataETLOrchestrator

from ..models.etl_models import (
    ETLJob, ETLJobWithDetails, ETLJobStep, ETLJobRun, 
    ETLJobRunWithSteps, ETLJobStepRun, ETLJobStepRunWithDetails,
    JobPerformanceStats, DashboardStats
)

logger = logging.getLogger(__name__)


# =============================================================================
# ETL Service
# =============================================================================

class ETLService:
    """Service für ETL Orchestrator Operations"""
    
    def __init__(self, config_path: str = None):
        """
        Initialisiert Service mit Datenbankverbindung.
        
        Args:
            config_path: Pfad zu database.yml (default: cfg/database.yml im Installationsverzeichnis)
        """
        # Pfade ermitteln
        install_dir = Path(__file__).parent.parent.parent.parent
        cfg_dir = install_dir / "cfg"
        
        database_yml = cfg_dir / "database.yml"
        config_yml = cfg_dir / "config.yml"
        
        # Fallback auf alte Struktur
        if not database_yml.exists():
            database_yml = install_dir.parent / "daita-lakehouse-db" / "config" / "database.yml"
        
        # database.yml laden
        with open(database_yml, 'r') as f:
            db_config = yaml.safe_load(f)
        
        # config.yml laden (optional, für Pfade)
        paths_config = {}
        if config_yml.exists():
            with open(config_yml, 'r') as f:
                paths_config = yaml.safe_load(f) or {}
        
        # Kombinierte Config für Orchestrator zusammenbauen
        teradata_cfg = db_config.get('teradata', {})
        paths = paths_config.get('paths', {})
        
        config = {
            'teradata': teradata_cfg,
            'source_systems': db_config.get('source_systems', {}),
            'metadata': db_config.get('metadata', {}),
            'etl': {
                'transaction_mode': teradata_cfg.get('transaction_mode', 'ANSI'),
                'autocommit': teradata_cfg.get('autocommit', False),
                'batch_size': teradata_cfg.get('batch_size', 10000),
                'sql_templates_base_dir': str(install_dir / paths.get('sql_templates', 'sql/templates')),
                'log_dir': str(install_dir / paths.get('log', 'log')),
                'verbose': paths_config.get('logging', {}).get('level', 'INFO') == 'DEBUG',
            }
        }
        
        self.config = config
        self.db_config = teradata_cfg
        self.etl_config = config['etl']
        self.orchestrator = MetadataETLOrchestrator(config)  # Pass config dict, not path
    
    def _get_connection(self) -> teradatasql.TeradataConnection:
        """Erstellt neue DB Connection mit Session Timezone"""
        # Nur Connection-Parameter, nicht autocommit/transaction_mode/batch_size
        conn_params = {
            'host': self.db_config.get('host'),
            'user': self.db_config.get('user'),
            'password': self.db_config.get('password'),
            'connect_timeout': self.db_config.get('connect_timeout', 10000),
        }
        conn = teradatasql.connect(**conn_params)
        
        # Session-Zeitzone auf Europe/Berlin setzen (CET/CEST)
        try:
            cursor = conn.cursor()
            cursor.execute("SET TIME ZONE 'Europe/Berlin'")
        except Exception:
            pass  # Fallback: behalte Server-Zeitzone
        
        return conn
    
    # =========================================================================
    # Job Operations
    # =========================================================================
    
    def get_all_jobs(self, active_only: bool = False) -> List[ETLJobWithDetails]:
        """
        Gibt alle ETL Jobs zurück mit Details.
        
        Args:
            active_only: Nur aktive Jobs (is_active='Y')
        
        Returns:
            Liste von ETLJobWithDetails
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT 
            j.etl_job_id,
            j.job_name,
            j.job_type,
            j.source_table_id,
            j.target_table_id,
            j.is_active,
            j.create_timestamp,
            j.last_alter_timestamp,
            st.table_name as source_table_name,
            tt.table_name as target_table_name,
            COALESCE(sd.layer_id, j.source_layer_id) as source_layer_id,
            COALESCE(td.layer_id, j.target_layer_id) as target_layer_id,
            (SELECT COUNT(*) FROM MDP01_META.META_ETL_JOB_STEP s 
             WHERE s.etl_job_id = j.etl_job_id AND s.is_active = 'Y') as step_count,
            lr.status as last_run_status,
            lr.start_time as last_run_time
        FROM MDP01_META.META_ETL_JOB j
        LEFT JOIN MDP01_META.META_TABLE st ON j.source_table_id = st.table_id
        LEFT JOIN MDP01_META.META_TABLE tt ON j.target_table_id = tt.table_id
        LEFT JOIN MDP01_META.META_DATABASE sd ON st.database_id = sd.database_id
        LEFT JOIN MDP01_META.META_DATABASE td ON tt.database_id = td.database_id
        LEFT JOIN (
            SELECT etl_job_id, status, start_time
            FROM (
                SELECT etl_job_id, status, start_time,
                       ROW_NUMBER() OVER (PARTITION BY etl_job_id ORDER BY start_time DESC) as rn
                FROM MDP01_META.META_ETL_JOB_RUN
            ) tmp
            WHERE rn = 1
        ) lr ON j.etl_job_id = lr.etl_job_id
        """
        
        if active_only:
            query += " WHERE j.is_active = 'Y'"
        
        query += " ORDER BY j.etl_job_id"
        
        cursor.execute(query)
        
        jobs = []
        for row in cursor.fetchall():
            jobs.append(ETLJobWithDetails(
                etl_job_id=row[0],
                job_name=row[1],
                job_type=row[2],
                source_table_id=row[3],
                target_table_id=row[4],
                is_active=row[5],
                retry_count=3,  # Default value
                timeout_seconds=3600,  # Default value
                create_timestamp=row[6],
                last_alter_timestamp=row[7],
                source_table_name=row[8],
                target_table_name=row[9],
                source_layer_id=row[10],
                target_layer_id=row[11],
                step_count=row[12],
                last_run_status=row[13],
                last_run_time=row[14]
            ))
        
        conn.close()
        return jobs
    
    def get_job_by_id(self, job_id: int) -> Optional[ETLJobWithDetails]:
        """Gibt einen spezifischen Job zurück – inkl. Details (Tabellennamen, Layer, Step-Count)"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                j.etl_job_id,
                j.job_name,
                j.job_type,
                j.source_table_id,
                j.target_table_id,
                j.is_active,
                j.create_timestamp,
                j.last_alter_timestamp,
                st.table_name  AS source_table_name,
                tt.table_name  AS target_table_name,
                COALESCE(sd.layer_id, j.source_layer_id) AS source_layer_id,
                COALESCE(td.layer_id, j.target_layer_id) AS target_layer_id,
                (SELECT COUNT(*) FROM MDP01_META.META_ETL_JOB_STEP s
                 WHERE s.etl_job_id = j.etl_job_id AND s.is_active = 'Y') AS step_count,
                lr.status     AS last_run_status,
                lr.start_time AS last_run_time
            FROM MDP01_META.META_ETL_JOB j
            LEFT JOIN MDP01_META.META_TABLE    st ON j.source_table_id = st.table_id
            LEFT JOIN MDP01_META.META_TABLE    tt ON j.target_table_id = tt.table_id
            LEFT JOIN MDP01_META.META_DATABASE sd ON st.database_id   = sd.database_id
            LEFT JOIN MDP01_META.META_DATABASE td ON tt.database_id   = td.database_id
            LEFT JOIN (
                SELECT etl_job_id, status, start_time
                FROM (
                    SELECT etl_job_id, status, start_time,
                           ROW_NUMBER() OVER (PARTITION BY etl_job_id ORDER BY start_time DESC) AS rn
                    FROM MDP01_META.META_ETL_JOB_RUN
                ) tmp WHERE rn = 1
            ) lr ON j.etl_job_id = lr.etl_job_id
            WHERE j.etl_job_id = ?
        """, (job_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return ETLJobWithDetails(
                etl_job_id=row[0],         job_name=row[1],          job_type=row[2],
                source_table_id=row[3],    target_table_id=row[4],   is_active=row[5],
                retry_count=3,             timeout_seconds=3600,
                create_timestamp=row[6],   last_alter_timestamp=row[7],
                source_table_name=row[8],  target_table_name=row[9],
                source_layer_id=row[10],   target_layer_id=row[11],
                step_count=row[12],        last_run_status=row[13],  last_run_time=row[14],
            )
        return None
    
    def get_job_steps(self, job_id: int) -> List[ETLJobStep]:
        """Gibt alle Steps für einen Job zurück"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT etl_job_step_id, etl_job_id, step_name, step_order, step_category,
                   sql_template_path, sql_inline, python_module, python_function,
                   parameters, condition_sql, skip_on_empty, is_critical,
                   rollback_on_error, is_active, create_timestamp, last_alter_timestamp
            FROM MDP01_META.META_ETL_JOB_STEP
            WHERE etl_job_id = ?
            ORDER BY step_order
        """, (job_id,))
        
        steps = []
        for row in cursor.fetchall():
            steps.append(ETLJobStep(
                etl_job_step_id=row[0], etl_job_id=row[1], step_name=row[2],
                step_order=row[3], step_category=row[4], sql_template_path=row[5],
                sql_inline=row[6], python_module=row[7], python_function=row[8],
                parameters=row[9], condition_sql=row[10], skip_on_empty=row[11],
                is_critical=row[12], rollback_on_error=row[13], is_active=row[14],
                create_timestamp=row[15], last_alter_timestamp=row[16]
            ))
        
        conn.close()
        return steps
    
    def update_step_parameters(self, step_id: int, parameters_json: str) -> None:
        """Aktualisiert die Parameter eines ETL Job Steps"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE MDP01_META.META_ETL_JOB_STEP
            SET parameters = ?,
                last_alter_timestamp = CURRENT_TIMESTAMP
            WHERE etl_job_step_id = ?
        """, (parameters_json, step_id))
        
        conn.commit()
        conn.close()
        logger.info(f"Updated parameters for step {step_id}")
    
    # =========================================================================
    # Metadata Explorer: Layers, Databases, Tables
    # =========================================================================
    
    def get_all_layers(self) -> list:
        """Gibt alle Layer mit Datenbank-Anzahl zurück"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT l.layer_id, l.layer_name, l.layer_code, l.layer_sequence,
                   l.layer_beschreibung, l.modellierungsansatz,
                   COUNT(d.database_id) as database_count
            FROM MDP01_META.META_LAYER l
            LEFT JOIN MDP01_META.META_DATABASE d ON l.layer_id = d.layer_id
            GROUP BY l.layer_id, l.layer_name, l.layer_code, l.layer_sequence,
                     l.layer_beschreibung, l.modellierungsansatz
            ORDER BY l.layer_sequence
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            "layer_id": r[0],
            "layer_name": r[1],
            "layer_code": r[2],
            "layer_sequence": r[3],
            "description": r[4],
            "modeling_approach": r[5],
            "database_count": r[6]
        } for r in rows]
    
    def get_databases_by_layer(self, layer_id: int = None) -> list:
        """Gibt alle Databases zurück, optional gefiltert nach Layer"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        sql = """
            SELECT d.database_id, d.database_name, d.layer_id, 
                   l.layer_code, l.layer_name, l.layer_sequence,
                   d.comment_string,
                   COUNT(t.table_id) as table_count
            FROM MDP01_META.META_DATABASE d
            JOIN MDP01_META.META_LAYER l ON d.layer_id = l.layer_id
            LEFT JOIN MDP01_META.META_TABLE t ON d.database_id = t.database_id
        """
        
        params = []
        if layer_id:
            sql += " WHERE d.layer_id = ?"
            params.append(layer_id)
        
        sql += """
            GROUP BY d.database_id, d.database_name, d.layer_id,
                     l.layer_code, l.layer_name, l.layer_sequence, d.comment_string
            ORDER BY l.layer_sequence, d.database_name
        """
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            "database_id": r[0],
            "database_name": r[1],
            "layer_id": r[2],
            "layer_code": r[3],
            "layer_name": r[4],
            "comment": r[6],
            "table_count": r[7]
        } for r in rows]
    
    def get_tables_by_database(self, database_id: int) -> list:
        """Gibt alle Tabellen einer Database mit Spaltenanzahl zurück"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT t.table_id, t.table_name, t.is_historized, t.historization_type,
                   t.comment_string,
                   COUNT(c.column_id) as column_count
            FROM MDP01_META.META_TABLE t
            LEFT JOIN MDP01_META.META_COLUMN c ON t.table_id = c.table_id
            WHERE t.database_id = ?
            GROUP BY t.table_id, t.table_name, t.is_historized, 
                     t.historization_type, t.comment_string
            ORDER BY t.table_name
        """, (database_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            "table_id": r[0],
            "table_name": r[1],
            "is_historized": r[2].strip() if r[2] else 'N',
            "historization_type": r[3],
            "comment": r[4],
            "column_count": r[5]
        } for r in rows]
    
    def get_table_columns(self, table_id: int) -> list:
        """Gibt alle Spalten einer Tabelle zurück"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT c.column_id, c.column_name, c.column_position,
                   c.column_type, c.column_length, c.nullable,
                   c.is_business_key, c.is_technical_key,
                   c.is_audit_column, c.is_scd_column, c.scd_type,
                   c.comment_string
            FROM MDP01_META.META_COLUMN c
            WHERE c.table_id = ?
            ORDER BY c.column_position
        """, (table_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            "column_id": r[0],
            "column_name": r[1],
            "position": r[2],
            "data_type": r[3].strip() if r[3] else None,
            "length": r[4],
            "nullable": r[5].strip() == 'Y' if r[5] else True,
            "is_business_key": r[6].strip() == 'Y' if r[6] else False,
            "is_technical_key": r[7].strip() == 'Y' if r[7] else False,
            "is_audit_column": r[8].strip() == 'Y' if r[8] else False,
            "is_scd_column": r[9].strip() == 'Y' if r[9] else False,
            "scd_type": r[10],
            "comment": r[11]
        } for r in rows]
    
    def delete_table(self, table_id: int) -> dict:
        """Löscht eine Tabelle (META_TABLE + META_COLUMN) aus den Metadaten"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Tabellenname ermitteln (für Rückgabe)
        cursor.execute(
            "SELECT table_name FROM MDP01_META.META_TABLE WHERE table_id = ?",
            (table_id,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {"error": f"Tabelle {table_id} nicht gefunden"}

        table_name = row[0]

        # Spalten zuerst löschen (FK-Abhängigkeit)
        cursor.execute(
            "DELETE FROM MDP01_META.META_COLUMN WHERE table_id = ?",
            (table_id,)
        )
        columns_deleted = cursor.rowcount

        # Dann die Tabelle selbst
        cursor.execute(
            "DELETE FROM MDP01_META.META_TABLE WHERE table_id = ?",
            (table_id,)
        )
        conn.commit()
        conn.close()

        logger.info(f"Table {table_name} (id={table_id}) deleted from metadata ({columns_deleted} columns removed)")
        return {
            "table_id": table_id,
            "table_name": table_name,
            "columns_deleted": columns_deleted
        }

    def get_dbc_tables(self, database_name: str) -> list:
        """Gibt alle Tabellen aus dbc.tablesV für eine Database zurück (zum Importieren)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT tablename, tablekind, commentstring,
                   createtimestamp, lastaltertimestamp
            FROM dbc.tablesV 
            WHERE databasename = ? 
              AND tablekind IN ('T', 'O', 'V')
            ORDER BY tablename
        """, (database_name,))
        
        rows = cursor.fetchall()
        conn.close()
        
        def _kind_label(k):
            return 'Table' if k == 'T' else ('View' if k == 'V' else 'Object')

        return [{
            "table_name": r[0],
            "table_kind": _kind_label(r[1]),
            "comment": r[2],
            "created": r[3].isoformat() if r[3] else None,
            "last_altered": r[4].isoformat() if r[4] else None
        } for r in rows]
    
    def import_table_from_dbc(self, database_id: int, table_name: str) -> dict:
        """Importiert eine Tabelle mit Spalten aus dbc in META_TABLE/META_COLUMN"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Hole Database-Name
        cursor.execute("SELECT database_name FROM MDP01_META.META_DATABASE WHERE database_id = ?", (database_id,))
        db_row = cursor.fetchone()
        if not db_row:
            conn.close()
            return {"error": f"Database {database_id} nicht gefunden"}
        
        database_name = db_row[0]
        
        # Prüfe ob Tabelle schon existiert
        cursor.execute("""
            SELECT table_id FROM MDP01_META.META_TABLE 
            WHERE database_id = ? AND UPPER(table_name) = UPPER(?)
        """, (database_id, table_name))
        if cursor.fetchone():
            conn.close()
            return {"error": f"Tabelle {table_name} existiert bereits in META_TABLE"}
        
        # Hole Tabellen-Info aus dbc
        cursor.execute("""
            SELECT tablename, commentstring FROM dbc.tablesV 
            WHERE databasename = ? AND UPPER(tablename) = UPPER(?)
        """, (database_name, table_name))
        tbl_row = cursor.fetchone()
        if not tbl_row:
            conn.close()
            return {"error": f"Tabelle {table_name} nicht in {database_name} gefunden"}
        
        actual_table_name = tbl_row[0]
        table_comment = tbl_row[1]
        
        # Nächste table_id
        cursor.execute("SELECT COALESCE(MAX(table_id), 0) + 1 FROM MDP01_META.META_TABLE")
        next_table_id = cursor.fetchone()[0]
        
        # Tabelle einfügen
        cursor.execute("""
            INSERT INTO MDP01_META.META_TABLE (
                table_id, database_id, table_name, is_historized,
                comment_string, ersterfassungsdatum, aenderungsdatum
            ) VALUES (?, ?, ?, 'N', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (next_table_id, database_id, actual_table_name, table_comment))
        
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
        conn.close()
        
        return {
            "success": True,
            "table_id": next_table_id,
            "table_name": actual_table_name,
            "columns_imported": inserted_columns
        }

    def get_table_with_columns(self, table_id: int) -> dict:
        """Gibt eine Tabelle mit ihren Spalten zurück"""
        if not table_id:
            return None
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Tabelle laden
        cursor.execute("""
            SELECT t.table_id, t.table_name, d.database_name, 
                   t.comment_string, t.is_historized, t.historization_type
            FROM MDP01_META.META_TABLE t
            LEFT JOIN MDP01_META.META_DATABASE d ON t.database_id = d.database_id
            WHERE t.table_id = ?
        """, (table_id,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        
        table_info = {
            "table_id": row[0],
            "table_name": row[1],
            "database_name": row[2],
            "full_name": f"{row[2]}.{row[1]}" if row[2] else row[1],
            "comment": row[3],
            "is_historized": row[4],
            "historization_type": row[5],
            "columns": []
        }
        
        # Spalten laden
        cursor.execute("""
            SELECT c.column_id, c.column_name, c.column_position, 
                   c.column_type, c.column_length, c.nullable,
                   c.is_business_key, c.is_technical_key, c.is_audit_column,
                   c.is_scd_column, c.scd_type, c.comment_string
            FROM MDP01_META.META_COLUMN c
            WHERE c.table_id = ?
            ORDER BY c.column_position
        """, (table_id,))
        
        for col in cursor.fetchall():
            table_info["columns"].append({
                "column_id": col[0],
                "column_name": col[1],
                "position": col[2],
                "data_type": col[3],
                "length": col[4],
                "nullable": col[5] == 'Y',
                "is_business_key": col[6] == 'Y',
                "is_technical_key": col[7] == 'Y',
                "is_audit_column": col[8] == 'Y',
                "is_scd_column": col[9] == 'Y',
                "scd_type": col[10],
                "comment": col[11]
            })
        
        conn.close()
        return table_info
    
    def get_job_mapping_info(self, job_id: int) -> dict:
        """Gibt Source/Target Tabellen mit Spalten für einen Job zurück"""
        job = self.get_job_by_id(job_id)
        if not job:
            return None
        
        return {
            "job_id": job.etl_job_id,
            "job_name": job.job_name,
            "source": self.get_table_with_columns(job.source_table_id),
            "target": self.get_table_with_columns(job.target_table_id)
        }
    
    def generate_tpt_preview(self, job_id: int) -> Optional[dict]:
        """
        Generiert TPT Script Preview für einen Job.
        
        Args:
            job_id: ETL Job ID
        
        Returns:
            Dict mit job_id, job_name, tpt_script, message oder None
        """
        # Lade Job und Steps
        job = self.get_job_by_id(job_id)
        if not job:
            return None
        
        steps = self.get_job_steps(job_id)
        
        # Finde TPT_LOAD Step
        tpt_step = None
        for step in steps:
            if step.step_category == 'TPT_LOAD':
                tpt_step = step
                break
        
        if not tpt_step:
            return None
        
        import json
        from .tpt_generator import TPTGenerator
        from dataclasses import dataclass
        
        @dataclass
        class SourceSystemInfo:
            odbc_dsn_name: str
            odbc_user: str
            odbc_password: str
            source_database: str
        
        # Parse Parameters
        try:
            parameters = json.loads(tpt_step.parameters) if isinstance(tpt_step.parameters, str) else tpt_step.parameters
        except:
            parameters = {}
        
        # Hole Source System Info
        conn = self._get_connection()
        cursor = conn.cursor()
        
        source_system_id = parameters.get('source_system_id')
        if not source_system_id:
            conn.close()
            return {
                "job_id": job_id,
                "job_name": job.job_name,
                "tpt_script": "-- ERROR: source_system_id nicht in Parameters",
                "message": "Fehler: source_system_id nicht in Parameters"
            }
        
        cursor.execute("""
            SELECT ODBC_DSN_NAME, CREDENTIAL_USER_WALLET, CREDENTIAL_PASSWORD_WALLET, DEFAULT_DATABASE
            FROM MDP01_META.META_SOURCE_SYSTEM
            WHERE SOURCE_SYSTEM_ID = ?
        """, (source_system_id,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {
                "job_id": job_id,
                "job_name": job.job_name,
                "tpt_script": f"-- ERROR: Source System {source_system_id} nicht gefunden",
                "message": f"Fehler: Source System {source_system_id} nicht gefunden"
            }
        
        source_system = SourceSystemInfo(
            odbc_dsn_name=row[0],
            odbc_user=row[1] or 'tpt_user',
            odbc_password=row[2] or 'tpt_password',
            source_database=row[3] or 'master'
        )
        
        # TPT Generator aufrufen
        try:
            generator = TPTGenerator(conn)
            
            # Generiere Script ohne zu speichern
            columns = generator._get_columns(parameters)
            if not columns:
                return {
                    "job_id": job_id,
                    "job_name": job.job_name,
                    "tpt_script": "-- ERROR: Keine Spalten gefunden",
                    "message": "Fehler: Keine Spalten für Tabelle gefunden"
                }
            
            tpt_job_name = f"load_{parameters.get('target_table', 'unknown')}"
            schema_def = generator._build_schema_definition(columns)
            odbc_operator = generator._build_odbc_operator(source_system, parameters, columns)
            td_operator = generator._build_td_operator(parameters)
            apply_stmt = generator._build_apply_statement(parameters, columns)
            
            script = generator._assemble_script(
                job_name=tpt_job_name,
                schema_def=schema_def,
                odbc_operator=odbc_operator,
                td_operator=td_operator,
                apply_stmt=apply_stmt
            )
            
            conn.close()
            
            return {
                "job_id": job_id,
                "job_name": job.job_name,
                "tpt_script": script,
                "message": f"TPT Script generiert für {len(columns)} Spalten"
            }
            
        except Exception as e:
            conn.close()
            logger.error(f"TPT Preview generation error: {e}")
            return {
                "job_id": job_id,
                "job_name": job.job_name,
                "tpt_script": f"-- ERROR: {str(e)}",
                "message": f"Fehler bei Script-Generierung: {str(e)}"
            }
    
    def get_actual_columns_from_dbc(self, database_name: str, table_name: str) -> list:
        """Liest die echten Spalten aus dbc.columnsV"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
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
        
        conn.close()
        return columns
    
    def compare_table_columns(self, table_id: int) -> dict:
        """Vergleicht META_COLUMN mit dbc.columnsV für eine Tabelle"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Hole Tabellen-Info
        cursor.execute("""
            SELECT t.table_name, d.database_name
            FROM MDP01_META.META_TABLE t
            JOIN MDP01_META.META_DATABASE d ON t.database_id = d.database_id
            WHERE t.table_id = ?
        """, (table_id,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {"error": "Tabelle nicht gefunden"}
        
        table_name, database_name = row[0], row[1]
        conn.close()
        
        # Echte Spalten aus dbc
        actual_columns = self.get_actual_columns_from_dbc(database_name, table_name)
        actual_by_name = {c["column_name"].upper(): c for c in actual_columns}
        
        # Metadaten-Spalten
        table_info = self.get_table_with_columns(table_id)
        meta_columns = table_info.get("columns", []) if table_info else []
        meta_by_name = {c["column_name"].upper(): c for c in meta_columns}
        
        # Diff berechnen
        diff = {
            "table_id": table_id,
            "table_name": table_name,
            "database_name": database_name,
            "added": [],      # In dbc, nicht in META_COLUMN
            "removed": [],    # In META_COLUMN, nicht in dbc
            "changed": [],    # Unterschiedlicher Typ/Länge
            "unchanged": []   # Gleich
        }
        
        # Neue Spalten (in dbc, nicht in meta)
        for name, actual in actual_by_name.items():
            if name not in meta_by_name:
                diff["added"].append({
                    "column_name": actual["column_name"],
                    "position": actual["position"],
                    "column_type": actual["column_type"],
                    "length": actual["length"],
                    "nullable": actual["nullable"]
                })
        
        # Gelöschte Spalten (in meta, nicht in dbc)
        for name, meta in meta_by_name.items():
            if name not in actual_by_name:
                diff["removed"].append({
                    "column_id": meta["column_id"],
                    "column_name": meta["column_name"],
                    "position": meta["position"],
                    "data_type": meta["data_type"]
                })
        
        # Geänderte/Unveränderte Spalten
        for name, meta in meta_by_name.items():
            if name in actual_by_name:
                actual = actual_by_name[name]
                # Vergleiche Typ und Länge
                meta_type = (meta.get("data_type") or "").strip()
                actual_type = (actual.get("column_type") or "").strip()
                
                changes = []
                if meta_type != actual_type:
                    changes.append(f"Typ: {meta_type} → {actual_type}")
                if meta.get("length") != actual.get("length"):
                    changes.append(f"Länge: {meta.get('length')} → {actual.get('length')}")
                if meta.get("position") != actual.get("position"):
                    changes.append(f"Position: {meta.get('position')} → {actual.get('position')}")
                
                if changes:
                    diff["changed"].append({
                        "column_id": meta["column_id"],
                        "column_name": meta["column_name"],
                        "changes": changes,
                        "meta": meta,
                        "actual": actual
                    })
                else:
                    diff["unchanged"].append(meta["column_name"])
        
        diff["summary"] = {
            "total_in_dbc": len(actual_columns),
            "total_in_meta": len(meta_columns),
            "added_count": len(diff["added"]),
            "removed_count": len(diff["removed"]),
            "changed_count": len(diff["changed"]),
            "unchanged_count": len(diff["unchanged"])
        }
        
        return diff
    
    def sync_table_columns(self, table_id: int) -> dict:
        """Synchronisiert META_COLUMN mit dbc.columnsV"""
        diff = self.compare_table_columns(table_id)
        
        if "error" in diff:
            return diff
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        results = {
            "inserted": 0,
            "updated": 0,
            "deleted": 0,
            "errors": []
        }
        
        # Neue Spalten einfügen
        for col in diff["added"]:
            try:
                # Hole nächste column_id
                cursor.execute("SELECT COALESCE(MAX(column_id), 0) + 1 FROM MDP01_META.META_COLUMN")
                next_id = cursor.fetchone()[0]
                
                # Hole datatype_id (oder default)
                cursor.execute("""
                    SELECT datatype_id FROM MDP01_META.META_DATATYPE 
                    WHERE teradata_type = ? 
                    SAMPLE 1
                """, (col["column_type"],))
                dt_row = cursor.fetchone()
                datatype_id = dt_row[0] if dt_row else 1
                
                cursor.execute("""
                    INSERT INTO MDP01_META.META_COLUMN (
                        column_id, table_id, column_name, column_position,
                        datatype_id, column_type, column_length, nullable,
                        ersterfassungsdatum, aenderungsdatum
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (next_id, table_id, col["column_name"], col["position"],
                      datatype_id, col["column_type"], col["length"], 
                      'Y' if col["nullable"] else 'N'))
                results["inserted"] += 1
            except Exception as e:
                results["errors"].append(f"Insert {col['column_name']}: {str(e)}")
        
        # Geänderte Spalten aktualisieren
        for col in diff["changed"]:
            try:
                actual = col["actual"]
                cursor.execute("""
                    UPDATE MDP01_META.META_COLUMN
                    SET column_type = ?,
                        column_length = ?,
                        column_position = ?,
                        aenderungsdatum = CURRENT_TIMESTAMP
                    WHERE column_id = ?
                """, (actual["column_type"], actual["length"], 
                      actual["position"], col["column_id"]))
                results["updated"] += 1
            except Exception as e:
                results["errors"].append(f"Update {col['column_name']}: {str(e)}")
        
        # Gelöschte Spalten entfernen (nicht mehr in DB vorhanden)
        for col in diff["removed"]:
            try:
                cursor.execute("DELETE FROM MDP01_META.META_COLUMN WHERE column_id = ?", (col["column_id"],))
                results["deleted"] += 1
            except Exception as e:
                results["errors"].append(f"Delete {col['column_name']}: {str(e)}")
        
        conn.commit()
        conn.close()
        
        return results
    
    # =========================================================================
    # Job Execution
    # =========================================================================
    
    def execute_job(self, job_id: int, initial_load_mode: bool = False) -> int:
        """
        Führt ETL Job aus.
        
        Args:
            job_id: Job ID
            initial_load_mode: Wenn True, wird die Zieltabelle vor dem Load gelöscht
        
        Returns:
            Job Run ID
        
        Raises:
            Exception: Bei Ausführungsfehler
        """
        logger.info(f"Executing job {job_id} via orchestrator (initial_load_mode={initial_load_mode})")
        return self.orchestrator.execute_job(job_id, initial_load_mode=initial_load_mode)
    
    def cleanup_stale_running_jobs(self, hours_threshold: int = 2) -> int:
        """
        Markiert "hängende" RUNNING Jobs und Steps als FAILED.
        
        Jobs/Steps die länger als hours_threshold Stunden im Status RUNNING sind,
        werden als FAILED markiert.
        
        Args:
            hours_threshold: Anzahl Stunden nach denen ein Job als "stale" gilt
        
        Returns:
            Anzahl der bereinigten Runs
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 1. Finde und update stale JOB runs
        cursor.execute("""
            UPDATE MDP01_META.META_ETL_JOB_RUN
            SET status = 'FAILED',
                error_message = 'Job wurde als fehlgeschlagen markiert (Timeout/Stale Run Cleanup)',
                end_time = CURRENT_TIMESTAMP
            WHERE status = 'RUNNING'
            AND start_time < CURRENT_TIMESTAMP - CAST(? AS INTERVAL HOUR)
        """, (hours_threshold,))
        
        job_count = cursor.rowcount
        
        # 2. Finde und update stale STEP runs
        cursor.execute("""
            UPDATE MDP01_META.META_ETL_JOB_STEP_RUN
            SET status = 'FAILED',
                error_message = 'Step wurde als fehlgeschlagen markiert (Timeout/Stale Run Cleanup)',
                end_time = CURRENT_TIMESTAMP
            WHERE status = 'RUNNING'
            AND start_time < CURRENT_TIMESTAMP - CAST(? AS INTERVAL HOUR)
        """, (hours_threshold,))
        
        step_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        total_count = job_count + step_count
        logger.info(f"Cleaned up {job_count} stale job runs and {step_count} stale step runs")
        return total_count
    
    # =========================================================================
    # Job Run Control (Pause/Resume/Cancel)
    # =========================================================================
    
    def pause_job_run(self, job_run_id: int) -> bool:
        """
        Fordert Pause eines laufenden Jobs an.
        Der Job wird nach dem aktuellen Step pausiert.
        """
        return self.orchestrator.pause_job_run(job_run_id)
    
    def resume_job_run(self, job_run_id: int) -> int:
        """
        Setzt einen pausierten Job fort.
        """
        return self.orchestrator.resume_job_run(job_run_id)
    
    def cancel_job_run(self, job_run_id: int) -> bool:
        """
        Bricht einen laufenden oder pausierten Job ab.
        """
        return self.orchestrator.cancel_job_run(job_run_id)
    
    # =========================================================================
    # Job Run History
    # =========================================================================
    
    def get_job_runs(
        self, 
        job_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[ETLJobRun]:
        """
        Gibt Job Run History zurück.
        
        Args:
            job_id: Filter nach Job ID (optional)
            status: Filter nach Status (optional)
            limit: Max. Anzahl Ergebnisse
            offset: Offset für Pagination
        
        Returns:
            Liste von ETLJobRun
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT etl_job_run_id, etl_job_id, start_time, end_time, duration_seconds,
               status, error_message, 
               CAST(error_stack AS VARCHAR(2000)) AS error_stack, 
               create_timestamp
        FROM MDP01_META.META_ETL_JOB_RUN
        WHERE 1=1
        """
        params = []
        
        if job_id:
            query += " AND etl_job_id = ?"
            params.append(job_id)
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY start_time DESC"
        # Teradata: TOP n ersetzt LIMIT, keine OFFSET-Unterstützung in diesem Context
        # Workaround: Fetch all und in Python limitieren
        # Für Production: ROW_NUMBER() OVER (ORDER BY ...) QUALIFY ROW_NUMBER() verwenden
        
        cursor.execute(query, params)
        
        # Python-side pagination (Teradata LIMIT workaround)
        all_rows = cursor.fetchall()
        paginated_rows = all_rows[offset:offset+limit]
        
        runs = []
        for row in paginated_rows:
            runs.append(ETLJobRun(
                etl_job_run_id=row[0], etl_job_id=row[1], start_time=row[2],
                end_time=row[3], duration_seconds=row[4], status=row[5],
                error_message=row[6], error_stack=row[7], create_timestamp=row[8]
            ))
        
        conn.close()
        return runs
    
    def get_job_run_details(self, job_run_id: int) -> Optional[ETLJobRunWithSteps]:
        """
        Gibt Job Run mit Step Details zurück.
        
        Args:
            job_run_id: Job Run ID
        
        Returns:
            ETLJobRunWithSteps oder None
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Job Run
        cursor.execute("""
            SELECT r.etl_job_run_id, r.etl_job_id, r.start_time, r.end_time,
                   r.duration_seconds, r.status, r.error_message, 
                   CAST(r.error_stack AS VARCHAR(2000)) AS error_stack,
                   r.create_timestamp, j.job_name
            FROM MDP01_META.META_ETL_JOB_RUN r
            JOIN MDP01_META.META_ETL_JOB j ON r.etl_job_id = j.etl_job_id
            WHERE r.etl_job_run_id = ?
        """, (job_run_id,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        
        job_run = ETLJobRunWithSteps(
            etl_job_run_id=row[0], etl_job_id=row[1], start_time=row[2],
            end_time=row[3], duration_seconds=row[4], status=row[5],
            error_message=row[6], error_stack=row[7], create_timestamp=row[8],
            job_name=row[9]
        )
        
        # Step Runs - inklusive PARAMETERS für Debugging
        cursor.execute("""
            SELECT sr.etl_job_step_run_id, sr.etl_job_run_id, sr.etl_job_step_id,
                   sr.start_time, sr.end_time, sr.duration_seconds, sr.status,
                   sr.rows_read, sr.rows_inserted, sr.rows_updated, sr.rows_deleted,
                   sr.error_message, 
                   CAST(sr.error_stacktrace AS VARCHAR(2000)) AS error_stack, 
                   sr.was_skipped, sr.skip_reason,
                   sr.create_timestamp, s.step_name, s.step_order, s.step_category,
                   CAST(s.parameters AS VARCHAR(10000)) AS parameters
            FROM MDP01_META.META_ETL_JOB_STEP_RUN sr
            JOIN MDP01_META.META_ETL_JOB_STEP s ON sr.etl_job_step_id = s.etl_job_step_id
            WHERE sr.etl_job_run_id = ?
            ORDER BY s.step_order
        """, (job_run_id,))
        
        for row in cursor.fetchall():
            job_run.step_runs.append(ETLJobStepRunWithDetails(
                etl_job_step_run_id=row[0], etl_job_run_id=row[1],
                etl_job_step_id=row[2], start_time=row[3], end_time=row[4],
                duration_seconds=row[5], status=row[6], rows_read=row[7],
                rows_inserted=row[8], rows_updated=row[9], rows_deleted=row[10],
                error_message=row[11], error_stack=row[12], was_skipped=row[13],
                skip_reason=row[14], create_timestamp=row[15],
                step_name=row[16], step_order=row[17], step_category=row[18],
                parameters=row[19]
            ))
        
        conn.close()
        return job_run
    
    # =========================================================================
    # Statistics & Monitoring
    # =========================================================================
    
    def get_dashboard_stats(self) -> DashboardStats:
        """Gibt Dashboard Statistiken zurück"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Total & Active Jobs
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN is_active = 'Y' THEN 1 ELSE 0 END) as active
            FROM MDP01_META.META_ETL_JOB
        """)
        row = cursor.fetchone()
        total_jobs, active_jobs = row[0], row[1]
        
        # Running Jobs
        cursor.execute("""
            SELECT COUNT(DISTINCT etl_job_id)
            FROM MDP01_META.META_ETL_JOB_RUN
            WHERE status = 'RUNNING'
        """)
        running_jobs = cursor.fetchone()[0]
        
        # Recent Runs (last 10)
        cursor.execute("""
            SELECT TOP 10 etl_job_run_id, etl_job_id, start_time, end_time,
                   duration_seconds, status, error_message, 
                   CAST(error_stack AS VARCHAR(2000)) AS error_stack, 
                   create_timestamp
            FROM MDP01_META.META_ETL_JOB_RUN
            ORDER BY start_time DESC
        """)
        recent_runs = [
            ETLJobRun(
                etl_job_run_id=row[0], etl_job_id=row[1], start_time=row[2],
                end_time=row[3], duration_seconds=row[4], status=row[5],
                error_message=row[6], error_stack=row[7], create_timestamp=row[8]
            )
            for row in cursor.fetchall()
        ]
        
        # Failed runs last 24h
        cursor.execute("""
            SELECT COUNT(*)
            FROM MDP01_META.META_ETL_JOB_RUN
            WHERE status = 'FAILED' 
            AND start_time >= CURRENT_TIMESTAMP - INTERVAL '24' HOUR
        """)
        failed_24h = cursor.fetchone()[0]
        
        # Success rate last 24h
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success,
                COUNT(*) as total
            FROM MDP01_META.META_ETL_JOB_RUN
            WHERE start_time >= CURRENT_TIMESTAMP - INTERVAL '24' HOUR
        """)
        row = cursor.fetchone()
        success_rate = (row[0] / row[1] * 100) if row[1] > 0 else None
        
        conn.close()
        
        return DashboardStats(
            total_jobs=total_jobs,
            active_jobs=active_jobs,
            running_jobs=running_jobs,
            recent_runs=recent_runs,
            failed_runs_24h=failed_24h,
            success_rate_24h=success_rate
        )
    
    def get_job_performance(self, job_id: Optional[int] = None) -> List[JobPerformanceStats]:
        """Gibt Performance-Statistiken zurück"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT 
            j.etl_job_id,
            j.job_name,
            COUNT(*) as total_runs,
            SUM(CASE WHEN r.status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
            SUM(CASE WHEN r.status = 'FAILED' THEN 1 ELSE 0 END) as failed_count,
            AVG(r.duration_seconds) as avg_duration,
            MIN(r.duration_seconds) as min_duration,
            MAX(r.duration_seconds) as max_duration
        FROM MDP01_META.META_ETL_JOB j
        LEFT JOIN MDP01_META.META_ETL_JOB_RUN r ON j.etl_job_id = r.etl_job_id
        """
        
        if job_id:
            query += " WHERE j.etl_job_id = ?"
            params = [job_id]
        else:
            params = []
        
        query += " GROUP BY j.etl_job_id, j.job_name ORDER BY j.etl_job_id"
        
        cursor.execute(query, params)
        
        stats = []
        for row in cursor.fetchall():
            success_rate = (row[3] / row[2] * 100) if row[2] > 0 else None
            stats.append(JobPerformanceStats(
                etl_job_id=row[0],
                job_name=row[1],
                total_runs=row[2],
                success_count=row[3],
                failed_count=row[4],
                avg_duration_seconds=row[5],
                min_duration_seconds=row[6],
                max_duration_seconds=row[7],
                success_rate=success_rate
            ))
        
        conn.close()
        return stats

    def delete_job(self, job_id: int, delete_tables: bool = False) -> Dict[str, Any]:
        """
        Löscht einen ETL Job und alle zugehörigen Daten.
        
        Args:
            job_id: ID des zu löschenden Jobs
            delete_tables: Auch Staging/Error Tables in Teradata löschen
        
        Returns:
            Dict mit gelöschten Objekten
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        result = {
            'job_id': job_id,
            'deleted_steps': 0,
            'deleted_job_runs': 0,
            'deleted_step_runs': 0,
            'deleted_tables': []
        }
        
        # 1. Prüfen ob Job existiert
        cursor.execute("""
            SELECT JOB_NAME, TARGET_TABLE_ID FROM MDP01_META.META_ETL_JOB WHERE ETL_JOB_ID = ?
        """, (job_id,))
        job_row = cursor.fetchone()
        
        if not job_row:
            conn.close()
            raise ValueError(f"Job {job_id} not found")
        
        job_name = job_row[0]
        target_table_id = job_row[1]
        result['job_name'] = job_name
        
        # 2. Target Table Info für Table-Cleanup
        target_db = None
        target_table = None
        if delete_tables and target_table_id:
            cursor.execute("""
                SELECT d.DATABASE_NAME, t.TABLE_NAME 
                FROM MDP01_META.META_TABLE t
                JOIN MDP01_META.META_DATABASE d ON t.DATABASE_ID = d.DATABASE_ID
                WHERE t.TABLE_ID = ?
            """, (target_table_id,))
            table_row = cursor.fetchone()
            if table_row:
                target_db = table_row[0]
                target_table = table_row[1]
        
        # 3. Step Runs löschen (für alle Job Runs dieses Jobs)
        cursor.execute("""
            DELETE FROM MDP01_META.META_ETL_JOB_STEP_RUN 
            WHERE ETL_JOB_RUN_ID IN (
                SELECT ETL_JOB_RUN_ID FROM MDP01_META.META_ETL_JOB_RUN WHERE ETL_JOB_ID = ?
            )
        """, (job_id,))
        result['deleted_step_runs'] = cursor.rowcount
        
        # 4. Job Runs löschen
        cursor.execute("""
            DELETE FROM MDP01_META.META_ETL_JOB_RUN WHERE ETL_JOB_ID = ?
        """, (job_id,))
        result['deleted_job_runs'] = cursor.rowcount
        
        # 5. Job Steps löschen
        cursor.execute("""
            DELETE FROM MDP01_META.META_ETL_JOB_STEP WHERE ETL_JOB_ID = ?
        """, (job_id,))
        result['deleted_steps'] = cursor.rowcount
        
        # 6. Job löschen
        cursor.execute("""
            DELETE FROM MDP01_META.META_ETL_JOB WHERE ETL_JOB_ID = ?
        """, (job_id,))
        
        conn.commit()
        
        # 7. Optional: Staging/Error Tables löschen
        # SICHERHEIT: RAW-Layer Tabellen NIEMALS löschen!
        if delete_tables and target_db and target_table:
            # Prüfen ob Target im RAW-Layer liegt
            cursor.execute("""
                SELECT l.LAYER_NAME 
                FROM MDP01_META.META_TABLE t
                JOIN MDP01_META.META_LAYER l ON t.LAYER_ID = l.LAYER_ID
                WHERE t.TABLE_ID = ?
            """, (target_table_id,))
            layer_row = cursor.fetchone()
            target_layer = layer_row[0].upper() if layer_row else ''
            
            if 'RAW' in target_layer:
                logger.warning(f"SICHERHEIT: Tabelle {target_db}.{target_table} liegt im RAW-Layer - wird NICHT gelöscht!")
                result['warning'] = f"RAW-Layer Tabellen werden nie gelöscht: {target_db}.{target_table}"
            else:
                tables_to_drop = [
                    f"{target_db}.{target_table}_LOAD",
                    f"{target_db}.{target_table}_LOAD_log",
                    f"{target_db}.{target_table}_LOAD_err1",
                    f"{target_db}.{target_table}_LOAD_err2",
                    f"{target_db}.{target_table}"  # Zieltabelle (nur wenn NICHT RAW!)
                ]
                for table_name in tables_to_drop:
                    try:
                        cursor.execute(f"DROP TABLE {table_name}")
                        conn.commit()
                        result['deleted_tables'].append(table_name)
                        logger.info(f"Dropped table: {table_name}")
                    except Exception as e:
                        # Table existiert nicht - OK
                        logger.debug(f"Table {table_name} not found or could not be dropped: {e}")
        
        conn.close()
        logger.info(f"Deleted job {job_id} ({job_name}): {result}")
        return result


# =============================================================================
# Global Service Instance
# =============================================================================

# Service wird lazy initialisiert (beim ersten API Call)
_etl_service: Optional[ETLService] = None

def get_etl_service() -> ETLService:
    """Dependency Injection für FastAPI"""
    global _etl_service
    if _etl_service is None:
        _etl_service = ETLService()
    return _etl_service
