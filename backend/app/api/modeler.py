"""
META API – lesende und schreibende Endpunkte für META-Schema-Daten.
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional

from app.services import meta_service

router = APIRouter(prefix="/api/modeler", tags=["meta"])


@router.get("/layers")
def list_layers():
    """Alle Layer (RAW, DISC, REUS, CONS, …)."""
    return meta_service.get_layers()


@router.get("/databases")
def list_databases():
    """Alle Datenbanken / Datenbank-Objekte aus META_DATABASE."""
    return meta_service.get_databases()


@router.get("/tables")
def list_tables(
    layer_id: Optional[int]  = Query(None, description="Layer filtern"),
    db_name:  Optional[str]  = Query(None, description="Datenbank filtern"),
    search:   Optional[str]  = Query(None, description="Freitextsuche (Name/Beschreibung)"),
):
    """
    Tabellen aus META_TABLE.
    Optionale Filter: layer_id, db_name, search (LIKE).
    """
    return meta_service.get_tables(layer_id=layer_id, db_name=db_name, search=search)


@router.get("/tables/{table_id}/columns")
def list_columns(table_id: int):
    """Spalten einer bestimmten Tabelle."""
    return meta_service.get_columns(table_id)


@router.get("/tables/{table_id}/fk")
def list_fk_for_table(table_id: int):
    """Foreign Keys, die von dieser Tabelle ausgehen."""
    return meta_service.get_foreign_keys(table_id=table_id)


@router.get("/fk")
def list_all_fk():
    """Alle Foreign Keys (für vollständiges ERD)."""
    return meta_service.get_foreign_keys()


@router.get("/areas")
def list_areas():
    """Subject Areas aus META_AREA."""
    return meta_service.get_areas()


# ---------------------------------------------------------------------------
# DM3: FK schreiben
# ---------------------------------------------------------------------------

class FKCreateRequest(BaseModel):
    fk_name:          Optional[str] = None
    child_table_id:   int
    parent_table_id:  int
    child_column_id:  Optional[int] = None
    parent_column_id: Optional[int] = None


@router.post("/fk")
def create_fk(body: FKCreateRequest):
    """Neuen logischen FK in META_FOREIGN_KEY eintragen."""
    return meta_service.create_foreign_key(
        fk_name=body.fk_name or "",
        child_table_id=body.child_table_id,
        parent_table_id=body.parent_table_id,
        child_column_id=body.child_column_id,
        parent_column_id=body.parent_column_id,
    )


class FKUpdateRequest(BaseModel):
    fk_name:          str
    child_column_id:  Optional[int] = None
    parent_column_id: Optional[int] = None


@router.put("/fk/{fk_id}")
def update_fk(fk_id: int, body: FKUpdateRequest):
    """FK-Name und Spalten-Zuordnung aktualisieren."""
    return meta_service.update_foreign_key(
        fk_id=fk_id,
        fk_name=body.fk_name,
        child_column_id=body.child_column_id,
        parent_column_id=body.parent_column_id,
    )


@router.delete("/fk/{fk_id}")
def delete_fk(fk_id: int):
    """FK aus META_FOREIGN_KEY löschen."""
    return meta_service.delete_foreign_key(fk_id)


@router.post("/cache/clear")
def clear_cache():
    """Cache leeren (z. B. nach manuellem DB-Eingriff)."""
    meta_service.clear_cache()
    return {"cleared": True}


# ---------------------------------------------------------------------------
# DM7: Tabellen / Spalten / Indizes bearbeiten + Reverse Engineering
# ---------------------------------------------------------------------------

@router.get("/tables/{table_id}")
def get_table_detail(table_id: int):
    """Vollständige Tabellen-Details."""
    return meta_service.get_table_detail(table_id)


class TableUpdateRequest(BaseModel):
    comment:            Optional[str] = None
    is_historized:      Optional[str] = None
    historization_type: Optional[str] = None
    valid_from_column:  Optional[str] = None
    valid_to_column:    Optional[str] = None
    is_current_column:  Optional[str] = None


@router.put("/tables/{table_id}")
def update_table(table_id: int, body: TableUpdateRequest):
    """Tabellen-Metadaten aktualisieren."""
    return meta_service.update_table(
        table_id=table_id,
        comment=body.comment,
        is_historized=body.is_historized,
        historization_type=body.historization_type,
        valid_from_column=body.valid_from_column,
        valid_to_column=body.valid_to_column,
        is_current_column=body.is_current_column,
    )


@router.get("/tables/{table_id}/columns/full")
def list_columns_full(table_id: int):
    """Erweiterte Spalten-Abfrage für den Editor."""
    return meta_service.get_columns_full(table_id)


class ColumnUpdateRequest(BaseModel):
    data_type:         Optional[str] = None
    data_length:       Optional[int] = None
    decimal_precision: Optional[int] = None
    decimal_scale:     Optional[int] = None
    nullable:          Optional[str] = None
    pk_flag:           Optional[str] = None
    bk_flag:           Optional[str] = None
    audit_flag:        Optional[str] = None
    comment:           Optional[str] = None
    default_value:     Optional[str] = None
    is_pk:             Optional[str] = None
    is_fk:             Optional[str] = None
    is_pi:             Optional[str] = None
    is_hash:           Optional[str] = None
    charset:           Optional[str] = None
    is_casespecific:   Optional[str] = None
    business_name:     Optional[str] = None
    masking_rule:      Optional[str] = None
    is_pii:            Optional[str] = None


@router.put("/columns/{column_id}")
def update_column(column_id: int, body: ColumnUpdateRequest):
    """Spalten-Metadaten aktualisieren."""
    return meta_service.update_column(
        column_id=column_id,
        data_type=body.data_type,
        data_length=body.data_length,
        decimal_precision=body.decimal_precision,
        decimal_scale=body.decimal_scale,
        nullable=body.nullable,
        pk_flag=body.pk_flag,
        bk_flag=body.bk_flag,
        audit_flag=body.audit_flag,
        comment=body.comment,
        default_value=body.default_value,
        is_pk=body.is_pk,
        is_fk=body.is_fk,
        is_pi=body.is_pi,
        is_hash=body.is_hash,
        charset=body.charset,
        is_casespecific=body.is_casespecific,
        business_name=body.business_name,
        masking_rule=body.masking_rule,
        is_pii=body.is_pii,
    )


@router.get("/tables/{table_id}/column-panel")
def get_column_panel(table_id: int):
    """Bottom-Panel-Daten: DBC + META Spalten für Tabellenvergleich."""
    return meta_service.get_column_panel(table_id)


@router.get("/tables/{table_id}/indexes")
def get_indexes(table_id: int):
    """Indizes (PI, UPI, SI) einer Tabelle."""
    return meta_service.get_indexes(table_id)


class IndexColumnItem(BaseModel):
    column_id:       int
    column_position: int


class IndexItem(BaseModel):
    index_type:  str = "PRIMARY INDEX"
    index_name:  Optional[str] = None
    is_unique:   str = "N"
    columns:     list[IndexColumnItem]


@router.put("/tables/{table_id}/indexes")
def save_indexes(table_id: int, body: list[IndexItem]):
    """Alle Indizes einer Tabelle ersetzen (vollständiger Replace)."""
    return meta_service.save_indexes(
        table_id=table_id,
        indexes=[i.model_dump() for i in body],
    )


@router.get("/tables/{table_id}/reverse-engineer")
def reverse_engineer(table_id: int, db_name: str = Query(...), table_name: str = Query(...)):
    """DBC.ColumnsV + IndicesV mit META vergleichen."""
    return meta_service.reverse_engineer(table_id, db_name, table_name)


@router.post("/tables/{table_id}/sync-from-dbc")
def sync_from_dbc(table_id: int, db_name: str = Query(...), table_name: str = Query(...)):
    """Typ/Länge/Nullable aus DBC in META_COLUMN übernehmen (nur Diffs)."""
    return meta_service.sync_columns_from_dbc(table_id, db_name, table_name)



@router.post("/cache/clear")
def clear_cache():
    """Meta-Cache leeren (nach Datenänderungen)."""
    meta_service.clear_cache()
    return {"status": "ok", "message": "Cache geleert"}


# ---------------------------------------------------------------------------
# DM12 – DDL
# ---------------------------------------------------------------------------

@router.get("/tables/{table_id}/ddl")
def get_ddl(table_id: int):
    """CREATE TABLE DDL aus META generieren."""
    return meta_service.generate_ddl(table_id)


class ExecuteDdlRequest(BaseModel):
    ddl: str


@router.post("/tables/{table_id}/ddl/execute")
def execute_ddl(table_id: int, body: ExecuteDdlRequest):
    """DDL-Text gegen Teradata ausführen."""
    return meta_service.execute_ddl(body.ddl)


# ---------------------------------------------------------------------------
# DM13 – Maintenance
# ---------------------------------------------------------------------------

@router.get("/tables/{table_id}/stats")
def get_table_stats(table_id: int):
    """Row-Count + Speicherverbrauch für eine Tabelle."""
    return meta_service.get_table_stats(table_id)


@router.delete("/tables/{table_id}/meta")
def delete_from_meta(table_id: int):
    """Tabelle + alle Abhängigkeiten aus META löschen (CASCADE)."""
    return meta_service.delete_from_meta(table_id)


@router.post("/tables/{table_id}/drop")
def drop_from_db(table_id: int):
    """DROP TABLE in Teradata ausführen."""
    return meta_service.drop_from_db(table_id)


@router.post("/tables/{table_id}/truncate")
def truncate_table(table_id: int):
    """Alle Zeilen der Tabelle in Teradata löschen (DELETE ALL)."""
    return meta_service.truncate_table(table_id)
