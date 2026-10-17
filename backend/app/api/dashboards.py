"""
Dashboards API – deklarative Dashboards (Definitionen als YAML unter
PATHS["dashboards"], siehe services/dashboard_service.py und
docs/DASHBOARD_KONZEPT.md).

Der Client erhält nie SQL; Filterwerte kommen als Query-Parameter.
"""

from fastapi import APIRouter, HTTPException, Request

import json

from app.services import dashboard_service as svc
from app.services import bom_service, star_service

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


@router.get("/{dashboard_id}/widgets/{widget_id}/stern")
def get_stern(dashboard_id: str, widget_id: str):
    """Star-Explorer: Fakten, Kennzahlen, Dimensionen (Rollen) und freigegebene Attribute."""
    return _call(star_service.definition, dashboard_id, widget_id)


@router.get("/{dashboard_id}/widgets/{widget_id}/stern/werte")
def get_stern_werte(dashboard_id: str, widget_id: str, fakt: str, rolle: str, attr: str):
    """Werte eines Attributs für die Filter-Auswahlliste."""
    return _call(star_service.werte, dashboard_id, widget_id, fakt, rolle, attr)


@router.get("/{dashboard_id}/widgets/{widget_id}/stern/abfrage")
def get_stern_abfrage(dashboard_id: str, widget_id: str, fakt: str, q: str = "{}",
                      offset: int = 0, limit: int = 100, ausfuehren: bool = True):
    """Star-Explorer: Auswahl als JSON (q = {gruppen, filter, kennzahlen}); liefert das
    erzeugte SQL und eine Seite des gruppierten Ergebnisses. ausfuehren=false: nur SQL."""
    try:
        auswahl = json.loads(q)
    except ValueError:
        raise HTTPException(status_code=400, detail="q ist kein gültiges JSON")
    return _call(star_service.abfrage, dashboard_id, widget_id, fakt, auswahl, offset, limit, ausfuehren)


@router.get("/{dashboard_id}/widgets/{widget_id}/stern/r")
def get_stern_r(dashboard_id: str, widget_id: str, fakt: str, q: str = "{}"):
    """Star-Explorer: R-Gerüst zur Auswahl (Vorlage widget.R, Excel-Export)."""
    try:
        auswahl = json.loads(q)
    except ValueError:
        raise HTTPException(status_code=400, detail="q ist kein gültiges JSON")
    return _call(star_service.r_code, dashboard_id, widget_id, fakt, auswahl)


def _auswahl(q: str) -> dict:
    try:
        return json.loads(q)
    except ValueError:
        raise HTTPException(status_code=400, detail="q ist kein gültiges JSON")


@router.get("/{dashboard_id}/widgets/{widget_id}/bom/werte")
def get_bom_werte(dashboard_id: str, widget_id: str, entitaet: str, attr: str):
    """BOM-Explorer: Werte eines Attributs für die Filter-Auswahlliste."""
    return _call(bom_service.werte, dashboard_id, widget_id, entitaet, attr)


@router.get("/{dashboard_id}/widgets/{widget_id}/bom/abfrage")
def get_bom_abfrage(dashboard_id: str, widget_id: str, basis: str, q: str = "{}",
                    offset: int = 0, limit: int = 100, ausfuehren: bool = True):
    """BOM-Explorer: Auswahl als JSON (q = {zeit, gruppen, filter, kennzahlen}) ab der
    Ausgangsentität basis; liefert SQL und eine Seite des Ergebnisses. ausfuehren=false: nur SQL."""
    return _call(bom_service.abfrage, dashboard_id, widget_id, basis, _auswahl(q), offset, limit, ausfuehren)


@router.get("/{dashboard_id}/widgets/{widget_id}/bom/r")
def get_bom_r(dashboard_id: str, widget_id: str, basis: str, q: str = "{}"):
    """BOM-Explorer: R-Gerüst zur Auswahl (Vorlage widget.R)."""
    return _call(bom_service.r_code, dashboard_id, widget_id, basis, _auswahl(q))


@router.get("/{dashboard_id}/status")
def get_status(dashboard_id: str):
    """Je Objekt aus 'objekte' der Definition: existiert, Art, Zeilenzahl."""
    return _call(svc.dashboard_status, dashboard_id)


@router.post("/{dashboard_id}/refresh")
def refresh(dashboard_id: str):
    """Cache dieses Dashboards im aktiven Environment leeren."""
    return {"entfernt": _call(svc.refresh, dashboard_id)}
