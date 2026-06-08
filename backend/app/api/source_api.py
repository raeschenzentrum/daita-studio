"""
Source System API Router
========================

REST Endpoints für Source System Management:
- GET /sources - Alle Source Systems
- GET /sources/{id} - Einzelnes Source System
- GET /sources/{id}/tables - Tabellen Discovery
- GET /sources/{id}/tables/{table}/columns - Spalten einer Tabelle
- POST /sources/tpt-jobs - TPT Job erstellen

Autor: DWH MVP Team
Datum: 2026-03-18
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from ..models.source_models import (
    SourceSystem, SourceTableList, SourceColumn,
    TPTJobCreateRequest, TPTJobCreateResponse,
    BulkTPTJobCreateRequest, BulkTPTJobCreateResponse,
    TableImportStatus
)
from ..services.source_service import SourceSystemService, get_source_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sources", tags=["Source Systems"])


# =============================================================================
# Source System Endpoints
# =============================================================================

@router.get("", response_model=List[SourceSystem])
async def list_source_systems(
    active_only: bool = Query(False, description="Nur aktive Source Systems"),
    service: SourceSystemService = Depends(get_source_service)
):
    """
    Listet alle registrierten Source Systems.
    
    Diese Endpoint zeigt alle externen Quellsysteme die für TPT Loads
    konfiguriert sind.
    """
    try:
        return service.get_all_source_systems(active_only=active_only)
    except Exception as e:
        logger.error(f"Error listing source systems: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{source_system_id}", response_model=SourceSystem)
async def get_source_system(
    source_system_id: int,
    service: SourceSystemService = Depends(get_source_service)
):
    """
    Gibt Details zu einem Source System zurück.
    """
    result = service.get_source_system(source_system_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Source System {source_system_id} not found")
    return result


# =============================================================================
# Schema & Table Discovery Endpoints
# =============================================================================

@router.get("/{source_system_id}/schemas", response_model=List[str])
async def discover_schemas(
    source_system_id: int,
    service: SourceSystemService = Depends(get_source_service)
):
    """
    Entdeckt alle Schemas in einem externen Source System.
    
    Verbindet sich via ODBC zum Quellsystem und listet alle verfügbaren
    Schemas auf.
    """
    try:
        return service.discover_schemas(source_system_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Connection failed: {e}")
    except Exception as e:
        logger.error(f"Schema discovery error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{source_system_id}/tables", response_model=SourceTableList)
async def discover_tables(
    source_system_id: int,
    schema: Optional[str] = Query(None, description="Schema-Filter (optional)"),
    service: SourceSystemService = Depends(get_source_service)
):
    """
    Entdeckt alle Tabellen in einem externen Source System.
    
    Verbindet sich via ODBC zum Quellsystem und listet alle verfügbaren
    Tabellen im angegebenen Schema oder im Default-Schema.
    """
    try:
        return service.discover_tables(source_system_id, schema_filter=schema)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Connection failed: {e}")
    except Exception as e:
        logger.error(f"Discovery error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{source_system_id}/tables/{table_name}/columns", response_model=List[SourceColumn])
async def get_table_columns(
    source_system_id: int,
    table_name: str,
    schema: Optional[str] = Query(None, description="Schema (default: default_schema)"),
    service: SourceSystemService = Depends(get_source_service)
):
    """
    Holt alle Spalten einer Tabelle aus dem externen System.
    
    Gibt Spaltennamen, Datentypen und den gemappten Teradata-Datentyp zurück.
    """
    try:
        return service.get_table_columns(source_system_id, table_name, schema)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Column discovery error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# TPT Job Creation Endpoints
# =============================================================================

@router.post("/tpt-jobs", response_model=TPTJobCreateResponse)
async def create_tpt_job(
    request: TPTJobCreateRequest,
    service: SourceSystemService = Depends(get_source_service)
):
    """
    Erstellt einen TPT Load Job.
    
    Dieser Endpoint erstellt:
    - META_ETL_JOB Eintrag
    - META_ETL_JOB_STEP mit STEP_CATEGORY='TPT_LOAD'
    - Optional: META_TABLE/META_COLUMN Einträge
    
    Der Job kann danach über /api/etl/jobs/{id}/execute ausgeführt werden.
    """
    try:
        return service.create_tpt_job(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"TPT Job creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tpt-jobs/bulk", response_model=BulkTPTJobCreateResponse)
async def create_tpt_jobs_bulk(
    request: BulkTPTJobCreateRequest,
    service: SourceSystemService = Depends(get_source_service)
):
    """
    Erstellt mehrere TPT Load Jobs auf einmal.
    
    Optimal für initiales Setup wenn viele Tabellen geladen werden sollen.
    Unterstützt optionale Column Mappings via tables_with_mappings.
    """
    results = []
    
    # Baue ein Dictionary für Tabellen mit Mappings
    mappings_dict = {}
    if request.tables_with_mappings:
        for twm in request.tables_with_mappings:
            mappings_dict[twm.table_name] = twm.column_mappings
    
    # Verarbeite alle Tabellen
    tables_to_process = request.source_tables or []
    
    # Falls tables_with_mappings, aber keine source_tables: nimm Tabellen aus mappings
    if not tables_to_process and request.tables_with_mappings:
        tables_to_process = [twm.table_name for twm in request.tables_with_mappings]
    
    for table in tables_to_process:
        try:
            # Hole Mappings falls vorhanden
            column_mappings = mappings_dict.get(table)
            
            job_request = TPTJobCreateRequest(
                source_system_id=request.source_system_id,
                source_table=table,
                target_database=request.target_database,
                tpt_operator_type=request.tpt_operator_type,
                register_in_meta_table=request.register_in_meta_table,
                column_mappings=column_mappings
            )
            result = service.create_tpt_job(job_request)
            results.append(result)
        except Exception as e:
            logger.error(f"Error creating job for {table}: {e}")
            results.append(TPTJobCreateResponse(
                success=False,
                message=str(e)
            ))
    
    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful
    
    return BulkTPTJobCreateResponse(
        total_requested=len(tables_to_process),
        successful=successful,
        failed=failed,
        results=results
    )


# =============================================================================
# Import Status Endpoints
# =============================================================================

@router.post("/{source_system_id}/import-status", response_model=List[TableImportStatus])
async def get_import_status(
    source_system_id: int,
    tables: List[str],
    service: SourceSystemService = Depends(get_source_service)
):
    """
    Gibt Import-Status für mehrere Tabellen zurück.
    
    Zeigt für jede Tabelle:
    - Ob ein TPT Job existiert
    - Letzter Load-Status (COMPLETED, FAILED, etc.)
    - Zeitpunkt des letzten Loads
    """
    try:
        return service.get_table_import_status(source_system_id, tables)
    except Exception as e:
        logger.error(f"Status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
