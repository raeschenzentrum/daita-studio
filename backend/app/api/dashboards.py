"""
Dashboards API – deklarative Dashboards (Definitionen als YAML unter
PATHS["dashboards"], siehe services/dashboard_service.py und
docs/DASHBOARD_KONZEPT.md).

Der Client erhält nie SQL; Filterwerte kommen als Query-Parameter.
"""

from fastapi import APIRouter, HTTPException, Request

from app.services import dashboard_service as svc

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


def _call(fn, *args):
    try:
        return fn(*args)
    except svc.DashboardError as e:
        raise HTTPException(status_code=e.status, detail=e.message)


@router.get("")
def list_dashboards():
    """Alle Dashboards (id, titel, gruppe, reihenfolge, beschreibung)."""
    return _call(svc.list_dashboards)


@router.get("/catalog")
def get_catalog():
    """Katalog der Bereiche und Elemente (Platzhalter in 'quelle' aufgelöst)."""
    return _call(svc.catalog)


@router.get("/catalog/status")
def get_catalog_status():
    """Je 'quelle' im Katalog: existiert, Art, Zeilenzahl."""
    return _call(svc.catalog_status)


@router.get("/geo/{name}")
def get_geo(name: str):
    """GeoJSON für Karten-Widgets aus <ablage>/geo/."""
    return _call(svc.geo, name)


@router.get("/{dashboard_id}")
def get_dashboard(dashboard_id: str):
    """Definition ohne SQL: Filter, Widgets, Layout."""
    return _call(svc.get_dashboard, dashboard_id)


@router.get("/{dashboard_id}/widgets/{widget_id}/data")
def get_widget_data(dashboard_id: str, widget_id: str, request: Request):
    """Ergebnis {columns, rows, meta}. Filterwerte als Query-Parameter (?jahr_von=2015)."""
    return _call(svc.widget_data, dashboard_id, widget_id, dict(request.query_params))


@router.get("/{dashboard_id}/widgets/{widget_id}/info")
def get_widget_info(dashboard_id: str, widget_id: str, request: Request):
    """Info-Panel: Erläuterung, Hinweise, Fakten/Dimensionen, Joins, Herkunft, SQL.
    Filterwerte wie beim Datenabruf; das SQL wird nur angezeigt, nie vom Client entgegengenommen."""
    filter = dict(request.query_params)
    zeilen = filter.pop("_zeilen", "1") != "0"   # _zeilen=0: ohne Zeilenzahlen (schnell)
    return _call(svc.widget_info, dashboard_id, widget_id, filter, zeilen)


@router.get("/{dashboard_id}/status")
def get_status(dashboard_id: str):
    """Je Objekt aus 'objekte' der Definition: existiert, Art, Zeilenzahl."""
    return _call(svc.dashboard_status, dashboard_id)


@router.post("/{dashboard_id}/refresh")
def refresh(dashboard_id: str):
    """Cache dieses Dashboards im aktiven Environment leeren."""
    return {"entfernt": _call(svc.refresh, dashboard_id)}
