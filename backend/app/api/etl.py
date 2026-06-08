"""
ETL API Router
==============

REST API Endpoints für ETL Orchestrator Dashboard.
Getrennt vom Lineage API - modulare Struktur.

Autor: DWH MVP Team
Datum: 2026-01-19
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import logging

from ..models.etl_models import (
    ETLJob, ETLJobWithDetails, ETLJobStep, ETLJobRun,
    ETLJobRunWithSteps, ExecuteJobRequest, ExecuteJobResponse,
    JobRunHistoryRequest, JobPerformanceStats, DashboardStats
)
from ..services.etl_service import ETLService, get_etl_service
from ..services.metadata_sync_service import MetadataSyncService, create_metadata_sync_service

# Dependency für MetadataSyncService
_metadata_sync_service = None

def get_metadata_sync_service() -> MetadataSyncService:
    global _metadata_sync_service
    if _metadata_sync_service is None:
        _metadata_sync_service = create_metadata_sync_service()
    return _metadata_sync_service

logger = logging.getLogger(__name__)

# Router
router = APIRouter(
    prefix="/api/etl",
    tags=["ETL Orchestrator"],
    responses={404: {"description": "Not found"}}
)


# =============================================================================
# Jobs Endpoints
# =============================================================================

@router.get("/jobs", response_model=List[ETLJobWithDetails])
async def get_jobs(
    active_only: bool = False,
    layer_id: Optional[int] = None,
    etl_service: ETLService = Depends(get_etl_service)
):
    """
    Gibt alle ETL Jobs zurück mit Details.

    Query Parameters:
    - active_only: Nur aktive Jobs (is_active='Y')
    - layer_id: Nur Jobs die source_layer_id oder target_layer_id diesem Layer haben
    """
    try:
        return etl_service.get_all_jobs(active_only=active_only, layer_id=layer_id)
    except Exception as e:
        logger.error(f"Error fetching jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}", response_model=ETLJobWithDetails)
async def get_job(
    job_id: int,
    etl_service: ETLService = Depends(get_etl_service)
):
    """Gibt einen spezifischen Job zurück (inkl. Tabellennamen, Layer, Step-Count)"""
    try:
        job = etl_service.get_job_by_id(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return job
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}/mapping")
async def get_job_mapping(
    job_id: int,
    etl_service: ETLService = Depends(get_etl_service)
):
    """Gibt Source/Target Tabellen mit Spalten für Mapping zurück"""
    try:
        mapping = etl_service.get_job_mapping_info(job_id)
        if not mapping:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return mapping
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching mapping for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}/steps", response_model=List[ETLJobStep])
async def get_job_steps(
    job_id: int,
    etl_service: ETLService = Depends(get_etl_service)
):
    """Gibt alle Steps für einen Job zurück"""
    try:
        return etl_service.get_job_steps(job_id)
    except Exception as e:
        logger.error(f"Error fetching steps for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}/sql-export", response_class=PlainTextResponse)
async def export_job_sql(
    job_id: int,
    etl_service: ETLService = Depends(get_etl_service)
):
    """Rendert alle aktiven Steps eines Jobs und gibt eine SQL-Datei zurück"""
    from ..services.template_engine import SQLTemplateEngine

    job = etl_service.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} nicht gefunden")

    steps = etl_service.get_job_steps(job_id)
    active_steps = [s for s in steps if s.is_active.strip() == 'Y']
    active_steps.sort(key=lambda s: s.step_order)

    engine = SQLTemplateEngine(TEMPLATE_BASE_DIR)
    parts = []

    for step in active_steps:
        header = (
            f"-- {'=' * 68}\n"
            f"-- Step {step.step_order}: {step.step_name}\n"
            f"-- Category: {step.step_category}\n"
        )
        if step.sql_template_path:
            header += f"-- Template: {step.sql_template_path}\n"
        header += f"-- {'=' * 68}"

        try:
            params = json.loads(step.parameters) if isinstance(step.parameters, str) else (step.parameters or {})
            if step.sql_template_path:
                rendered = engine.render(step.sql_template_path, params)
            elif step.sql_inline:
                rendered = step.sql_inline
            else:
                rendered = "-- (kein SQL)"
        except Exception as e:
            rendered = f"-- RENDER ERROR: {e}"

        parts.append(f"{header}\n{rendered}")

    sql_content = "\n\n".join(parts)
    job_name_safe = (job.job_name or f"job_{job_id}").replace(" ", "_")
    filename = f"job_{job_id}_{job_name_safe}.sql"

    return PlainTextResponse(
        content=sql_content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


class TPTPreviewResponse(BaseModel):
    """Response für TPT Script Preview"""
    job_id: int
    job_name: str
    tpt_script: str
    message: str


@router.get("/jobs/{job_id}/tpt-preview", response_model=TPTPreviewResponse)
async def get_tpt_preview(
    job_id: int,
    etl_service: ETLService = Depends(get_etl_service)
):
    """
    Generiert TPT Script Vorschau für einen Job.
    
    Zeigt das TPT Script das generiert werden würde, ohne es zu speichern.
    """
    try:
        result = etl_service.generate_tpt_preview(job_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found or has no TPT_LOAD step")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating TPT preview for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: int,
    delete_tables: bool = False,
    etl_service: ETLService = Depends(get_etl_service)
):
    """
    Löscht einen ETL Job und alle zugehörigen Daten.
    
    Query Parameters:
    - delete_tables: Auch Staging/Error Tables in Teradata löschen (default: false)
    """
    try:
        result = etl_service.delete_job(job_id, delete_tables=delete_tables)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Table Column Metadata Sync
# =============================================================================

@router.get("/tables/{table_id}/columns/diff")
async def get_column_diff(
    table_id: int,
    etl_service: ETLService = Depends(get_etl_service)
):
    """Vergleicht META_COLUMN mit dbc.columnsV und zeigt Unterschiede"""
    try:
        diff = etl_service.compare_table_columns(table_id)
        if "error" in diff:
            raise HTTPException(status_code=404, detail=diff["error"])
        return diff
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing columns for table {table_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tables/{table_id}/columns/sync")
async def sync_table_columns(
    table_id: int,
    etl_service: ETLService = Depends(get_etl_service)
):
    """Synchronisiert META_COLUMN mit dbc.columnsV"""
    try:
        result = etl_service.sync_table_columns(table_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return {
            "success": True,
            "message": f"Sync abgeschlossen: {result['inserted']} eingefügt, {result['updated']} aktualisiert, {result['deleted']} gelöscht",
            "details": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing columns for table {table_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Metadata Explorer: Layers, Databases, Tables
# =============================================================================

@router.get("/layers")
async def get_layers(
    etl_service: ETLService = Depends(get_etl_service)
):
    """Gibt alle Layer mit Datenbank-Anzahl zurück"""
    try:
        return etl_service.get_all_layers()
    except Exception as e:
        logger.error(f"Error fetching layers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases")
async def get_databases(
    layer_id: Optional[int] = None,
    etl_service: ETLService = Depends(get_etl_service)
):
    """Gibt alle Databases zurück, optional gefiltert nach Layer"""
    try:
        return etl_service.get_databases_by_layer(layer_id)
    except Exception as e:
        logger.error(f"Error fetching databases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases/{database_id}/tables")
async def get_tables(
    database_id: int,
    etl_service: ETLService = Depends(get_etl_service)
):
    """Gibt alle Tabellen einer Database zurück"""
    try:
        return etl_service.get_tables_by_database(database_id)
    except Exception as e:
        logger.error(f"Error fetching tables for database {database_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables/{table_id}/columns")
async def get_table_columns(
    table_id: int,
    etl_service: ETLService = Depends(get_etl_service)
):
    """Gibt alle Spalten einer Tabelle zurück"""
    try:
        return etl_service.get_table_columns(table_id)
    except Exception as e:
        logger.error(f"Error fetching columns for table {table_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases/{database_id}/dbc-tables")
async def get_dbc_tables(
    database_id: int,
    etl_service: ETLService = Depends(get_etl_service)
):
    """Gibt alle Tabellen aus dbc.tablesV für Import zurück"""
    try:
        # Hole Database-Name
        databases = etl_service.get_databases_by_layer()
        db = next((d for d in databases if d["database_id"] == database_id), None)
        if not db:
            raise HTTPException(status_code=404, detail=f"Database {database_id} nicht gefunden")
        
        return etl_service.get_dbc_tables(db["database_name"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching dbc tables for database {database_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ImportTableRequest(BaseModel):
    table_name: str

@router.post("/databases/{database_id}/import-table")
async def import_table(
    database_id: int,
    request: ImportTableRequest,
    sync_service: MetadataSyncService = Depends(get_metadata_sync_service)
):
    """Importiert eine Tabelle aus dbc in META_TABLE/META_COLUMN"""
    try:
        result = sync_service.import_table_from_dbc(database_id, request.table_name)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing table {request.table_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tables/{table_id}")
async def delete_table(
    table_id: int,
    etl_service: ETLService = Depends(get_etl_service)
):
    """Löscht eine Tabelle (META_TABLE + META_COLUMN) aus den Metadaten"""
    try:
        result = etl_service.delete_table(table_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting table {table_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tables/{table_id}/sync-columns")
async def sync_table_columns(
    table_id: int,
    sync_service: MetadataSyncService = Depends(get_metadata_sync_service)
):
    """Synchronisiert Spalten einer Tabelle mit dbc"""
    try:
        result = sync_service.sync_columns_from_dbc(table_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing table {table_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tables/{table_id}/compare")
async def compare_table_with_dbc(
    table_id: int,
    sync_service: MetadataSyncService = Depends(get_metadata_sync_service)
):
    """Vergleicht META_COLUMN mit dbc ohne Änderungen"""
    try:
        result = sync_service.compare_meta_with_dbc(table_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing table {table_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Step Parameter Update
# =============================================================================

class StepParameterUpdateRequest(BaseModel):
    parameters: dict

@router.put("/steps/{step_id}/parameters")
async def update_step_parameters(
    step_id: int,
    request: StepParameterUpdateRequest,
    etl_service: ETLService = Depends(get_etl_service)
):
    """Aktualisiert die Parameter eines ETL Job Steps"""
    try:
        import json
        params_json = json.dumps(request.parameters)
        etl_service.update_step_parameters(step_id, params_json)
        return {"success": True, "message": "Parameter erfolgreich aktualisiert"}
    except Exception as e:
        logger.error(f"Error updating parameters for step {step_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Job Execution Endpoints
# =============================================================================

async def _execute_job_background(job_id: int, etl_service: ETLService, initial_load_mode: bool = False):
    """Background Task für Job Execution"""
    try:
        logger.info(f"Starting background execution of job {job_id} (initial_load_mode={initial_load_mode})")
        job_run_id = etl_service.execute_job(job_id, initial_load_mode=initial_load_mode)
        logger.info(f"Job {job_id} completed with run_id {job_run_id}")
    except Exception as e:
        logger.error(f"Background job {job_id} failed: {e}")


@router.post("/jobs/{job_id}/execute", response_model=ExecuteJobResponse)
async def execute_job(
    job_id: int,
    request: ExecuteJobRequest,
    background_tasks: BackgroundTasks,
    etl_service: ETLService = Depends(get_etl_service)
):
    """
    Führt einen ETL Job aus (asynchron im Hintergrund).
    
    Die Job-Ausführung läuft im Background. Status kann über
    /api/etl/runs/{job_run_id} abgefragt werden.
    """
    try:
        # Job existiert?
        job = etl_service.get_job_by_id(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        if job.is_active.strip() != 'Y':
            raise HTTPException(status_code=400, detail=f"Job {job_id} is not active")
        
        # Background Task starten
        background_tasks.add_task(_execute_job_background, job_id, etl_service, request.initial_load_mode)
        
        mode_info = " (Initial Load Mode - Target wird gelöscht)" if request.initial_load_mode else ""
        return ExecuteJobResponse(
            etl_job_run_id=0,  # Wird im Background erstellt
            status="STARTED",
            message=f"Job {job.job_name} execution started in background{mode_info}"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Job Runs Endpoints
# =============================================================================

@router.get("/runs", response_model=List[ETLJobRun])
async def get_job_runs(
    job_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    etl_service: ETLService = Depends(get_etl_service)
):
    """
    Gibt Job Run History zurück.
    
    Query Parameters:
    - job_id: Filter nach Job ID (optional)
    - status: Filter nach Status (RUNNING, SUCCESS, FAILED) (optional)
    - limit: Max. Anzahl Ergebnisse (default: 50)
    - offset: Offset für Pagination (default: 0)
    """
    try:
        return etl_service.get_job_runs(
            job_id=job_id,
            status=status,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error(f"Error fetching job runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{job_run_id}", response_model=ETLJobRunWithSteps)
async def get_job_run_details(
    job_run_id: int,
    etl_service: ETLService = Depends(get_etl_service)
):
    """Gibt Job Run Details mit Step-Informationen zurück"""
    try:
        run = etl_service.get_job_run_details(job_run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Job run {job_run_id} not found")
        return run
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching job run {job_run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Statistics & Monitoring Endpoints
# =============================================================================

@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    etl_service: ETLService = Depends(get_etl_service)
):
    """Gibt Dashboard Übersichts-Statistiken zurück"""
    try:
        return etl_service.get_dashboard_stats()
    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/maintenance/cleanup-stale-runs")
async def cleanup_stale_runs(
    hours_threshold: int = 2,
    etl_service: ETLService = Depends(get_etl_service)
):
    """
    Markiert "hängende" RUNNING Jobs als FAILED.
    
    Jobs die länger als hours_threshold Stunden im Status RUNNING sind,
    werden als FAILED markiert (vermutlich abgebrochen ohne Cleanup).
    """
    try:
        count = etl_service.cleanup_stale_running_jobs(hours_threshold)
        return {"message": f"{count} stale runs cleaned up", "cleaned_up": count}
    except Exception as e:
        logger.error(f"Error cleaning up stale runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Job Run Control Endpoints (Pause/Resume/Cancel)
# =============================================================================

@router.post("/runs/{job_run_id}/pause")
async def pause_job_run(
    job_run_id: int,
    etl_service: ETLService = Depends(get_etl_service)
):
    """
    Pausiert einen laufenden Job nach dem aktuellen Step.
    
    Der Job wird nicht sofort gestoppt, sondern erst nach Abschluss
    des aktuell laufenden Steps.
    """
    try:
        success = etl_service.pause_job_run(job_run_id)
        if success:
            return {"message": "Pause angefordert", "job_run_id": job_run_id, "status": "PAUSE_REQUESTED"}
        else:
            raise HTTPException(status_code=400, detail="Job ist nicht im Status RUNNING")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing job run {job_run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{job_run_id}/resume")
async def resume_job_run(
    job_run_id: int,
    background_tasks: BackgroundTasks,
    etl_service: ETLService = Depends(get_etl_service)
):
    """
    Setzt einen pausierten Job fort.
    
    Der Job wird ab dem nächsten ausstehenden Step fortgesetzt.
    """
    try:
        # Prüfe ob Job PAUSED ist
        run_info = etl_service.get_job_run_details(job_run_id)
        if not run_info:
            raise HTTPException(status_code=404, detail="Job Run nicht gefunden")
        
        if run_info.status.strip() != 'PAUSED':
            raise HTTPException(status_code=400, detail=f"Job ist nicht pausiert (Status: {run_info.status})")
        
        # Resume in Background ausführen
        background_tasks.add_task(etl_service.resume_job_run, job_run_id)
        
        return {"message": "Job wird fortgesetzt", "job_run_id": job_run_id, "status": "RESUMING"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming job run {job_run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{job_run_id}/cancel")
async def cancel_job_run(
    job_run_id: int,
    etl_service: ETLService = Depends(get_etl_service)
):
    """
    Bricht einen laufenden oder pausierten Job ab.
    
    Bei RUNNING: Abbruch nach dem aktuellen Step
    Bei PAUSED: Sofortiger Abbruch
    """
    try:
        success = etl_service.cancel_job_run(job_run_id)
        if success:
            return {"message": "Job abgebrochen", "job_run_id": job_run_id, "status": "CANCELLED"}
        else:
            raise HTTPException(status_code=400, detail="Job kann nicht abgebrochen werden (nur RUNNING oder PAUSED)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job run {job_run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance", response_model=List[JobPerformanceStats])
async def get_job_performance(
    job_id: Optional[int] = None,
    etl_service: ETLService = Depends(get_etl_service)
):
    """
    Gibt Performance-Statistiken zurück.
    
    Query Parameters:
    - job_id: Filter nach Job ID (optional, sonst alle Jobs)
    """
    try:
        return etl_service.get_job_performance(job_id=job_id)
    except Exception as e:
        logger.error(f"Error fetching performance stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Template Endpoints
# =============================================================================

import os

TEMPLATE_BASE_DIR = "/home/tdops/ps_toolbox/PS_ROOT/subsystem/metadaita/ddl/sql_templates"

class TemplateContent(BaseModel):
    path: str
    content: str
    exists: bool = True

class TemplateUpdateRequest(BaseModel):
    content: str

@router.get("/templates/{template_path:path}", response_model=TemplateContent)
async def get_template(template_path: str):
    """Liest den Inhalt eines SQL Templates"""
    # Sicherheitscheck: Nur innerhalb des Template-Verzeichnisses
    full_path = os.path.normpath(os.path.join(TEMPLATE_BASE_DIR, template_path))
    if not full_path.startswith(TEMPLATE_BASE_DIR):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    
    if not os.path.exists(full_path):
        return TemplateContent(path=template_path, content="", exists=False)
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return TemplateContent(path=template_path, content=content, exists=True)
    except Exception as e:
        logger.error(f"Error reading template {template_path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/templates/{template_path:path}", response_model=TemplateContent)
async def update_template(template_path: str, request: TemplateUpdateRequest):
    """Speichert den Inhalt eines SQL Templates"""
    # Sicherheitscheck: Nur innerhalb des Template-Verzeichnisses
    full_path = os.path.normpath(os.path.join(TEMPLATE_BASE_DIR, template_path))
    if not full_path.startswith(TEMPLATE_BASE_DIR):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    
    try:
        # Erstelle Verzeichnis falls nötig
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(request.content)
        
        logger.info(f"Template updated: {template_path}")
        return TemplateContent(path=template_path, content=request.content, exists=True)
    except Exception as e:
        logger.error(f"Error writing template {template_path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates", response_model=List[str])
async def list_templates():
    """Listet alle verfügbaren SQL Templates auf"""
    templates = []
    for root, dirs, files in os.walk(TEMPLATE_BASE_DIR):
        for file in files:
            if file.endswith('.sql'):
                rel_path = os.path.relpath(os.path.join(root, file), TEMPLATE_BASE_DIR)
                templates.append(rel_path)
    return sorted(templates)


class RenderTemplateRequest(BaseModel):
    parameters: dict = {}

class RenderedTemplateResponse(BaseModel):
    path: str
    rendered_sql: str
    parameters_used: dict
    missing_parameters: List[str] = []
    success: bool = True
    error: Optional[str] = None

@router.post("/templates/{template_path:path}/render", response_model=RenderedTemplateResponse)
async def render_template(template_path: str, request: RenderTemplateRequest):
    """Rendert ein SQL Template mit eingesetzten Parametern"""
    import re
    from ..services.template_engine import SQLTemplateEngine

    full_path = os.path.join(TEMPLATE_BASE_DIR, template_path)
    if not os.path.exists(full_path):
        return RenderedTemplateResponse(
            path=template_path,
            rendered_sql="",
            parameters_used=request.parameters,
            success=False,
            error=f"Template nicht gefunden: {template_path}"
        )

    # Parameter vorbereiten - SOURCE_TABLE mapping
    params_for_engine = dict(request.parameters)
    params_lower = {k.lower(): v for k, v in request.parameters.items()}

    # SOURCE_TABLE: Verschiedene mögliche Quellen
    if 'SOURCE_TABLE' not in params_for_engine:
        for source_key in ['staging_table', 'new_records_table', 'changed_records_table']:
            if source_key in params_lower:
                params_for_engine['SOURCE_TABLE'] = params_lower[source_key]
                break

    try:
        engine = SQLTemplateEngine(TEMPLATE_BASE_DIR)
        rendered_sql = engine.render(template_path, params_for_engine)

        # Prüfe ob noch Platzhalter übrig sind (nur in nicht-Kommentar Zeilen)
        remaining_in_code = set()
        for line in rendered_sql.split('\n'):
            if not line.strip().startswith('--'):
                for match in re.findall(r'\$\{([A-Z_][A-Z0-9_]*)\}', line):
                    remaining_in_code.add(match)

        return RenderedTemplateResponse(
            path=template_path,
            rendered_sql=rendered_sql,
            parameters_used=params_for_engine,
            missing_parameters=list(remaining_in_code),
            success=len(remaining_in_code) == 0
        )
    except Exception as e:
        return RenderedTemplateResponse(
            path=template_path,
            rendered_sql="",
            parameters_used=params_for_engine,
            missing_parameters=[],
            success=False,
            error=str(e)
        )
