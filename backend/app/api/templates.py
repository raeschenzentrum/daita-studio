"""
Templates API Endpoints
=======================

REST API für Job- und Step-Templates.

Autor: metadaita Team
Datum: 2026-04-15
"""
import io
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import Response

from ..services.template_service import (
    TemplateService,
    JobTemplate,
    StepTemplate,
    CreateJobTemplateRequest,
    CreateStepTemplateRequest,
    CreateJobFromTemplateRequest
)

router = APIRouter(prefix="/api/templates", tags=["Templates"])

# Service-Instanz
_service = TemplateService()


# =============================================================================
# Job Templates
# =============================================================================

@router.get("/jobs", response_model=List[JobTemplate])
async def get_job_templates(
    source_layer_id: Optional[int] = Query(None, description="Filter: Source Layer"),
    target_layer_id: Optional[int] = Query(None, description="Filter: Target Layer"),
    job_type: Optional[str] = Query(None, description="Filter: Job-Typ")
):
    """
    Liste aller Job-Templates.
    
    Optional filtern nach Layer-Übergang oder Job-Typ.
    """
    return _service.get_job_templates(
        source_layer_id=source_layer_id,
        target_layer_id=target_layer_id,
        job_type=job_type
    )


@router.get("/jobs/{template_id}", response_model=JobTemplate)
async def get_job_template(template_id: int):
    """Einzelnes Job-Template laden"""
    template = _service.get_job_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template {template_id} nicht gefunden")
    return template


@router.post("/jobs", response_model=dict)
async def create_job_template(request: CreateJobTemplateRequest):
    """Neues Job-Template erstellen"""
    try:
        template_id = _service.create_job_template(request)
        return {"template_id": template_id, "message": "Template erstellt"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/jobs/{template_id}", response_model=dict)
async def delete_job_template(template_id: int):
    """Job-Template inkl. aller Step-Templates löschen"""
    template = _service.get_job_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template {template_id} nicht gefunden")
    ok = _service.delete_template(template_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Löschen fehlgeschlagen")
    return {"message": f"Template {template_id} gelöscht"}


# =============================================================================
# Step Templates
# =============================================================================

@router.get("/steps", response_model=List[StepTemplate])
async def get_step_templates(
    template_id: Optional[int] = Query(None, description="Nur Steps eines Job-Templates"),
    standalone_only: bool = Query(False, description="Nur eigenständige Bausteine")
):
    """
    Liste aller Step-Templates.
    
    - template_id: Nur Steps eines bestimmten Job-Templates
    - standalone_only: Nur eigenständige Bausteine (template_id IS NULL)
    """
    return _service.get_step_templates(
        template_id=template_id,
        standalone_only=standalone_only
    )


@router.post("/steps", response_model=dict)
async def create_step_template(request: CreateStepTemplateRequest):
    """Neues Step-Template erstellen"""
    try:
        step_template_id = _service.create_step_template(request)
        return {"step_template_id": step_template_id, "message": "Step-Template erstellt"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Job aus Template erstellen
# =============================================================================

@router.post("/jobs/{template_id}/create-job", response_model=dict)
async def create_job_from_template(template_id: int, request: CreateJobFromTemplateRequest):
    """
    Erstellt neuen Job aus Template inkl. aller Steps.
    
    - Template muss existieren
    - job_name muss eindeutig sein
    - Parameter werden substituiert ({{KEY}} → Wert)
    """
    # Template-ID aus URL übernehmen
    request.template_id = template_id
    
    try:
        result = _service.create_job_from_template(request)
        return {
            "job_id":         result["job_id"],
            "target_table_id": result["target_table_id"],
            "target_created": result["target_created"],
            "message": f"Job aus Template {template_id} erstellt"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/steps/{step_template_id}/add-to-job/{job_id}", response_model=dict)
async def add_step_from_template(
    step_template_id: int,
    job_id: int,
    step_order: Optional[int] = Query(None, description="Position im Job"),
    parameters: Optional[str] = Query(None, description="JSON String mit Parametern")
):
    """
    Fügt einzelnen Step aus Template zu bestehendem Job hinzu.
    
    Für Custom-Jobs: Step-Bausteine einzeln hinzufügen.
    """
    import json
    
    params_dict = None
    if parameters:
        try:
            params_dict = json.loads(parameters)
        except:
            raise HTTPException(status_code=400, detail="Ungültiges JSON in parameters")
    
    try:
        new_step_id = _service.add_step_from_template(
            job_id=job_id,
            step_template_id=step_template_id,
            step_order=step_order,
            parameters=params_dict
        )
        return {"step_id": new_step_id, "message": "Step zum Job hinzugefügt"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Job als Template speichern
# =============================================================================

@router.post("/save-job/{job_id}", response_model=dict)
async def save_job_as_template(
    job_id: int,
    template_name: Optional[str] = Query(None, description="Name des Templates (default: Job-Name)"),
    template_code: Optional[str] = Query(None, description="Eindeutiger Code (default: aus Job-Name)"),
    category: Optional[str] = Query(None, description="Kategorie"),
    beschreibung: Optional[str] = Query(None, description="Beschreibung"),
    overwrite: bool = Query(False, description="Bei True: Existierendes Template überschreiben")
):
    """
    Speichert bestehenden Job als neues Template.
    
    Job + alle Steps werden als Template gespeichert.
    Kann dann für neue Jobs wiederverwendet werden.
    
    - Wenn Template bereits existiert und overwrite=False: 
      Gibt exists=True zurück, Template wird NICHT überschrieben.
    - Wenn Template existiert und overwrite=True:
      Altes Template wird gelöscht und neu erstellt.
    """
    try:
        result = _service.save_job_as_template(
            job_id=job_id,
            template_name=template_name,
            template_code=template_code,
            category=category,
            beschreibung=beschreibung,
            overwrite=overwrite
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Template Export / Import als ZIP
# =============================================================================

@router.get("/export/{template_id}")
async def export_template(template_id: int):
    """
    Exportiert Job-Template als ZIP (download).

    ZIP enthält:
    - manifest.json
    - job_template.json
    - step_templates.json
    - sql/<relativer-pfad>.sql  (alle referenzierten SQL-Templates)
    """
    try:
        zip_bytes = _service.export_template(template_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    template = _service.get_job_template(template_id)
    date_str = datetime.utcnow().strftime("%Y%m%d")
    filename = f"template_export_{template.template_code}_{date_str}.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/import", response_model=dict)
async def import_template(
    file: UploadFile = File(..., description="ZIP-Datei des exportierten Templates"),
    overwrite: bool = Query(False, description="Bei True: existierendes Template überschreiben"),
    template_code: Optional[str] = Query(None, description="Überschreibt den Template-Code aus der ZIP (für Umbenennungen bei Konflikten)")
):
    """
    Importiert Job-Template aus ZIP.

    - SQL-Dateien werden unter ddl/sql_templates/{TEMPLATE_CODE}/... gespeichert
    - DB: neuer Eintrag in META_ETL_JOB_TEMPLATE + META_ETL_JOB_STEP_TEMPLATE
    - Bei existierendem Template_Code und overwrite=False: exists=True zurück
    - template_code: optionaler Override (z.B. bei Namenskonflikt neuen Namen vergeben)
    """
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Nur ZIP-Dateien erlaubt")

    zip_bytes = await file.read()

    try:
        result = _service.import_template(zip_bytes, overwrite=overwrite, template_code_override=template_code)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Template Update (Inline-Bearbeitung)
# =============================================================================

@router.patch("/jobs/{template_id}", response_model=dict)
async def update_job_template(template_id: int, data: dict):
    """
    Aktualisiert Metadaten eines Job-Templates.
    Erlaubte Felder: template_name, beschreibung, category, tags
    """
    template = _service.get_job_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template {template_id} nicht gefunden")
    ok = _service.update_job_template(template_id, data)
    if not ok:
        raise HTTPException(status_code=500, detail="Update fehlgeschlagen")
    return {"message": "Template aktualisiert"}


@router.patch("/steps/{step_template_id}", response_model=dict)
async def update_step_template(step_template_id: int, data: dict):
    """
    Aktualisiert ein Step-Template.
    Erlaubte Felder: step_name, step_order, step_category, sql_template_path,
                     sql_inline, default_parameters, is_active, beschreibung
    """
    ok = _service.update_step_template(step_template_id, data)
    if not ok:
        raise HTTPException(status_code=500, detail="Update fehlgeschlagen")
    return {"message": "Step-Template aktualisiert"}
