"""
Metadata-Driven ETL Orchestrator
==================================

Orchestriert ETL-Jobs basierend auf Metadaten aus META_ETL_JOB und META_ETL_JOB_STEP.
Führt Steps sequentiell aus mit Error-Handling, Rollback und Monitoring.

Autor: DWH MVP Team
Datum: 2026-01-19
Version: 1.0
"""

import sys
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass
import traceback

# Teradata SQL Driver
try:
    import teradatasql
except ImportError:
    print("ERROR: teradatasql not installed. Run: pip install teradatasql")
    sys.exit(1)

# Template Engine (lokal aus services/)
try:
    from .template_engine import SQLTemplateEngine, load_parameters_from_json
except ImportError:
    from template_engine import SQLTemplateEngine, load_parameters_from_json


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ETLJob:
    """Repräsentiert einen ETL-Job aus META_ETL_JOB."""
    etl_job_id: int
    job_name: str
    job_type: str
    source_table_id: Optional[int]
    target_table_id: Optional[int]
    is_active: str
    retry_count: int = 3
    timeout_seconds: int = 3600


@dataclass
class ETLJobStep:
    """Repräsentiert einen Step aus META_ETL_JOB_STEP."""
    etl_job_step_id: int
    etl_job_id: int
    step_name: str
    step_order: int
    step_category: str
    sql_template_path: Optional[str]
    sql_inline: Optional[str]
    python_module: Optional[str]
    python_function: Optional[str]
    parameters: Optional[str]  # JSON String
    condition_sql: Optional[str]
    skip_on_empty: str
    is_critical: str
    rollback_on_error: str
    is_active: str


@dataclass
class StepRunMetrics:
    """Metriken für einen Step-Run."""
    rows_read: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_deleted: int = 0
    duration_seconds: float = 0.0


# =============================================================================
# Main Orchestrator
# =============================================================================

class MetadataETLOrchestrator:
    """
    Orchestriert ETL-Jobs basierend auf Metadaten.
    
    Features:
    - Lädt Job-Definition aus META_ETL_JOB
    - Lädt Steps aus META_ETL_JOB_STEP (sortiert nach step_order)
    - Führt Steps sequentiell aus
    - Error-Handling mit Rollback
    - Protokolliert in META_ETL_JOB_RUN und META_ETL_JOB_STEP_RUN
    
    Example:
        >>> config = load_config('config/database.yml')
        >>> orchestrator = MetadataETLOrchestrator(config)
        >>> orchestrator.execute_job(job_id=1)
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialisiert den Orchestrator.
        
        Args:
            config: Konfiguration aus database.yml
        """
        self.config = config
        self.teradata_config = config['teradata']
        self.etl_config = config['etl']
        
        # Template-Engine initialisieren
        template_base_dir = self.etl_config.get('sql_templates_base_dir')
        self.template_engine = SQLTemplateEngine(base_dir=template_base_dir)
        
        # Logging Connection (separate Session für Meta-Daten Updates)
        # Diese Connection wird für Job-Run/Step-Run Updates verwendet,
        # damit Rollbacks der Daten-Transaktion die Logging-Daten nicht löschen
        self._log_conn = None
        
        # Logging
        self._setup_logging()
        
        logger.info("MetadataETLOrchestrator initialized")
    
    def _setup_logging(self):
        """Konfiguriert Logging."""
        log_dir = Path(self.etl_config.get('log_dir', '/tmp/dwh_etl_logs'))
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / f"etl_orchestrator_{datetime.now():%Y%m%d_%H%M%S}.log"
        
        logging.basicConfig(
            level=logging.DEBUG if self.etl_config.get('verbose') else logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        global logger
        logger = logging.getLogger(__name__)
        logger.info(f"Logging to: {log_file}")
    
    def get_connection(self, autocommit: bool = False) -> teradatasql.TeradataConnection:
        """
        Erstellt Teradata-Verbindung für Daten-Operationen.
        
        Args:
            autocommit: Autocommit aktivieren (False für Transaktionen)
        
        Returns:
            Teradata-Connection
        """
        logger.debug(f"Connecting to Teradata: {self.teradata_config['host']}")
        
        conn = teradatasql.connect(
            host=self.teradata_config['host'],
            user=self.teradata_config['user'],
            password=self.teradata_config['password'],
            tmode=self.etl_config.get('transaction_mode', 'ANSI')
        )
        
        conn.autocommit = autocommit
        
        # Session-Zeitzone auf Europe/Berlin setzen (CET/CEST)
        try:
            cursor = conn.cursor()
            cursor.execute("SET TIME ZONE 'Europe/Berlin'")
            logger.debug("Session timezone set to Europe/Berlin")
        except Exception as e:
            logger.warning(f"Could not set session timezone: {e}")
        
        return conn
    
    def _get_log_connection(self) -> teradatasql.TeradataConnection:
        """
        Gibt die Logging-Connection zurück (oder erstellt sie).
        
        Diese separate Connection wird für Job-Run/Step-Run Updates verwendet,
        damit Rollbacks der Daten-Transaktion die Logging-Daten nicht löschen.
        
        Returns:
            Teradata-Connection mit autocommit=True
        """
        if self._log_conn is None:
            logger.debug("Creating dedicated logging connection")
            self._log_conn = teradatasql.connect(
                host=self.teradata_config['host'],
                user=self.teradata_config['user'],
                password=self.teradata_config['password'],
                tmode=self.etl_config.get('transaction_mode', 'ANSI')
            )
            self._log_conn.autocommit = True  # Jedes Statement sofort committen
            
            # Session-Zeitzone setzen
            try:
                cursor = self._log_conn.cursor()
                cursor.execute("SET TIME ZONE 'Europe/Berlin'")
            except Exception:
                pass
        
        return self._log_conn
    
    def _close_log_connection(self):
        """Schließt die Logging-Connection."""
        if self._log_conn is not None:
            try:
                self._log_conn.close()
            except Exception:
                pass
            self._log_conn = None
    
    def execute_job(self, job_id: int, execution_mode: str = 'MANUAL', initial_load_mode: bool = False) -> int:
        """
        Führt einen ETL-Job aus.
        
        Args:
            job_id: ID des Jobs (META_ETL_JOB.etl_job_id)
            execution_mode: MANUAL, SCHEDULED, API, RETRY
            initial_load_mode: Wenn True, wird die Zieltabelle vor dem Load gelöscht
        
        Returns:
            etl_job_run_id der Ausführung
        
        Raises:
            Exception: Bei kritischen Fehlern
        """
        logger.info(f"=" * 80)
        logger.info(f"Starting ETL Job: job_id={job_id}, mode={execution_mode}, initial_load={initial_load_mode}")
        logger.info(f"=" * 80)
        
        conn = self.get_connection(autocommit=False)
        
        try:
            # 1. Job laden
            job = self._load_job(conn, job_id)
            logger.info(f"Loaded job: {job.job_name} (type={job.job_type})")
            
            # 2. Job Run erstellen
            job_run_id = self._create_job_run(conn, job_id, execution_mode)
            logger.info(f"Created job_run_id: {job_run_id}")
            
            # 3. Initial Load Mode: Prüfe ob DELETE_TARGET Step vorhanden
            if initial_load_mode:
                logger.warning(f"⚠️ INITIAL LOAD MODE ACTIVATED - Looking for DELETE_TARGET step")
            
            # 4. Steps laden (sortiert nach step_order)
            steps = self._load_steps(conn, job_id)
            logger.info(f"Loaded {len(steps)} steps for execution")
            
            # 5. Steps ausführen
            last_step_rows = None
            has_failed_step = False
            executed_steps = 0
            
            for step in steps:
                logger.info(f"-" * 80)
                logger.info(f"Executing Step {step.step_order}: {step.step_name} ({step.step_category})")
                logger.info(f"-" * 80)
                
                # Prüfe Control-Flag (Pause/Cancel) vor jedem Step
                control_action = self._check_control_flag(conn, job_run_id, step.step_order)
                if control_action == 'PAUSED':
                    logger.info(f"Job paused before step {step.step_order}")
                    return job_run_id
                elif control_action == 'CANCELLED':
                    logger.info(f"Job cancelled before step {step.step_order}")
                    return job_run_id
                
                # DELETE_TARGET Step: Nur ausführen wenn initial_load_mode=True
                if step.step_category == 'DELETE_TARGET':
                    if not initial_load_mode:
                        logger.info(f"Skipping DELETE_TARGET step (initial_load_mode=False)")
                        self._create_skipped_step_run(conn, job_run_id, step, skip_reason="Initial Load Mode nicht aktiviert")
                        continue
                    else:
                        logger.warning(f"🔥 Executing DELETE_TARGET step (initial_load_mode=True)")
                
                # Wenn ein vorheriger Step fehlgeschlagen ist, überspringe alle weiteren
                if has_failed_step:
                    logger.info(f"Skipping step {step.step_order} due to previous failure")
                    self._create_skipped_step_run(conn, job_run_id, step, skip_reason="Vorheriger Step fehlgeschlagen")
                    continue
                
                # Skip-Logik für skip_on_empty
                if self._should_skip_step(step, last_step_rows):
                    logger.info(f"Skipping step (skip_on_empty=Y and last_step returned 0 rows)")
                    self._create_skipped_step_run(conn, job_run_id, step, skip_reason="Vorheriger Step lieferte 0 Zeilen")
                    continue
                
                # Step ausführen
                success, metrics = self._execute_step(conn, job_run_id, step)
                executed_steps += 1
                
                if success:
                    last_step_rows = metrics.rows_inserted + metrics.rows_updated
                    logger.info(f"Step completed: inserted={metrics.rows_inserted}, updated={metrics.rows_updated}, duration={metrics.duration_seconds}s")
                else:
                    has_failed_step = True
                    logger.warning(f"Step {step.step_order} failed - remaining steps will be skipped")
            
            # 5. Job-Status bestimmen
            if has_failed_step:
                conn.rollback()  # Rollback der Daten-Transaktion
                self._update_job_run(conn, job_run_id, status='FAILED', 
                                     error_message=f"Job fehlgeschlagen - {executed_steps} Steps ausgeführt, davon mindestens einer fehlgeschlagen")
                # Kein conn.commit() nötig - Log-Connection hat autocommit=True
                logger.warning(f"Job {job.job_name} completed with FAILURES")
            else:
                conn.commit()  # Commit der Daten-Transaktion (erfolgreiche Steps)
                self._update_job_run(conn, job_run_id, status='SUCCESS')
                # Kein conn.commit() nötig - Log-Connection hat autocommit=True
                logger.info(f"Job {job.job_name} completed successfully")
            
            return job_run_id
        
        except Exception as e:
            # 6. Fehler → Rollback
            logger.error(f"Job failed with error: {str(e)}")
            logger.error(traceback.format_exc())
            
            conn.rollback()  # Rollback der Daten-Transaktion
            
            try:
                self._update_job_run(
                    conn, 
                    job_run_id, 
                    status='FAILED',
                    error_message=str(e),
                    error_stack=traceback.format_exc()
                )
                # Kein conn.commit() nötig - Log-Connection hat autocommit=True
            except:
                logger.error("Failed to update job_run status")
            
            raise
        
        finally:
            conn.close()
            self._close_log_connection()  # Log-Connection auch schließen
            logger.info("=" * 80)
    
    def _load_job(self, conn: teradatasql.TeradataConnection, job_id: int) -> ETLJob:
        """Lädt Job-Definition aus META_ETL_JOB."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                etl_job_id, job_name, job_type, 
                source_table_id, target_table_id, is_active
            FROM MDP01_META.META_ETL_JOB
            WHERE etl_job_id = ?
        """, (job_id,))
        
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Job not found: etl_job_id={job_id}")
        
        return ETLJob(
            etl_job_id=row[0],
            job_name=row[1],
            job_type=row[2],
            source_table_id=row[3],
            target_table_id=row[4],
            is_active=row[5]
        )
    
    def _load_steps(self, conn: teradatasql.TeradataConnection, job_id: int) -> List[ETLJobStep]:
        """Lädt Steps aus META_ETL_JOB_STEP (sortiert nach step_order)."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                etl_job_step_id, etl_job_id, step_name, step_order, step_category,
                sql_template_path, sql_inline, python_module, python_function,
                parameters, condition_sql, skip_on_empty, is_critical, 
                rollback_on_error, is_active
            FROM MDP01_META.META_ETL_JOB_STEP
            WHERE etl_job_id = ?
              AND is_active = 'Y'
            ORDER BY step_order
        """, (job_id,))
        
        steps = []
        for row in cursor.fetchall():
            steps.append(ETLJobStep(
                etl_job_step_id=row[0],
                etl_job_id=row[1],
                step_name=row[2],
                step_order=row[3],
                step_category=row[4],
                sql_template_path=row[5],
                sql_inline=row[6],
                python_module=row[7],
                python_function=row[8],
                parameters=row[9],
                condition_sql=row[10],
                skip_on_empty=row[11],
                is_critical=row[12],
                rollback_on_error=row[13],
                is_active=row[14]
            ))
        
        return steps
    
    def _create_job_run(
        self, 
        conn: teradatasql.TeradataConnection, 
        job_id: int, 
        execution_mode: str
    ) -> int:
        """Erstellt Job-Run Eintrag in META_ETL_JOB_RUN (über Log-Connection)."""
        log_conn = self._get_log_connection()
        cursor = log_conn.cursor()
        cursor.execute("""
            INSERT INTO MDP01_META.META_ETL_JOB_RUN (
                etl_job_id, run_timestamp, start_time, status, execution_mode
            ) VALUES (?, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6), 'RUNNING', ?)
        """, (job_id, execution_mode))
        
        # Get generated job_run_id
        cursor.execute("""
            SELECT etl_job_run_id
            FROM MDP01_META.META_ETL_JOB_RUN
            WHERE etl_job_id = ?
            ORDER BY run_timestamp DESC
        """, (job_id,))
        
        return cursor.fetchone()[0]
    
    def _execute_step(
        self,
        conn: teradatasql.TeradataConnection,
        job_run_id: int,
        step: ETLJobStep
    ) -> tuple:
        """
        Führt einen einzelnen Step aus.
        
        Unterstützt:
        - SQL via sql_template_path oder sql_inline
        - Python Module via python_module + python_function (z.B. TPT_LOAD)
        
        Returns:
            Tuple (success: bool, metrics: StepRunMetrics)
        """
        start_time = datetime.now()
        metrics = StepRunMetrics()
        
        # Step Run erstellen
        step_run_id = self._create_step_run(conn, job_run_id, step.etl_job_step_id)
        
        try:
            # Parameter laden
            params = load_parameters_from_json(step.parameters) if step.parameters else {}
            
            # =========================================================================
            # Python Module Execution (z.B. TPT_LOAD)
            # =========================================================================
            if step.python_module and step.python_function:
                logger.info(f"Executing Python: {step.python_module}.{step.python_function}")
                
                success, result_metrics = self._execute_python_step(
                    conn, step, params, job_run_id
                )
                
                # Metriken übernehmen
                metrics.rows_inserted = result_metrics.get('rows_inserted', 0)
                metrics.rows_updated = result_metrics.get('rows_updated', 0)
                metrics.rows_deleted = result_metrics.get('rows_deleted', 0)
                metrics.duration_seconds = (datetime.now() - start_time).total_seconds()
                
                # Step Run updaten
                self._update_step_run(
                    conn, step_run_id,
                    status='SUCCESS' if success else 'FAILED',
                    metrics=metrics,
                    executed_sql=f"Python: {step.python_module}.{step.python_function}",
                    error_message=result_metrics.get('error_message') if not success else None
                )
                
                return (success, metrics)
            
            # =========================================================================
            # SQL Execution (Template oder Inline)
            # =========================================================================
            if step.sql_template_path:
                # Template rendern
                sql = self.template_engine.render(step.sql_template_path, params)
            elif step.sql_inline:
                sql = step.sql_inline
            else:
                raise ValueError(f"Step {step.step_name}: Neither sql_template_path, sql_inline, nor python_module provided")
            
            logger.debug(f"Executing SQL:\n{sql[:500]}...")
            
            # SQL ausführen
            cursor = conn.cursor()
            cursor.execute(sql)
            
            # COMMIT nach jedem SQL erforderlich!
            # Teradata ANSI Mode: Nach DDL-Statements (CREATE VOLATILE TABLE)
            # muss ein COMMIT erfolgen, bevor weitere Statements ausgeführt werden.
            # Volatile Tables mit "ON COMMIT PRESERVE ROWS" bleiben erhalten.
            conn.commit()
            
            # Metriken sammeln
            metrics.rows_inserted = cursor.rowcount if cursor.rowcount > 0 else 0
            metrics.duration_seconds = (datetime.now() - start_time).total_seconds()
            
            # Step Run updaten (SUCCESS)
            self._update_step_run(
                conn, step_run_id, 
                status='SUCCESS',
                metrics=metrics,
                executed_sql=sql
            )
            
            return (True, metrics)
        
        except Exception as e:
            # Step fehlgeschlagen
            logger.error(f"Step failed: {str(e)}")
            
            metrics.duration_seconds = (datetime.now() - start_time).total_seconds()
            
            self._update_step_run(
                conn, step_run_id,
                status='FAILED',
                metrics=metrics,
                error_message=str(e),
                error_stacktrace=traceback.format_exc()
            )
            
            # KEIN COMMIT hier - der finale Status wird am Ende von execute_job() commited
            # Dadurch bleiben Volatile Tables erhalten falls wir retry-Logik implementieren
            
            return (False, metrics)
    
    def _execute_python_step(
        self,
        conn: teradatasql.TeradataConnection,
        step: ETLJobStep,
        parameters: Dict[str, Any],
        job_run_id: int
    ) -> tuple:
        """
        Führt einen Python-basierten Step aus (z.B. TPT_LOAD).
        
        Args:
            conn: Teradata Connection
            step: Der auszuführende Step
            parameters: Parameter aus PARAMETERS JSON
            job_run_id: ID des aktuellen Job Runs
        
        Returns:
            Tuple (success: bool, metrics: Dict)
        """
        import importlib
        
        # Module laden
        try:
            # Versuche relatives Import aus backend.app.services/
            module = importlib.import_module(f'backend.app.services.{step.python_module}')
        except ImportError:
            try:
                # Fallback 1: app.services (für lokale Tests)
                module = importlib.import_module(f'app.services.{step.python_module}')
            except ImportError:
                # Fallback 2: relatives Import (same package)
                module = importlib.import_module(f'.{step.python_module}', package=__package__)
        
        # Funktion holen
        if not hasattr(module, step.python_function):
            raise ValueError(
                f"Function '{step.python_function}' not found in module '{step.python_module}'"
            )
        
        func = getattr(module, step.python_function)
        
        # Context für die Funktion
        context = {
            'job_run_id': job_run_id,
            'step_id': step.etl_job_step_id,
            'step_name': step.step_name,
            'step_category': step.step_category
        }
        
        # Funktion aufrufen
        logger.info(f"Calling {step.python_module}.{step.python_function}()")
        success, metrics = func(conn, parameters, context)
        
        return (success, metrics)
    
    def _create_step_run(
        self,
        conn: teradatasql.TeradataConnection,
        job_run_id: int,
        step_id: int
    ) -> int:
        """Erstellt Step-Run Eintrag (über Log-Connection)."""
        log_conn = self._get_log_connection()
        cursor = log_conn.cursor()
        cursor.execute("""
            INSERT INTO MDP01_META.META_ETL_JOB_STEP_RUN (
                etl_job_run_id, etl_job_step_id, start_time, status
            ) VALUES (?, ?, CURRENT_TIMESTAMP(6), 'RUNNING')
        """, (job_run_id, step_id))
        
        cursor.execute("""
            SELECT etl_job_step_run_id
            FROM MDP01_META.META_ETL_JOB_STEP_RUN
            WHERE etl_job_run_id = ? AND etl_job_step_id = ?
            ORDER BY start_time DESC
        """, (job_run_id, step_id))
        
        return cursor.fetchone()[0]
    
    def _update_step_run(
        self,
        conn: teradatasql.TeradataConnection,
        step_run_id: int,
        status: str,
        metrics: StepRunMetrics,
        executed_sql: str = None,
        error_message: str = None,
        error_stacktrace: str = None
    ):
        """Aktualisiert Step-Run mit Results (über Log-Connection)."""
        log_conn = self._get_log_connection()
        cursor = log_conn.cursor()
        cursor.execute("""
            UPDATE MDP01_META.META_ETL_JOB_STEP_RUN
            SET 
                end_time = CURRENT_TIMESTAMP(6),
                duration_seconds = ?,
                status = ?,
                rows_inserted = ?,
                rows_updated = ?,
                executed_sql = ?,
                error_message = ?,
                error_stacktrace = ?
            WHERE etl_job_step_run_id = ?
        """, (
            metrics.duration_seconds,
            status,
            metrics.rows_inserted,
            metrics.rows_updated,
            executed_sql,
            error_message,
            error_stacktrace,
            step_run_id
        ))
    
    def _update_job_run(
        self,
        conn: teradatasql.TeradataConnection,
        job_run_id: int,
        status: str,
        error_message: str = None,
        error_stack: str = None
    ):
        """Aktualisiert Job-Run Status (über Log-Connection)."""
        log_conn = self._get_log_connection()
        cursor = log_conn.cursor()
        cursor.execute("""
            UPDATE MDP01_META.META_ETL_JOB_RUN
            SET 
                end_time = CURRENT_TIMESTAMP(6),
                duration_seconds = (CURRENT_TIMESTAMP(6) - start_time) SECOND(4),
                status = ?,
                error_message = ?,
                error_stack = ?
            WHERE etl_job_run_id = ?
        """, (status, error_message, error_stack, job_run_id))
    
    def _check_control_flag(
        self, 
        conn: teradatasql.TeradataConnection, 
        job_run_id: int,
        current_step_order: int
    ) -> Optional[str]:
        """
        Prüft ob ein Pause/Cancel-Request vorliegt.
        Verwendet Log-Connection um die Daten-Transaktion nicht zu stören.
        
        Returns:
            'PAUSED' wenn pausiert wurde
            'CANCELLED' wenn abgebrochen wurde
            None wenn normal weiterlaufen soll
        """
        # Log-Connection verwenden, damit Daten-Transaktion nicht gestört wird
        log_conn = self._get_log_connection()
        cursor = log_conn.cursor()
        cursor.execute("""
            SELECT control_flag
            FROM MDP01_META.META_ETL_JOB_RUN
            WHERE etl_job_run_id = ?
        """, (job_run_id,))
        
        row = cursor.fetchone()
        if not row or not row[0]:
            return None
        
        control_flag = row[0].strip() if row[0] else None
        
        if control_flag == 'PAUSE_REQUESTED':
            # Pause ausführen: Status auf PAUSED setzen, paused_at_step merken
            logger.info(f"Pause requested - stopping before step {current_step_order}")
            cursor.execute("""
                UPDATE MDP01_META.META_ETL_JOB_RUN
                SET status = 'PAUSED',
                    paused_at_step = ?,
                    control_flag = NULL
                WHERE etl_job_run_id = ?
            """, (current_step_order, job_run_id))
            # Log-Connection hat autocommit=True, kein explizites commit nötig
            return 'PAUSED'
        
        elif control_flag == 'CANCEL_REQUESTED':
            # Cancel ausführen: Status auf CANCELLED setzen
            logger.info(f"Cancel requested - aborting job")
            cursor.execute("""
                UPDATE MDP01_META.META_ETL_JOB_RUN
                SET status = 'CANCELLED',
                    end_time = CURRENT_TIMESTAMP(6),
                    control_flag = NULL,
                    error_message = 'Job wurde manuell abgebrochen'
                WHERE etl_job_run_id = ?
            """, (job_run_id,))
            # Log-Connection hat autocommit=True, kein explizites commit nötig
            return 'CANCELLED'
        
        return None
    
    # =========================================================================
    # Public Control Methods (für API)
    # =========================================================================
    
    def pause_job_run(self, job_run_id: int) -> bool:
        """
        Fordert Pause eines laufenden Jobs an.
        Der Job wird nach dem aktuellen Step pausiert.
        
        Returns:
            True wenn erfolgreich, False wenn Job nicht RUNNING ist
        """
        conn = self.get_connection(autocommit=True)
        cursor = conn.cursor()
        
        # Prüfe ob Job RUNNING ist
        cursor.execute("""
            SELECT status FROM MDP01_META.META_ETL_JOB_RUN
            WHERE etl_job_run_id = ?
        """, (job_run_id,))
        
        row = cursor.fetchone()
        if not row or row[0].strip() != 'RUNNING':
            conn.close()
            return False
        
        # Setze Pause-Flag
        cursor.execute("""
            UPDATE MDP01_META.META_ETL_JOB_RUN
            SET control_flag = 'PAUSE_REQUESTED'
            WHERE etl_job_run_id = ?
        """, (job_run_id,))
        
        conn.close()
        logger.info(f"Pause requested for job_run_id={job_run_id}")
        return True
    
    def cancel_job_run(self, job_run_id: int) -> bool:
        """
        Fordert Abbruch eines laufenden/pausierten Jobs an.
        
        Returns:
            True wenn erfolgreich
        """
        conn = self.get_connection(autocommit=True)
        cursor = conn.cursor()
        
        # Prüfe ob Job RUNNING oder PAUSED ist
        cursor.execute("""
            SELECT status FROM MDP01_META.META_ETL_JOB_RUN
            WHERE etl_job_run_id = ?
        """, (job_run_id,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
        
        status = row[0].strip()
        
        if status == 'PAUSED':
            # Direkt auf CANCELLED setzen
            cursor.execute("""
                UPDATE MDP01_META.META_ETL_JOB_RUN
                SET status = 'CANCELLED',
                    end_time = CURRENT_TIMESTAMP(6),
                    error_message = 'Job wurde manuell abgebrochen'
                WHERE etl_job_run_id = ?
            """, (job_run_id,))
        elif status == 'RUNNING':
            # Cancel-Flag setzen
            cursor.execute("""
                UPDATE MDP01_META.META_ETL_JOB_RUN
                SET control_flag = 'CANCEL_REQUESTED'
                WHERE etl_job_run_id = ?
            """, (job_run_id,))
        else:
            conn.close()
            return False
        
        conn.close()
        logger.info(f"Cancel requested for job_run_id={job_run_id}")
        return True
    
    def resume_job_run(self, job_run_id: int) -> int:
        """
        Setzt einen pausierten Job fort.
        
        Returns:
            job_run_id wenn erfolgreich, 0 wenn Job nicht PAUSED ist
        """
        conn = self.get_connection(autocommit=True)
        cursor = conn.cursor()
        
        # Prüfe ob Job PAUSED ist und hole Daten
        cursor.execute("""
            SELECT status, etl_job_id, paused_at_step
            FROM MDP01_META.META_ETL_JOB_RUN
            WHERE etl_job_run_id = ?
        """, (job_run_id,))
        
        row = cursor.fetchone()
        if not row or row[0].strip() != 'PAUSED':
            conn.close()
            return 0
        
        job_id = row[1]
        resume_from_step = row[2] or 1
        
        # Status auf RUNNING setzen
        cursor.execute("""
            UPDATE MDP01_META.META_ETL_JOB_RUN
            SET status = 'RUNNING',
                control_flag = NULL
            WHERE etl_job_run_id = ?
        """, (job_run_id,))
        conn.close()
        
        logger.info(f"Resuming job_run_id={job_run_id} from step {resume_from_step}")
        
        # Job fortsetzen (async oder sync)
        # Hier könnte man auch den Job in einem Thread fortsetzen
        return self._continue_job_execution(job_run_id, job_id, resume_from_step)
    
    def _continue_job_execution(self, job_run_id: int, job_id: int, start_from_step: int) -> int:
        """
        Führt einen Job ab einem bestimmten Step fort.
        Interne Methode für Resume.
        """
        conn = self.get_connection(autocommit=False)
        
        try:
            # Steps laden (sortiert nach step_order)
            steps = self._load_steps(conn, job_id)
            
            # Nur Steps ab start_from_step ausführen
            steps_to_execute = [s for s in steps if s.step_order >= start_from_step]
            logger.info(f"Resuming with {len(steps_to_execute)} steps (starting at step_order={start_from_step})")
            
            last_step_rows = None
            has_failed_step = False
            
            for step in steps_to_execute:
                logger.info(f"-" * 80)
                logger.info(f"Executing Step {step.step_order}: {step.step_name} ({step.step_category})")
                logger.info(f"-" * 80)
                
                # Wenn ein vorheriger Step fehlgeschlagen ist, restliche Steps überspringen
                if has_failed_step:
                    logger.info(f"Skipping step {step.step_order} because previous step failed")
                    self._create_skipped_step_run(conn, job_run_id, step, skip_reason="Vorheriger Step fehlgeschlagen")
                    continue
                
                # Prüfe Control-Flag (Pause/Cancel) vor jedem Step
                control_action = self._check_control_flag(conn, job_run_id, step.step_order)
                if control_action == 'PAUSED':
                    logger.info(f"Job paused before step {step.step_order}")
                    return job_run_id
                elif control_action == 'CANCELLED':
                    logger.info(f"Job cancelled before step {step.step_order}")
                    return job_run_id
                
                # Skip-Logik
                if self._should_skip_step(step, last_step_rows):
                    logger.info(f"Skipping step (skip_on_empty=Y and last_step returned 0 rows)")
                    self._create_skipped_step_run(conn, job_run_id, step, skip_reason="Vorheriger Step lieferte 0 Zeilen")
                    continue
                
                # Step ausführen
                success, metrics = self._execute_step(conn, job_run_id, step)
                
                if not success:
                    has_failed_step = True
                    logger.error(f"Step {step.step_order} failed. Remaining steps will be skipped.")
                else:
                    last_step_rows = metrics.rows_inserted + metrics.rows_updated
                    logger.info(f"Step completed: inserted={metrics.rows_inserted}, updated={metrics.rows_updated}")
            
            # Final Status bestimmen
            if has_failed_step:
                conn.rollback()  # Rollback der Daten-Transaktion
                self._update_job_run(conn, job_run_id, status='FAILED', error_message='One or more steps failed')
                # Kein conn.commit() nötig - Log-Connection hat autocommit=True
            else:
                # Job erfolgreich → Commit der Daten-Transaktion
                conn.commit()
                self._update_job_run(conn, job_run_id, status='SUCCESS')
                # Kein conn.commit() nötig - Log-Connection hat autocommit=True
            
            return job_run_id
            
        except Exception as e:
            logger.error(f"Resumed job failed: {str(e)}")
            conn.rollback()  # Rollback der Daten-Transaktion
            
            try:
                self._update_job_run(
                    conn, job_run_id,
                    status='FAILED',
                    error_message=str(e),
                    error_stack=traceback.format_exc()
                )
                # Kein conn.commit() nötig - Log-Connection hat autocommit=True
            except:
                pass
            
            raise
            
        finally:
            conn.close()
            self._close_log_connection()  # Log-Connection auch schließen

    def _should_skip_step(self, step: ETLJobStep, last_step_rows: Optional[int]) -> bool:
        """Prüft ob Step übersprungen werden soll."""
        if step.skip_on_empty == 'Y' and last_step_rows == 0:
            return True
        return False
    
    def _create_skipped_step_run(
        self,
        conn: teradatasql.TeradataConnection,
        job_run_id: int,
        step: ETLJobStep,
        skip_reason: str = "Skipped"
    ):
        """Erstellt SKIPPED Step-Run (über Log-Connection)."""
        log_conn = self._get_log_connection()
        cursor = log_conn.cursor()
        cursor.execute("""
            INSERT INTO MDP01_META.META_ETL_JOB_STEP_RUN (
                etl_job_run_id, etl_job_step_id, start_time, end_time,
                status, was_skipped, skip_reason
            ) VALUES (?, ?, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6), 'SKIPPED', 'Y', ?)
        """, (job_run_id, step.etl_job_step_id, skip_reason))


# =============================================================================
# Utility Functions
# =============================================================================

def load_config(config_path: str) -> Dict[str, Any]:
    """Lädt Konfiguration aus YAML-Datei."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


# =============================================================================
# CLI Entry Point
# =============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Metadata-Driven ETL Orchestrator')
    parser.add_argument('--config', required=True, help='Path to database.yml')
    parser.add_argument('--job-id', type=int, required=True, help='ETL Job ID to execute')
    parser.add_argument('--mode', default='MANUAL', choices=['MANUAL', 'SCHEDULED', 'API', 'RETRY'])
    
    args = parser.parse_args()
    
    # Config laden
    config = load_config(args.config)
    
    # Orchestrator starten
    orchestrator = MetadataETLOrchestrator(config)
    job_run_id = orchestrator.execute_job(
        job_id=args.job_id,
        execution_mode=args.mode
    )
    
    print(f"\nJob completed successfully. job_run_id={job_run_id}")
