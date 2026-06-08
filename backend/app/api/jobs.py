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
import logging

from ..services.job_management import (
    JobManagementService, 
    get_job_management_service,
    TableWithLoadStatus,
    ColumnMapping,
    CreateJobRequest,
    CreateStepRequest
)
from ..models.etl_models import ETLJobWithDetails

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


@router.delete("/jobs/{job_id}", response_model=dict)
async def delete_job(
    job_id: int,
    service: JobManagementService = Depends(get_job_management_service)
):
    """
    Löscht einen Job mit allen Steps und Runs.
    
    ⚠️ ACHTUNG: Löscht auch die komplette Run-History!
    """
    try:
        service.delete_job(job_id)
        return {"message": f"Job {job_id} deleted"}
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
    step_name: Optional[str] = None,
    step_order: Optional[int] = None,
    sql_template_path: Optional[str] = None,
    sql_inline: Optional[str] = None,
    is_active: Optional[str] = None,
    service: JobManagementService = Depends(get_job_management_service)
):
    """Aktualisiert einen Step"""
    try:
        success = service.update_step(
            step_id,
            step_name=step_name,
            step_order=step_order,
            sql_template_path=sql_template_path,
            sql_inline=sql_inline,
            is_active=is_active
        )
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
