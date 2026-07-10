"""
Jobs API Router
===============

REST API Endpoints für Job-Management (CRUD).
Getrennt von ETL-Execution und Templates.

Autor: metadaita Team
Datum: 2026-04-15
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
import logging
import shutil
from pathlib import Path

from ..services.job_management import (
    JobManagementService, 
    get_job_management_service,
    TableWithLoadStatus,
    ColumnMapping,
    CreateJobRequest,
    CreateStepRequest,
    UpdateStepRequest,
)
from ..services.etl_service import ETLService, get_etl_service
from ..models.etl_models import ETLJobWithDetails
from ..config import PATHS

logger = logging.getLogger(__name__)


# Router
router = APIRouter(
    prefix="/api",
    tags=["Job Management"],
    responses={404: {"description": "Not found"}}
)


# =============================================================================
# Layer-Tabellen Endpoints (AF-001)
# =============================================================================

@router.get("/layers/{layer_id}/tables", response_model=List[TableWithLoadStatus])
async def get_tables_with_load_status(
    layer_id: int,
    service: JobManagementService = Depends(get_job_management_service)
):
    """
    Gibt alle Tabellen eines Layers zurück mit Info ob Job existiert.
    
    - **layer_id**: 1=SOURCE, 2=RAW, 3=DISC, 4=REUS, 5=CONS
    
    Für jeden Eintrag:
    - has_job: true wenn ein ETL-Job diese Tabelle als Target hat
    - job_id, job_name, job_status: Info zum Job falls vorhanden
    """
    try:
        return service.get_tables_with_load_status(layer_id)
    except Exception as e:
        logger.error(f"Error getting tables for layer {layer_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Layer-Transition Endpoints (AF-005)
# =============================================================================

@router.get("/layers/{source_layer_id}/to/{target_layer_id}/jobs", response_model=List[ETLJobWithDetails])
async def get_jobs_by_transition(
    source_layer_id: int,
    target_layer_id: int,
    service: JobManagementService = Depends(get_job_management_service)
):
    """
    Gibt alle Jobs zurück die von einem Layer zum anderen gehen.
    
    Beispiel: `/api/layers/2/to/3/jobs` für alle RAW→DISC Jobs
    """
    try:
        return service.get_jobs_by_transition(source_layer_id, target_layer_id)
    except Exception as e:
        logger.error(f"Error getting jobs for transition {source_layer_id}→{target_layer_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Job CRUD Endpoints
# =============================================================================

@router.post("/jobs", response_model=dict)
async def create_job(
    request: CreateJobRequest,
    service: JobManagementService = Depends(get_job_management_service)
):
    """
    Erstellt einen neuen ETL Job (ohne Steps).
    
    Steps müssen separat hinzugefügt werden via POST /api/jobs/{job_id}/steps
    """
    try:
        job_id = service.create_job(request)
        return {"job_id": job_id, "message": f"Job '{request.job_name}' created"}
    except Exception as e:
        logger.error(f"Error creating job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/jobs/{job_id}", response_model=dict)
async def update_job(
    job_id: int,
    job_name: Optional[str] = None,
    is_active: Optional[str] = None,
    service: JobManagementService = Depends(get_job_management_service)
):
    """Aktualisiert einen Job"""
    try:
        success = service.update_job(job_id, job_name=job_name, is_active=is_active)
        if success:
            return {"message": f"Job {job_id} updated"}
        return {"message": "No changes"}
    except Exception as e:
        logger.error(f"Error updating job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}/delete-preview", response_model=dict)
async def delete_preview(
    job_id: int,
    service: JobManagementService = Depends(get_job_management_service),
    etl_service: ETLService = Depends(get_etl_service),
):
    """
    F5-B1: Gibt alle Objekte zurück die beim Löschen betroffen wären.
    """
    try:
        job = etl_service.get_job_by_id(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} nicht gefunden")

        steps = etl_service.get_job_steps(job_id)
        job_dir = Path(PATHS["etl_jobs"]) / str(job_id)

        def read_cleanup(filename: str) -> Optional[str]:
            p = job_dir / "cleanup" / filename
            return p.read_text(encoding="utf-8") if p.exists() else None

        params_combined = {}
        for step in steps:
            if step.parameters:
                params_combined.update(step.parameters)

        target_table   = params_combined.get("TARGET_TABLE")
        target_database = params_combined.get("TARGET_DATABASE")
        sk_table       = params_combined.get("KEY_TABLE")
        sk_database    = params_combined.get("KEY_DATABASE")

        objects = [
            {
                "key": "job",
                "label": "ETL-Job",
                "value": job.job_name,
                "required": True,
                "default_selected": True,
            },
            {
                "key": "steps",
                "label": f"Job-Steps ({len(steps)})",
                "value": "Alle Steps + Parameter-JSONs",
                "required": True,
                "default_selected": True,
            },
            {
                "key": "drop_job_folder",
                "label": "Job-Folder",
                "value": str(job_dir) if job_dir.exists() else "Kein Folder vorhanden",
                "required": False,
                "default_selected": True,
                "exists": job_dir.exists(),
            },
            {
                "key": "drop_target_table",
                "label": "Zieltabelle (Datenbank)",
                "value": f"{target_database}.{target_table}" if target_table else "Nicht ermittelbar",
                "required": False,
                "default_selected": False,
                "sql_preview": read_cleanup("drop_target_table.sql"),
            },
            {
                "key": "drop_sk_table",
                "label": "SK-Tabelle (Datenbank)",
                "value": f"{sk_database}.{sk_table}" if sk_table else "Nicht ermittelbar",
                "required": False,
                "default_selected": False,
                "sql_preview": read_cleanup("drop_sk_table.sql"),
            },
            {
                "key": "drop_meta_table",
                "label": "META_TABLE Eintrag",
                "value": target_table or "Nicht ermittelbar",
                "required": False,
                "default_selected": False,
                "sql_preview": (
                    f"DELETE FROM MDP01_META.META_TABLE\nWHERE TABLE_ID = {job.target_table_id};"  # per ID, nicht Name!
                ) if job.target_table_id else None,
            },
            {
                "key": "drop_meta_columns",
                "label": "META_COLUMN Einträge",
                "value": f"Alle Spalten von {target_table}" if target_table else "Nicht ermittelbar",
                "required": False,
                "default_selected": False,
                "sql_preview": (
                    f"DELETE FROM MDP01_META.META_COLUMN\nWHERE TABLE_ID = {job.target_table_id};"
                ) if job.target_table_id else None,
            },
        ]

        return {"job_id": job_id, "job_name": job.job_name, "objects": objects}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in delete-preview for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class DeleteJobRequest(BaseModel):
    drop_job_folder: bool = True
    drop_target_table: bool = False
    drop_sk_table: bool = False
    drop_meta_table: bool = False
    drop_meta_columns: bool = False


@router.delete("/jobs/{job_id}", response_model=dict)
async def delete_job(
    job_id: int,
    request: Optional[DeleteJobRequest] = None,
    service: JobManagementService = Depends(get_job_management_service),
    etl_service: ETLService = Depends(get_etl_service),
):
    """
    F5-B2: Löscht einen Job mit allen Steps.
    Optional: Datenbankobjekte + META-Einträge mitlöschen.
    """
    try:
        opts = request or DeleteJobRequest()

        # Job-Folder löschen (optional, default True)
        job_dir = Path(PATHS["etl_jobs"]) / str(job_id)
        if opts.drop_job_folder and job_dir.exists():
            shutil.rmtree(job_dir)
            logger.info(f"Job-Folder gelöscht: {job_dir}")

        # Datenbank-Objekte optional
        if opts.drop_target_table or opts.drop_sk_table or opts.drop_meta_table or opts.drop_meta_columns:
            steps = etl_service.get_job_steps(job_id)
            params_combined = {}
            for step in steps:
                if step.parameters:
                    params_combined.update(step.parameters)

            conn = service._get_connection()
            cursor = conn.cursor()
            try:
                if opts.drop_target_table:
                    tgt = params_combined.get("TARGET_TABLE")
                    tgt_db = params_combined.get("TARGET_DATABASE")
                    if tgt and tgt_db:
                        try:
                            cursor.execute(f"DROP TABLE {tgt_db}.{tgt}")
                            conn.commit()
                            logger.info(f"Zieltabelle {tgt_db}.{tgt} gelöscht")
                        except Exception as e:
                            logger.warning(f"Zieltabelle löschen fehlgeschlagen: {e}")

                if opts.drop_sk_table:
                    sk = params_combined.get("KEY_TABLE")
                    sk_db = params_combined.get("KEY_DATABASE")
                    if sk and sk_db:
                        try:
                            cursor.execute(f"DROP TABLE {sk_db}.{sk}")
                            conn.commit()
                            logger.info(f"SK-Tabelle {sk_db}.{sk} gelöscht")
                        except Exception as e:
                            logger.warning(f"SK-Tabelle löschen fehlgeschlagen: {e}")

                if opts.drop_meta_table or opts.drop_meta_columns:
                    # TARGET_TABLE_ID direkt aus META_ETL_JOB holen – NICHT per Namen suchen!
                    # (Name-Suche würde Source+Target mit gleichem Namen beide treffen)
                    try:
                        cursor.execute(
                            "SELECT TARGET_TABLE_ID FROM MDP01_META.META_ETL_JOB WHERE ETL_JOB_ID = ?",
                            [job_id]
                        )
                        id_row = cursor.fetchone()
                        tbl_id = id_row[0] if id_row else None
                        if tbl_id:
                            if opts.drop_meta_columns:
                                cursor.execute(
                                    "DELETE FROM MDP01_META.META_COLUMN WHERE TABLE_ID = ?", [tbl_id]
                                )
                            if opts.drop_meta_table:
                                cursor.execute(
                                    "DELETE FROM MDP01_META.META_TABLE WHERE TABLE_ID = ?", [tbl_id]
                                )
                            conn.commit()
                            logger.info(f"META-Einträge für TABLE_ID={tbl_id} (Job {job_id}) gelöscht")
                    except Exception as e:
                        logger.warning(f"META-Einträge löschen fehlgeschlagen: {e}")
            finally:
                cursor.close()
                conn.close()

        # Job + Steps aus META löschen (immer)
        service.delete_job(job_id)
        return {"message": f"Job {job_id} gelöscht"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Step CRUD Endpoints
# =============================================================================

@router.post("/jobs/{job_id}/steps", response_model=dict)
async def add_step(
    job_id: int,
    request: CreateStepRequest,
    service: JobManagementService = Depends(get_job_management_service)
):
    """Fügt einen neuen Step zu einem Job hinzu"""
    try:
        step_id = service.add_step(job_id, request)
        return {"step_id": step_id, "message": f"Step '{request.step_name}' added to job {job_id}"}
    except Exception as e:
        logger.error(f"Error adding step to job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/jobs/{job_id}/steps/{step_id}", response_model=dict)
async def update_step(
    job_id: int,
    step_id: int,
    request: UpdateStepRequest,
    service: JobManagementService = Depends(get_job_management_service)
):
    """Aktualisiert einen Step (Einstellungen + Parameter als JSON-Body)"""
    try:
        success = service.update_step(step_id, request)
        if success:
            return {"message": f"Step {step_id} updated"}
        return {"message": "No changes"}
    except Exception as e:
        logger.error(f"Error updating step {step_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/jobs/{job_id}/steps/{step_id}", response_model=dict)
async def delete_step(
    job_id: int,
    step_id: int,
    service: JobManagementService = Depends(get_job_management_service)
):
    """Löscht einen Step"""
    try:
        service.delete_step(step_id)
        return {"message": f"Step {step_id} deleted"}
    except Exception as e:
        logger.error(f"Error deleting step {step_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Step Mapping Endpoint (AF-002)
# =============================================================================

@router.put("/jobs/{job_id}/steps/{step_id}/mapping", response_model=dict)
async def update_step_mapping(
    job_id: int,
    step_id: int,
    column_mappings: List[ColumnMapping],
    service: JobManagementService = Depends(get_job_management_service)
):
    """
    Aktualisiert das Spalten-Mapping eines Steps.
    
    Body-Beispiel:
    ```json
    [
        {
            "source_column": "ID",
            "target_column": "PERSON_ID",
            "transformation": null
        },
        {
            "source_column": "NAME",
            "target_column": "FULL_NAME",
            "transformation": "TRIM(NAME)"
        }
    ]
    ```
    """
    try:
        success = service.update_step_mapping(step_id, column_mappings)
        if success:
            return {"message": f"Mapping for step {step_id} updated with {len(column_mappings)} columns"}
        raise HTTPException(status_code=404, detail=f"Step {step_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating mapping for step {step_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# F4-C: Parameter-Migration
# =============================================================================

@router.post("/jobs/migrate-params-to-files", response_model=dict)
async def migrate_params_to_files(
    etl_service: ETLService = Depends(get_etl_service),
):
    """
    F4-C: Migriert alle DB-gespeicherten Step-Parameter in JSON-Dateien.
    Schreibt für jeden Step mit vorhandenen DB-Parametern eine
    etl/jobs/{job_id}/{step_id}.json falls diese noch nicht existiert.

    Idempotent: Überschreibt keine bereits vorhandenen Datei-Parameter.
    """
    import json as _json
    from ..config import PATHS
    from ..services.template_engine import write_step_parameters

    conn = etl_service._get_connection()
    cursor = conn.cursor()

    written = 0
    skipped = 0
    errors = []

    try:
        cursor.execute("""
            SELECT etl_job_step_id, etl_job_id, parameters
            FROM MDP01_META.META_ETL_JOB_STEP
            WHERE parameters IS NOT NULL
        """)
        rows = cursor.fetchall()
    finally:
        conn.close()

    etl_jobs_path = PATHS["etl_jobs"]

    for step_id, job_id, db_params in rows:
        json_file = etl_jobs_path / str(job_id) / f"{step_id}.json"
        if json_file.exists():
            skipped += 1
            continue
        try:
            params = _json.loads(db_params) if isinstance(db_params, str) else db_params
            write_step_parameters(int(job_id), int(step_id), params, etl_jobs_path)
            written += 1
        except Exception as e:
            errors.append(f"step {step_id}: {e}")

    return {
        "written": written,
        "skipped": skipped,
        "errors": errors,
        "message": f"{written} Dateien geschrieben, {skipped} bereits vorhanden, {len(errors)} Fehler"
    }
