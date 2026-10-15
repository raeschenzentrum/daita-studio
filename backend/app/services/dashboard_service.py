"""
DashboardService – deklarative Dashboards aus YAML-Dateien.

Ablage: je Environment `dashboards:` in cfg/environments.yml (lokal, nicht
im Repo – zeigt typischerweise in den Kunden-Workspace), sonst
PATHS["dashboards"] (cfg/config.yml → paths.dashboards, neutrales Beispiel):

    <root>/
      umgebungen.yml     optional: Variablen je Environment
      katalog.yml        optional: Bereiche/Elemente für die Übersichtsseite
      <id>.yml           je Dashboard eine Datei
      sql/<datei>.sql    Widget-SQL mit Platzhaltern
      geo/<name>.json    GeoJSON für Karten-Widgets

Platzhalter im SQL (Syntax wie template_engine: ${NAME}):
    ${META_SCHEMA}       Meta-Schema des aktiven Environments
    ${DB_<LAYER_CODE>}   Datenbank des Layers aus META_LAYER/META_DATABASE (z. B. ${DB_CONS})
    ${<NAME>}            eigene Variable aus umgebungen.yml (default + je Environment)
    ${FILTER:<id>}       Wert eines freigegebenen Filters → Bind-Parameter (?)

Der Client schickt nie SQL, nur Filterwerte; ausgeführt wird nur SELECT
(services/td_readonly.py).
"""

import datetime as _dt
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

import yaml

from app.config import META_SCHEMA, PATHS, get_active_env, get_active_env_id
from app.services import r_skelett, sql_analyse, td_readonly

logger = logging.getLogger(__name__)

RESERVED_FILES = {"umgebungen", "katalog"}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_IDENT_RE = re.compile(r"^[A-Za-z0-9_$#]+$")
_PH_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([A-Za-z0-9_-]+))?\}")


class DashboardError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# ---------------------------------------------------------------------------
# Dateien
# ---------------------------------------------------------------------------

def _root() -> Path:
    eigen = get_active_env().get("dashboards")
    if eigen:
        return Path(PATHS["root"]) / eigen  # absolut oder relativ zu install_root
    return Path(PATHS["dashboards"])


def _safe_id(value: str) -> str:
    if not value or not _ID_RE.match(value):
        raise DashboardError(400, f"Ungültige Kennung: {value!r}")
    return value


def _inside_root(rel: str) -> Path:
    root = _root().resolve()
    p = (root / rel).resolve()
    if not p.is_relative_to(root):
        raise DashboardError(400, f"Pfad außerhalb der Dashboard-Ablage: {rel}")
    return p


def _load_yaml(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise DashboardError(500, f"YAML-Fehler in {path.name}: {e}")


def _load_dashboard(dashboard_id: str) -> dict:
    _safe_id(dashboard_id)
    if dashboard_id in RESERVED_FILES:
        raise DashboardError(404, f"Dashboard '{dashboard_id}' nicht gefunden")
    path = _root() / f"{dashboard_id}.yml"
    if not path.exists():
        raise DashboardError(404, f"Dashboard '{dashboard_id}' nicht gefunden")
    data = _load_yaml(path)
    data["id"] = dashboard_id
    return data


def _widget(dash: dict, widget_id: str) -> dict:
    for w in dash.get("widgets") or []:
        if w.get("id") == widget_id:
            return w
    raise DashboardError(404, f"Widget '{widget_id}' nicht gefunden")


# ---------------------------------------------------------------------------
# Variablen / Platzhalter
# ---------------------------------------------------------------------------

def _builtin_variables() -> dict:
    def _load():
        res = td_readonly.query(
            f"SELECT l.layer_code, d.database_name "
            f"FROM {META_SCHEMA}.META_LAYER l "
            f"JOIN {META_SCHEMA}.META_DATABASE d ON d.layer_id = l.layer_id "
            f"ORDER BY l.layer_code, d.database_id"
        )
        out = {}
        for code, db in res["rows"]:
            if code and db:
                out.setdefault(f"DB_{str(code).strip().upper()}", str(db).strip())
        return out

    try:
        layer_dbs, _ = td_readonly.cached("dashboards::layer_dbs", _load)
    except Exception as e:  # Meta nicht erreichbar → nur META_SCHEMA
        logger.warning("Layer-Datenbanken nicht lesbar: %s", e)
        layer_dbs = {}
    return {"META_SCHEMA": str(META_SCHEMA), **layer_dbs}


def variables() -> dict:
    """Alle Variablen des aktiven Environments (ohne Filter)."""
    values = _builtin_variables()
    path = _root() / "umgebungen.yml"
    if path.exists():
        cfg = (_load_yaml(path).get("variablen") or {})
        own = {**(cfg.get("default") or {}), **(cfg.get(get_active_env_id()) or {})}
        for name, raw in own.items():
            values[str(name)] = _substitute(str(raw), values, strict=False)
    return values


def _substitute(text: str, values: dict, strict: bool = True) -> str:
    missing = []

    def repl(m):
        name, arg = m.group(1), m.group(2)
        if arg is not None:  # ${FILTER:x} o. ä. – hier nicht zuständig
            return m.group(0)
        if name in values:
            return str(values[name])
        missing.append(name)
        return m.group(0)

    out = _PH_RE.sub(repl, text)
    if strict and missing:
        raise DashboardError(500, f"Unbekannte Platzhalter: {', '.join(sorted(set(missing)))}")
    return out


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

def _filter_value(fdef: dict, raw: Optional[str]) -> Any:
    typ = fdef.get("typ", "text")
    value = raw if raw not in (None, "") else fdef.get("default")
    fid = fdef.get("id")
    if value is None:
        raise DashboardError(400, f"Filter '{fid}' fehlt")
    try:
        if typ == "jahr":
            if isinstance(value, str) and value.startswith("aktuell"):
                offset = int(value[7:] or 0)
                value = _dt.date.today().year + offset
            value = int(value)
            if not 1900 <= value <= 2100:
                raise ValueError
        elif typ == "zahl":
            value = float(value)
            value = int(value) if value.is_integer() else value
            if "min" in fdef and value < fdef["min"] or "max" in fdef and value > fdef["max"]:
                raise ValueError
        elif typ == "datum":
            value = _dt.date.today() if value == "heute" else _dt.date.fromisoformat(str(value))
        elif typ == "auswahl":
            allowed = [w["wert"] if isinstance(w, dict) else w for w in fdef.get("werte") or []]
            if value not in allowed and str(value) not in [str(a) for a in allowed]:
                raise ValueError
            value = next(a for a in allowed if str(a) == str(value))
        else:  # text
            value = str(value)
            if len(value) > 200:
                raise ValueError
    except (ValueError, TypeError, StopIteration):
        raise DashboardError(400, f"Ungültiger Wert für Filter '{fid}': {raw!r}")
    return value


def _render_sql(dash: dict, widget: dict, sql_rel: str, raw_filters: dict) -> tuple[str, list, dict]:
    path = _inside_root(sql_rel)
    if not path.exists():
        raise DashboardError(500, f"SQL-Datei fehlt: {sql_rel}")
    text = path.read_text(encoding="utf-8")

    fdefs = {f["id"]: f for f in dash.get("filter") or [] if f.get("id")}
    allowed = set(widget.get("filter") or []) if widget is not None else set(fdefs)
    params: list = []
    used: dict = {}

    def repl(m):
        kind, fid = m.group(1), m.group(2)
        if kind != "FILTER" or fid is None:
            return m.group(0)
        if fid not in fdefs or fid not in allowed:
            raise DashboardError(500, f"Filter '{fid}' ist für dieses Widget nicht freigegeben")
        val = used.get(fid)
        if fid not in used:
            val = used[fid] = _filter_value(fdefs[fid], raw_filters.get(fid))
        params.append(val)
        return "?"

    text = _PH_RE.sub(repl, text)
    text = _substitute(text, variables())
    rest = _PH_RE.search(text)
    if rest:
        raise DashboardError(500, f"Unbekannter Platzhalter in {sql_rel}: {rest.group(0)}")
    return text, params, used


# ---------------------------------------------------------------------------
# Öffentliche Funktionen
# ---------------------------------------------------------------------------

def list_dashboards() -> list[dict]:
    root = _root()
    if not root.exists():
        return []
    out = []
    for path in sorted(root.glob("*.yml")):
        if path.stem in RESERVED_FILES or not _ID_RE.match(path.stem):
            continue
        try:
            d = _load_yaml(path)
        except DashboardError as e:
            logger.warning(e.message)
            continue
        out.append({
            "id": path.stem,
            "titel": d.get("titel", path.stem),
            "gruppe": d.get("gruppe"),
            "reihenfolge": d.get("reihenfolge", 999),
            "beschreibung": d.get("beschreibung"),
        })
    return sorted(out, key=lambda d: (d["reihenfolge"], d["titel"]))


def get_dashboard(dashboard_id: str) -> dict:
    """Definition für den Client – ohne SQL-Dateinamen."""
    d = _load_dashboard(dashboard_id)
    widgets = []
    for w in d.get("widgets") or []:
        w = {k: v for k, v in w.items() if k != "sql"}
        widgets.append(w)
    return {
        "id": d["id"],
        "titel": d.get("titel", d["id"]),
        "beschreibung": d.get("beschreibung"),
        "gruppe": d.get("gruppe"),
        "filter": d.get("filter") or [],
        "widgets": widgets,
        "hat_datenstand": bool(d.get("datenstand")),
    }


def _min_zelle(dash: dict) -> Optional[int]:
    if "min_zelle" in dash:
        return dash["min_zelle"]
    kat = _root() / "katalog.yml"
    return _load_yaml(kat).get("min_zelle") if kat.exists() else None


def widget_data(dashboard_id: str, widget_id: str, raw_filters: dict) -> dict:
    dash = _load_dashboard(dashboard_id)
    widget = _widget(dash, widget_id)
    if widget.get("daten") == "katalog":
        return _katalog_daten()
    if not widget.get("sql"):
        raise DashboardError(400, f"Widget '{widget_id}' hat keine SQL-Datei")
    sql, params, used = _render_sql(dash, widget, widget["sql"], raw_filters)
    max_rows = int((widget.get("optionen") or {}).get("max_zeilen", td_readonly.DEFAULT_MAX_ROWS))
    ttl = int(dash.get("cache_ttl", td_readonly.DEFAULT_TTL))
    # Schlüssel über SQL und Parameter: Widgets mit gleicher Abfrage teilen sich das Ergebnis
    digest = hashlib.sha1(f"{sql}|{max_rows}|{json.dumps(params, default=str)}".encode()).hexdigest()
    key = f"dash::{dashboard_id}::{digest}"
    def _laden():
        t0 = time.monotonic()
        res = td_readonly.query(sql, params, max_rows, art="daten")
        res["laufzeit_ms"] = int((time.monotonic() - t0) * 1000)
        return res

    try:
        result, from_cache = td_readonly.cached(key, _laden, ttl)
    except td_readonly.ReadOnlyViolation as e:
        raise DashboardError(500, f"Widget '{widget_id}': {e}")
    except Exception as e:
        logger.warning("Widget %s/%s: %s", dashboard_id, widget_id, str(e).splitlines()[0])
        raise DashboardError(502, f"Abfrage fehlgeschlagen: {str(e).splitlines()[0]}")

    rows = result["rows"]
    suppressed = 0
    limit = _min_zelle(dash)
    cols = (widget.get("optionen") or {}).get("zelle_spalten") or []
    if limit and cols:
        idx = [result["columns"].index(c) for c in cols if c in result["columns"]]
        rows = [list(r) for r in rows]
        for r in rows:
            for i in idx:
                v = r[i]
                if isinstance(v, (int, float)) and 0 < v < limit:
                    r[i] = None
                    suppressed += 1

    meta = {
        "zeilen": len(rows),
        "abgeschnitten": result["truncated"],
        "cache": from_cache,
        "unterdrueckt": suppressed,
        "filter": {k: str(v) for k, v in used.items()},
        "laufzeit_ms": result.get("laufzeit_ms"),
    }
    if dash.get("datenstand"):
        meta["datenstand"] = datenstand(dashboard_id, dash)
    return {"columns": result["columns"], "rows": rows, "meta": meta}


def widget_info(dashboard_id: str, widget_id: str, raw_filters: dict, zeilen: bool = True) -> dict:
    """Inhalt des Info-Panels: Erläuterung, Hinweise, Objekte (Fakt/Dimension mit
    Status), Joins, Herkunft bis zu den Tabellen, SQL (Vorlage, eingesetzt, mit Werten)."""
    dash = _load_dashboard(dashboard_id)
    widget = _widget(dash, widget_id)
    info = {
        "dashboard": dashboard_id,
        "widget": widget_id,
        "titel": widget.get("titel", widget_id),
        "typ": widget.get("typ"),
        "erlaeuterung": widget.get("erlaeuterung"),
        "hinweise": list(widget.get("hinweise") or []),
        "katalog": None,
        "objekte": [], "joins": [], "herkunft": [],
        "sql": None,
    }
    if widget.get("katalog"):
        info["katalog"] = _katalog_element(widget["katalog"])
        if info["katalog"] and info["katalog"].get("luecke") and not info["hinweise"]:
            info["hinweise"].append(info["katalog"]["luecke"])

    if widget.get("daten") == "katalog":
        return _katalog_info(dash, widget, info, zeilen)
    if not widget.get("sql"):
        return info

    vorlage = _inside_root(widget["sql"]).read_text(encoding="utf-8")
    sql, params, used = _render_sql(dash, widget, widget["sql"], raw_filters)
    info["erlaeuterung"] = info["erlaeuterung"] or sql_analyse.erlaeuterung(vorlage)
    objs = sql_analyse.objekte(sql)
    # Zeilenzahlen können bei großen Views Sekunden dauern: der Client lädt sie getrennt nach
    status = object_status([o["objekt"] for o in objs], zaehlen=zeilen) if objs else {}
    for o in objs:
        st = status.get(o["objekt"], {})
        o.update({k: st.get(k) for k in ("existiert", "zeilen", "zugriff", "fehler") if k in st})
    info["objekte"] = objs
    info["joins"] = sql_analyse.joins(sql, objs)
    try:
        info["herkunft"] = sql_analyse.herkunft([o["objekt"] for o in objs])
    except Exception as e:
        logger.warning("Herkunft %s/%s: %s", dashboard_id, widget_id, str(e).splitlines()[0])
        info["herkunft_fehler"] = str(e).splitlines()[0][:200]
    info["sql"] = {
        "datei": widget["sql"],
        "vorlage": vorlage,
        "gerendert": sql,
        "mit_werten": sql_analyse.mit_werten(sql, params),
        "parameter": {k: str(v) for k, v in used.items()},
    }
    try:
        umg = _root() / "umgebungen.yml"
        r_umg = (_load_yaml(umg).get("r_umgebungen") or {}) if umg.exists() else {}
        fdefs = {f["id"]: f for f in dash.get("filter") or [] if f.get("id")}
        alle_filter = dict(used)
        for fid in fdefs:   # auch Filter, die nicht im SQL stehen, mit Default füllen
            if fid not in alle_filter and fid in (widget.get("filter") or []):
                alle_filter[fid] = _filter_value(fdefs[fid], raw_filters.get(fid))
        info["r_code"] = r_skelett.erzeuge(dash, widget, vorlage, alle_filter, fdefs, r_umg, variables, _root())
    except Exception as e:
        logger.warning("R-Gerüst %s/%s: %s", dashboard_id, widget_id, e)
        info["r_code_fehler"] = str(e)[:200]
    return info


_KATALOG_ERLAEUTERUNG = {
    "area-map": ("Data-Mart-Bereiche aus dem Katalog (katalog.yml): je Bereich Produkte, Priorität, "
                 "Schutzniveau und Abdeckung (Anteil der Kennzahlen, die vorhanden oder ableitbar sind; "
                 "teilweise zählt halb). Der Status jedes Elements verbindet den Plan aus dem Katalog mit "
                 "dem live geprüften Ist-Stand seines DB-Objekts (existiert, Zeilen, Lesezugriff)."),
    "star-map": ("Stern eines Data-Mart-Bereichs aus dem Katalog: Fakt mit Kennzahlen, Dimensionen, "
                 "heutige Umsetzung und Datenprodukte, jeweils mit Plan-Status und live geprüftem Ist-Stand."),
    "subject-map": ("Business-Objekt-Modell aus dem Katalog: Subject Areas mit ihren Entitäten. Status je "
                    "Entität = Plan aus dem Katalog kombiniert mit dem live geprüften Ist-Stand der "
                    "umgesetzten Tabelle; Linien = Beziehungen aus dem Katalog."),
}


def _katalog_quellen(widget: dict) -> list[str]:
    """Rohe 'quelle'-Angaben (mit Platzhaltern) der Katalog-Teile, die das Widget zeigt."""
    path = _root() / "katalog.yml"
    if not path.exists():
        return []
    kat = _load_yaml(path)
    bereiche = kat.get("bereiche") or []
    if widget.get("typ") == "subject-map":
        teile = [b for b in bereiche if b.get("art") == "subject_area"]
    else:
        teile = (kat.get("conformed_dimensionen") or []) + [b for b in bereiche if b.get("art") == "mart"]
    roh: list = []
    _collect_sources(teile, roh)
    return list(dict.fromkeys(roh))


def _katalog_info(dash: dict, widget: dict, info: dict, zeilen: bool) -> dict:
    """Info-Panel für Übersichts-Widgets: Katalog-Objekte, Herkunft, Statusprüfung als SQL und R."""
    info["erlaeuterung"] = info["erlaeuterung"] or _KATALOG_ERLAEUTERUNG.get(
        widget.get("typ"), "Erzeugt aus dem Katalog (katalog.yml); kein eigenes SQL.")
    roh = _katalog_quellen(widget)
    if not roh:
        return info
    werte = variables()
    status = object_status(roh, zaehlen=zeilen)
    objs = []
    for r in roh:
        name = _substitute(r, werte, strict=False).upper()
        st = status.get(r, {})
        o = {"objekt": name, "db": name.split(".")[0], "name": name.split(".")[-1], "aliase": [],
             "art": sql_analyse.art(name.split(".")[-1])}
        o.update({k: st.get(k) for k in ("existiert", "zeilen", "zugriff", "fehler") if k in st})
        objs.append(o)
    info["objekte"] = objs
    info["hinweise"] = info["hinweise"] or []
    ohne = [o["name"] for o in objs if o.get("existiert") is False]
    if ohne:
        info["hinweise"].append("Im Katalog genannt, aber nicht in der Datenbank: " + ", ".join(ohne))
    try:
        info["herkunft"] = sql_analyse.herkunft([o["objekt"] for o in objs if o.get("existiert") is not False])
    except Exception as e:
        info["herkunft_fehler"] = str(e).splitlines()[0][:200]
    kopf = ("-- Statusprüfung der Übersicht: je DB-Objekt aus katalog.yml Existenz und Art,\n"
            "-- danach die Zeilenzahl (über die Verbindung der Umgebung, bei fehlendem\n"
            "-- Leserecht über die Lese-Verbindung der Dashboards).\n"
            "SELECT TableKind FROM DBC.TablesV WHERE DatabaseName = '<DB>' AND TableName = '<OBJEKT>';\n\n")
    info["sql"] = {
        "datei": "katalog.yml (Statusprüfung)",
        "vorlage": kopf + "\n".join(f"LOCKING ROW FOR ACCESS SELECT COUNT(*) FROM {r};" for r in roh),
        "gerendert": kopf + "\n".join(f"LOCKING ROW FOR ACCESS SELECT COUNT(*) FROM {o['objekt']};" for o in objs),
        "parameter": {},
    }
    info["sql"]["mit_werten"] = info["sql"]["gerendert"]
    try:
        umg = _root() / "umgebungen.yml"
        r_umg = (_load_yaml(umg).get("r_umgebungen") or {}) if umg.exists() else {}
        info["r_code"] = r_skelett.erzeuge_katalog(dash, widget, roh, info["erlaeuterung"], r_umg, variables, _root())
    except Exception as e:
        logger.warning("R-Gerüst Katalog %s: %s", dash["id"], e)
        info["r_code_fehler"] = str(e)[:200]
    return info


def _katalog_element(pfad: str) -> Optional[dict]:
    """Katalog-Element über Punktpfad aus IDs, z. B. 'm1.fact_asylstatistik.bewilligungsquote'."""
    kat = catalog()
    teile = pfad.split(".")
    knoten_liste = (kat.get("bereiche") or []) + (kat.get("conformed_dimensionen") or [])
    treffer = None
    for teil in teile:
        treffer = next((k for k in knoten_liste if isinstance(k, dict) and k.get("id") == teil), None)
        if treffer is None:
            return None
        knoten_liste = [x for key in ("fakten", "dimensionen", "kennzahlen", "entitaeten", "produkte")
                        for x in (treffer.get(key) or [])]
    return {k: treffer.get(k) for k in ("id", "titel", "status", "luecke", "quelle") if treffer.get(k) is not None}


def datenstand(dashboard_id: str, dash: Optional[dict] = None) -> Optional[str]:
    dash = dash or _load_dashboard(dashboard_id)
    if not dash.get("datenstand"):
        return None
    sql, params, _ = _render_sql(dash, None, dash["datenstand"], {})
    try:
        res, _ = td_readonly.cached(f"dash::{dashboard_id}::__datenstand",
                                    lambda: td_readonly.query(sql, params, 1, art="daten"),
                                    int(dash.get("cache_ttl", td_readonly.DEFAULT_TTL)))
    except Exception as e:
        logger.warning("Datenstand %s: %s", dashboard_id, e)
        return None
    return res["rows"][0][0] if res["rows"] else None


def refresh(dashboard_id: str) -> int:
    """Cache des Dashboards und den Objektstatus (Katalog/Übersicht) leeren."""
    _safe_id(dashboard_id)
    return td_readonly.invalidate(f"dash::{dashboard_id}::") + td_readonly.invalidate("dashboards::status::")


# ---------------------------------------------------------------------------
# Katalog und Objektstatus
# ---------------------------------------------------------------------------

def _collect_sources(node: Any, out: list) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "quelle" and isinstance(v, str):
                out.append(v)
            else:
                _collect_sources(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_sources(v, out)


def _resolve_sources(node: Any, values: dict) -> Any:
    if isinstance(node, dict):
        return {k: (_substitute(v, values, strict=False) if k == "quelle" and isinstance(v, str)
                    else _resolve_sources(v, values)) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_sources(v, values) for v in node]
    return node


def catalog() -> dict:
    path = _root() / "katalog.yml"
    if not path.exists():
        return {}
    return _resolve_sources(_load_yaml(path), variables())


def object_status(refs: list[str], zaehlen: bool = True) -> dict:
    """Je 'DB.OBJEKT': {objekt, existiert, art, zeilen | zugriff=False | fehler}.
    Nicht auflösbare Verweise → fehler."""
    values = variables()
    out: dict = {}
    targets: dict = {}
    for ref in dict.fromkeys(refs):
        resolved = _substitute(ref, values, strict=False)
        parts = resolved.split(".")
        if len(parts) != 2 or not all(_IDENT_RE.match(p) for p in parts):
            out[ref] = {"objekt": resolved, "existiert": False, "fehler": "nicht auflösbar"}
            continue
        targets[ref] = (parts[0].upper(), parts[1].upper())

    def _load():
        res = {}
        if not targets:
            return res
        with td_readonly.connection() as conn:
            # Existenz und Art für alle Objekte in einer Abfrage
            dbs = sorted({db for db, _ in targets.values()})
            kinds = {}
            rows = td_readonly.query(
                "SELECT TRIM(DatabaseName), TRIM(TableName), TableKind FROM DBC.TablesV "
                f"WHERE DatabaseName IN ({', '.join('?' * len(dbs))})", dbs, 100000, conn)["rows"]
            for db, obj, kind in rows:
                kinds[(db.upper(), obj.upper())] = kind
            daten = td_readonly.connection("daten") if td_readonly.hat_eigene_datenverbindung() else None
            try:
                for ref, (db, obj) in targets.items():
                    res[ref] = (_status_eines(conn, db, obj, kinds.get((db, obj)), daten) if zaehlen
                            else _ohne_zaehlung(db, obj, kinds.get((db, obj))))
            finally:
                if daten is not None:
                    daten.close()
        return res

    key = f"dashboards::status::{int(zaehlen)}::" + json.dumps(sorted(targets.items()))
    found, _ = td_readonly.cached(key, _load)
    out.update(found)
    return out


def _ohne_zaehlung(db: str, obj: str, kind: Optional[str]) -> dict:
    entry = {"objekt": f"{db}.{obj}", "existiert": kind is not None}
    if kind is not None:
        entry["art"] = {"T": "Tabelle", "O": "Tabelle", "V": "View"}.get(kind, kind)
    return entry


def _status_eines(conn, db: str, obj: str, kind: Optional[str], daten=None) -> dict:
    """Zeilenzahl über die Meta-Verbindung; fehlt dort das Recht, über die
    Daten-Verbindung (Lese-User der Dashboards) versuchen."""
    entry = {"objekt": f"{db}.{obj}", "existiert": kind is not None}
    if kind is None:
        return entry
    entry["art"] = {"T": "Tabelle", "O": "Tabelle", "V": "View"}.get(kind, kind)
    sql = f"LOCKING ROW FOR ACCESS SELECT COUNT(*) FROM {db}.{obj}"
    for c in [conn] + ([daten] if daten is not None else []):
        try:
            entry["zeilen"] = td_readonly.query(sql, (), 1, c)["rows"][0][0]
            entry.pop("zugriff", None)
            return entry
        except Exception as e:
            msg = str(e)
            if "[Error 3523]" in msg:  # existiert, aber dieser Verbindung fehlt SELECT
                entry["zugriff"] = False
            else:
                entry["fehler"] = msg.splitlines()[0][:200]
                return entry
    return entry


def _katalog_daten() -> dict:
    """Daten für Übersichts-Widgets: Katalog, Objektstatus, vorhandene Dashboards."""
    try:
        status = catalog_status()
    except DashboardError:
        raise
    except Exception as e:
        logger.exception("Katalogstatus")
        raise DashboardError(502, f"Objektstatus nicht lesbar: {e}")
    return {
        "columns": [], "rows": [],
        "katalog": catalog(),
        "status": status,
        "dashboards": [d["id"] for d in list_dashboards()],
        "meta": {"zeilen": len(status), "abgeschnitten": False, "cache": False, "unterdrueckt": 0},
    }


def catalog_status() -> dict:
    path = _root() / "katalog.yml"
    if not path.exists():
        return {}
    refs: list = []
    _collect_sources(_load_yaml(path), refs)
    return object_status(refs)


def dashboard_status(dashboard_id: str) -> dict:
    return object_status(list(_load_dashboard(dashboard_id).get("objekte") or []))


def geo(name: str) -> dict:
    _safe_id(name)
    path = _inside_root(f"geo/{name}.json")
    if not path.exists():
        raise DashboardError(404, f"Geodatei '{name}' nicht gefunden")
    return json.loads(path.read_text(encoding="utf-8"))
