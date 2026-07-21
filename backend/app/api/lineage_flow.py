"""
Lineage-Flow API – Herkunftsgraph (Dataflow) eines Objekts.

Kombiniert ETL-Kanten (META_ETL_JOB) und View-Kanten (View-DDL via sqlglot).
Read-only.
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.services import lineage_flow_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lineage", tags=["lineage-flow"])


@router.get("/dataflow/{table_id}")
def get_dataflow(
    table_id: int,
    depth: int = Query(12, ge=1, le=50, description="Maximale Traversierungstiefe"),
):
    """
    Herkunftsgraph (upstream) eines Objekts als ``{root_table_id, nodes, edges}``.

    Folgt materialisierten ETL-Strecken (``META_ETL_JOB``) **und**
    View-Abhängigkeiten (View-DDL via sqlglot).
    """
    try:
        return lineage_flow_service.build_dataflow(table_id, depth)
    except Exception as e:
        logger.error(f"Error building dataflow for table {table_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/view/{table_id}/ddl")
def get_view_ddl(table_id: int):
    """View-DDL (RequestText) eines Objekts: ``{table_id, db_name, table_name, ddl}``."""
    try:
        return lineage_flow_service.get_view_ddl(table_id)
    except Exception as e:
        logger.error(f"Error fetching view DDL for table {table_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
