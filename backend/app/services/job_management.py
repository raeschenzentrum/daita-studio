"""
Job Management Service
======================

CRUD-Operationen für ETL Jobs und Steps.
Keine Ausführungs-Logik - nur Verwaltung.

Autor: metadaita Team
Datum: 2026-04-15
"""
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

import teradatasql
import yaml

from ..models.etl_models import ETLJob, ETLJobStep, ETLJobWithDetails

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models für diesen Service
# =============================================================================

from pydantic import BaseModel


class TableWithLoadStatus(BaseModel):
    """Tabelle mit Info ob Job existiert"""
    table_id: int
    table_name: str
    database_id: int
    database_name: str
    # Wird diese Tabelle BEFÜLLT? (Tabelle ist Target eines Jobs)
    has_job: bool
    job_id: Optional[int] = None
    job_name: Optional[str] = None
    job_status: Optional[str] = None  # Letzter Run-Status
    # Wird diese Tabelle als SOURCE genutzt? (Tabelle ist Source eines Jobs)
    is_used_as_source: bool = False
    downstream_job_id: Optional[int] = None
    downstream_job_name: Optional[str] = None
    downstream_target_table: Optional[str] = None


class ColumnMapping(BaseModel):
    """Spalten-Mapping für Step"""
    source_column: str
    target_column: str
    transformation: Optional[str] = None  # z.B. "CAST(x AS VARCHAR(100))"


class CreateJobRequest(BaseModel):
    """Request für Job-Erstellung"""
    job_name: str
    job_type: str
    source_table_id: int
    target_table_id: int


class CreateStepRequest(BaseModel):
    """Request für Step-Erstellung"""
    step_name: str
    step_order: int
    step_category: str
    sql_template_path: Optional[str] = None
    sql_inline: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class UpdateStepRequest(BaseModel):
    """Request für Step-Update (alle Felder optional)"""
    step_name: Optional[str] = None
    step_order: Optional[int] = None
    sql_template_path: Optional[str] = None
    sql_inline: Optional[str] = None
    is_active: Optional[str] = None
    is_critical: Optional[str] = None
    skip_on_empty: Optional[str] = None
    rollback_on_error: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


# =============================================================================
# Job Management Service
# =============================================================================

class JobManagementService:
    """
    Service für Job/Step CRUD-Operationen.
    
    Verantwortlichkeiten:
    - Jobs erstellen, bearbeiten, löschen
    - Steps erstellen, bearbeiten, löschen
    - Tabellen mit Load-Status abfragen
    - Jobs zwischen Layers abfragen
    """
    
    def __init__(self):
        """Initialisiert Service mit DB-Config"""
        # Config laden
        cfg_dir = Path("/home/tdops/ps_toolbox/PS_ROOT/subsystem/metadaita/cfg")
        database_yml = cfg_dir / "database.yml"
        
        with open(database_yml, 'r') as f:
            db_config = yaml.safe_load(f)
        
        self.db_config = db_config.get('teradata', {})
    
    def _get_connection(self) -> teradatasql.TeradataConnection:
        """Erstellt neue DB Connection"""
        conn = teradatasql.connect(
            host=self.db_config.get('host'),
            user=self.db_config.get('user'),
            password=self.db_config.get('password'),
            connect_timeout=self.db_config.get('connect_timeout', 10000)
        )
        # Timezone setzen
        try:
            cursor = conn.cursor()
            cursor.execute("SET TIME ZONE 'Europe/Berlin'")
        except Exception:
            pass
        return conn
    
    # =========================================================================
    # Abfragen: Tabellen mit Load-Status
    # =========================================================================
    
    def get_tables_with_load_status(self, layer_id: int) -> List[TableWithLoadStatus]:
        """
        Gibt alle Tabellen eines Layers zurück mit Info:
        - has_job: Wird diese Tabelle BEFÜLLT? (Tabelle ist Target eines Jobs)
        - is_used_as_source: Wird diese Tabelle als SOURCE genutzt?
        
        Args:
            layer_id: Layer-ID (1=RAW, 2=DISC, 3=REUS, 4=CONS)
        
        Returns:
            Liste von TableWithLoadStatus
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Query: Tabellen mit optionalem Job als TARGET und als SOURCE
        cursor.execute("""
            SELECT 
                t.table_id,
                t.table_name,
                d.database_id,
                d.database_name,
                -- Job der diese Tabelle BEFÜLLT (Target)
                j_target.etl_job_id as target_job_id,
                j_target.job_name as target_job_name,
                lr.status as last_run_status,
                -- Job der diese Tabelle als SOURCE nutzt
                j_source.etl_job_id as source_job_id,
                j_source.job_name as source_job_name,
                t_downstream.table_name as downstream_target_table
            FROM MDP01_META.META_TABLE t
            JOIN MDP01_META.META_DATABASE d ON t.database_id = d.database_id
            -- Job der diese Tabelle befüllt (Tabelle ist TARGET)
            LEFT JOIN MDP01_META.META_ETL_JOB j_target ON t.table_id = j_target.target_table_id
            LEFT JOIN (
                SELECT etl_job_id, status,
                       ROW_NUMBER() OVER (PARTITION BY etl_job_id ORDER BY start_time DESC) as rn
                FROM MDP01_META.META_ETL_JOB_RUN
            ) lr ON j_target.etl_job_id = lr.etl_job_id AND lr.rn = 1
            -- Job der diese Tabelle als Source nutzt (Tabelle wird weitergereicht)
            LEFT JOIN MDP01_META.META_ETL_JOB j_source ON t.table_id = j_source.source_table_id
            LEFT JOIN MDP01_META.META_TABLE t_downstream ON j_source.target_table_id = t_downstream.table_id
            WHERE d.layer_id = ?
            ORDER BY d.database_name, t.table_name
        """, (layer_id,))
        
        results = []
        for row in cursor.fetchall():
            results.append(TableWithLoadStatus(
                table_id=row[0],
                table_name=row[1],
                database_id=row[2],
                database_name=row[3],
                # Wird befüllt?
                has_job=row[4] is not None,
                job_id=row[4],
                job_name=row[5],
                job_status=row[6],
                # Wird als Source genutzt?
                is_used_as_source=row[7] is not None,
                downstream_job_id=row[7],
                downstream_job_name=row[8],
                downstream_target_table=row[9]
            ))
        
        conn.close()
        return results
    
    def get_jobs_by_transition(
        self, 
        source_layer_id: int, 
        target_layer_id: int
    ) -> List[ETLJobWithDetails]:
        """
        Gibt alle Jobs zurück die von einem Layer zum anderen gehen.
        
        Args:
            source_layer_id: Quell-Layer (z.B. 2 für RAW)
            target_layer_id: Ziel-Layer (z.B. 3 für DISC)
        
        Returns:
            Liste von Jobs mit Details
        """
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
                SELECT etl_job_id, status, start_time,
                       ROW_NUMBER() OVER (PARTITION BY etl_job_id ORDER BY start_time DESC) as rn
                FROM MDP01_META.META_ETL_JOB_RUN
            ) lr ON j.etl_job_id = lr.etl_job_id AND lr.rn = 1
            WHERE COALESCE(sd.layer_id, j.source_layer_id) = ?
              AND COALESCE(td.layer_id, j.target_layer_id) = ?
            ORDER BY j.job_name
        """, (source_layer_id, target_layer_id))
        
        jobs = []
        for row in cursor.fetchall():
            jobs.append(ETLJobWithDetails(
                etl_job_id=row[0],
                job_name=row[1],
                job_type=row[2],
                source_table_id=row[3],
                target_table_id=row[4],
                is_active=row[5],
                retry_count=3,
                timeout_seconds=3600,
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
    
    # =========================================================================
    # CRUD: Jobs
    # =========================================================================
    
    def create_job(self, request: CreateJobRequest) -> int:
        """
        Erstellt einen neuen ETL Job (ohne Steps).
        
        Returns:
            Neue Job-ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # PRÜFUNG: Job-Name bereits vergeben?
        cursor.execute("SELECT ETL_JOB_ID FROM MDP01_META.META_ETL_JOB WHERE JOB_NAME = ?", [request.job_name])
        existing_job = cursor.fetchone()
        if existing_job:
            conn.close()
            raise ValueError(f"Job mit Namen '{request.job_name}' existiert bereits (ID: {existing_job[0]})")
        
        # Nächste Job-ID ermitteln
        cursor.execute("SELECT COALESCE(MAX(etl_job_id), 0) + 1 FROM MDP01_META.META_ETL_JOB")
        new_job_id = cursor.fetchone()[0]
        
        cursor.execute("""
            INSERT INTO MDP01_META.META_ETL_JOB (
                etl_job_id, job_name, job_type, source_table_id, target_table_id,
                is_active, retry_count, timeout_seconds,
                create_timestamp, last_alter_timestamp
            ) VALUES (?, ?, ?, ?, ?, 'Y', 3, 3600, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (new_job_id, request.job_name, request.job_type, 
              request.source_table_id, request.target_table_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Created job {new_job_id}: {request.job_name}")
        return new_job_id
    
    def update_job(
        self, 
        job_id: int, 
        job_name: Optional[str] = None,
        is_active: Optional[str] = None
    ) -> bool:
        """Aktualisiert einen Job"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if job_name:
            updates.append("job_name = ?")
            params.append(job_name)
        if is_active:
            updates.append("is_active = ?")
            params.append(is_active)
        
        if not updates:
            return False
        
        updates.append("last_alter_timestamp = CURRENT_TIMESTAMP")
        params.append(job_id)
        
        cursor.execute(f"""
            UPDATE MDP01_META.META_ETL_JOB 
            SET {', '.join(updates)}
            WHERE etl_job_id = ?
        """, params)
        
        conn.commit()
        conn.close()
        
        logger.info(f"Updated job {job_id}")
        return True
    
    def delete_job(self, job_id: int) -> bool:
        """
        Löscht einen Job und alle zugehörigen Steps.
        
        ACHTUNG: Löscht auch Job-Runs!
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Erst Step-Runs löschen
        cursor.execute("""
            DELETE FROM MDP01_META.META_ETL_JOB_STEP_RUN 
            WHERE etl_job_run_id IN (
                SELECT etl_job_run_id FROM MDP01_META.META_ETL_JOB_RUN
                WHERE etl_job_id = ?
            )
        """, (job_id,))
        
        # Dann Job-Runs löschen
        cursor.execute("DELETE FROM MDP01_META.META_ETL_JOB_RUN WHERE etl_job_id = ?", (job_id,))
        
        # Dann Steps löschen
        cursor.execute("DELETE FROM MDP01_META.META_ETL_JOB_STEP WHERE etl_job_id = ?", (job_id,))
        
        # Dann Job löschen
        cursor.execute("DELETE FROM MDP01_META.META_ETL_JOB WHERE etl_job_id = ?", (job_id,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Deleted job {job_id} with all steps and runs")
        return True
    
    # =========================================================================
    # CRUD: Steps
    # =========================================================================
    
    def add_step(self, job_id: int, request: CreateStepRequest) -> int:
        """
        Fügt einen neuen Step zu einem Job hinzu.
        
        Returns:
            Neue Step-ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Nächste Step-ID ermitteln
        cursor.execute("SELECT COALESCE(MAX(etl_job_step_id), 0) + 1 FROM MDP01_META.META_ETL_JOB_STEP")
        new_step_id = cursor.fetchone()[0]
        
        # Parameters als JSON
        params_json = json.dumps(request.parameters) if request.parameters else None
        
        cursor.execute("""
            INSERT INTO MDP01_META.META_ETL_JOB_STEP (
                etl_job_step_id, etl_job_id, step_name, step_order, step_category,
                sql_template_path, sql_inline, parameters,
                is_active, is_critical, skip_on_empty, rollback_on_error,
                create_timestamp, last_alter_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Y', 'Y', 'N', 'Y', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (new_step_id, job_id, request.step_name, request.step_order, 
              request.step_category, request.sql_template_path, request.sql_inline, params_json))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Added step {new_step_id} to job {job_id}: {request.step_name}")
        return new_step_id
    
    def update_step(self, step_id: int, request: 'UpdateStepRequest') -> bool:
        """Aktualisiert einen Step (alle Felder aus UpdateStepRequest)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        updates = []
        params = []

        if request.step_name is not None:
            updates.append("step_name = ?")
            params.append(request.step_name)
        if request.step_order is not None:
            updates.append("step_order = ?")
            params.append(request.step_order)
        if request.sql_template_path is not None:
            updates.append("sql_template_path = ?")
            params.append(request.sql_template_path)
        if request.sql_inline is not None:
            updates.append("sql_inline = ?")
            params.append(request.sql_inline)
        if request.is_active is not None:
            updates.append("is_active = ?")
            params.append(request.is_active)
        if request.is_critical is not None:
            updates.append("is_critical = ?")
            params.append(request.is_critical)
        if request.skip_on_empty is not None:
            updates.append("skip_on_empty = ?")
            params.append(request.skip_on_empty)
        if request.rollback_on_error is not None:
            updates.append("rollback_on_error = ?")
            params.append(request.rollback_on_error)
        if request.parameters is not None:
            updates.append("parameters = ?")
            params.append(json.dumps(request.parameters))

        if not updates:
            return False

        updates.append("last_alter_timestamp = CURRENT_TIMESTAMP")
        params.append(step_id)

        cursor.execute(f"""
            UPDATE MDP01_META.META_ETL_JOB_STEP
            SET {', '.join(updates)}
            WHERE etl_job_step_id = ?
        """, params)

        conn.commit()
        conn.close()

        logger.info(f"Updated step {step_id}")
        return True
    
    def delete_step(self, step_id: int) -> bool:
        """Löscht einen Step"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Erst Step-Runs löschen
        cursor.execute("DELETE FROM MDP01_META.META_ETL_JOB_STEP_RUN WHERE etl_job_step_id = ?", (step_id,))
        
        # Dann Step löschen
        cursor.execute("DELETE FROM MDP01_META.META_ETL_JOB_STEP WHERE etl_job_step_id = ?", (step_id,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Deleted step {step_id}")
        return True
    
    def update_step_mapping(
        self, 
        step_id: int, 
        column_mappings: List[ColumnMapping]
    ) -> bool:
        """
        Aktualisiert das Spalten-Mapping eines Steps (in PARAMETERS JSON).
        
        Args:
            step_id: Step-ID
            column_mappings: Liste von Spalten-Mappings
        
        Returns:
            True bei Erfolg
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Bestehende Parameters laden
        cursor.execute("""
            SELECT parameters FROM MDP01_META.META_ETL_JOB_STEP
            WHERE etl_job_step_id = ?
        """, (step_id,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
        
        # Parameters parsen oder neu erstellen
        params = json.loads(row[0]) if row[0] else {}
        
        # Mappings aktualisieren
        params['column_mappings'] = [
            {
                'source_column': m.source_column,
                'target_column': m.target_column,
                'transformation': m.transformation
            }
            for m in column_mappings
        ]
        
        # Zurückschreiben
        cursor.execute("""
            UPDATE MDP01_META.META_ETL_JOB_STEP
            SET parameters = ?,
                last_alter_timestamp = CURRENT_TIMESTAMP
            WHERE etl_job_step_id = ?
        """, (json.dumps(params), step_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Updated mapping for step {step_id}: {len(column_mappings)} columns")
        return True


# =============================================================================
# Singleton Instanz
# =============================================================================

_job_management_service: Optional[JobManagementService] = None


def get_job_management_service() -> JobManagementService:
    """Factory für JobManagementService (Singleton)"""
    global _job_management_service
    if _job_management_service is None:
        _job_management_service = JobManagementService()
    return _job_management_service
