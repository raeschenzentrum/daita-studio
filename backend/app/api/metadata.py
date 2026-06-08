"""
Metadata API Router
===================
REST API Endpoints für generische Metadaten-Verwaltung.
CRUD: List, Get, Create, Update, Delete.

Autor: DWH MVP Team
Datum: 2026-01-19
"""
from fastapi import APIRouter, HTTPException
from typing import List
import logging

from ..models.metadata_models import MetadataObject, MetadataObjectCreate, MetadataObjectUpdate

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/metadata",
    tags=["Metadata"],
    responses={404: {"description": "Not found"}}
)

# In-Memory Store (später durch DB ersetzen)
# Hinweis: Keine echten Tabellennamen hier - nur generische Beispiele
_metadata_store: List[MetadataObject] = [
    MetadataObject(id=1, name="EXAMPLE_TABLE_RAW", type="table", description="Beispiel-Tabelle im Raw Layer", properties={"layer": "RAW"}),
    MetadataObject(id=2, name="EXAMPLE_TABLE_HISTORY", type="table", description="Historisierte Beispiel-Tabelle", properties={"layer": "REUSABLE", "scd_type": 2}),
    MetadataObject(id=3, name="ETL_EXAMPLE_TO_HISTORY", type="pipeline", description="ETL Pipeline Beispiel", properties={"source": "EXAMPLE_TABLE_RAW", "target": "EXAMPLE_TABLE_HISTORY"}),
]
_next_id = 4


@router.get("/list", response_model=List[MetadataObject])
async def list_metadata(type: str = None):
    """Alle Metadaten-Objekte auflisten, optional nach Typ filtern."""
    if type:
        return [m for m in _metadata_store if m.type == type]
    return _metadata_store


@router.get("/{meta_id}", response_model=MetadataObject)
async def get_metadata(meta_id: int):
    """Ein Metadaten-Objekt nach ID abrufen."""
    for m in _metadata_store:
        if m.id == meta_id:
            return m
    raise HTTPException(status_code=404, detail="Metadaten-Objekt nicht gefunden")


@router.post("/", response_model=MetadataObject)
async def create_metadata(obj: MetadataObjectCreate):
    """Neues Metadaten-Objekt anlegen."""
    global _next_id
    new_obj = MetadataObject(id=_next_id, **obj.dict())
    _next_id += 1
    _metadata_store.append(new_obj)
    return new_obj


@router.put("/{meta_id}", response_model=MetadataObject)
async def update_metadata(meta_id: int, obj: MetadataObjectUpdate):
    """Metadaten-Objekt aktualisieren."""
    for i, m in enumerate(_metadata_store):
        if m.id == meta_id:
            updated = m.copy(update={k: v for k, v in obj.dict().items() if v is not None})
            _metadata_store[i] = updated
            return updated
    raise HTTPException(status_code=404, detail="Metadaten-Objekt nicht gefunden")


@router.delete("/{meta_id}")
async def delete_metadata(meta_id: int):
    """Metadaten-Objekt löschen."""
    global _metadata_store
    for i, m in enumerate(_metadata_store):
        if m.id == meta_id:
            _metadata_store.pop(i)
            return {"status": "deleted", "id": meta_id}
    raise HTTPException(status_code=404, detail="Metadaten-Objekt nicht gefunden")
