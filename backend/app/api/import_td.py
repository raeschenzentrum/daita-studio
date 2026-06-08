"""
Import API – Tabellen aus DBC.TablesV / DBC.ColumnsV in META_TABLE / META_COLUMN importieren.
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel
from app.services import import_service, meta_service

router = APIRouter(prefix="/api/import", tags=["import"])


class ImportRequest(BaseModel):
    db_name:    str
    table_name: str
    layer_id:   int = 1


@router.get("/candidates")
def get_candidates(db: str):
    """
    Alle Tabellen/Views in DBC.TablesV für die angegebene Datenbank.
    Jeder Eintrag enthält 'in_meta: bool' – ob bereits in META_TABLE vorhanden.
    """
    return import_service.get_candidates(db)


@router.post("/table")
def import_table(req: ImportRequest):
    """
    Importiert eine Tabelle aus DBC in META_TABLE + META_COLUMN + META_INDEX.
    """
    result = import_service.import_table(req.db_name, req.table_name, req.layer_id)
    if "error" not in result:
        meta_service.clear_cache()
    return result


@router.post("/tables/{table_id}/indexes")
def import_indexes(
    table_id:   int,
    db_name:    str = Query(...),
    table_name: str = Query(...),
):
    """
    Liest DBC.IndicesV und befüllt META_INDEX + META_INDEX_COLUMN nach
    (für Tabellen die vor dem PI-Fix importiert wurden).
    Überspringt bereits vorhandene Index-Nummern.
    """
    return import_service.import_indexes_from_dbc(table_id, db_name, table_name)
