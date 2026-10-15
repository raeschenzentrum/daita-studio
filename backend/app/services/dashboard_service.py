"""
DashboardService – deklarative Dashboards aus YAML-Dateien.

Ablage (PATHS["dashboards"], in cfg/config.yml → paths.dashboards; liegt
normalerweise im Kunden-Workspace):

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
from pathlib import Path
from typing import Any, Optional

import yaml

from app.config import META_SCHEMA, PATHS, get_active_env_id
from app.services import td_readonly

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
    if not widget.get("sql"):
        raise DashboardError(400, f"Widget '{widget_id}' hat keine SQL-Datei")
    sql, params, used = _render_sql(dash, widget, widget["sql"], raw_filters)
    max_rows = int((widget.get("optionen") or {}).get("max_zeilen", td_readonly.DEFAULT_MAX_ROWS))
    ttl = int(dash.get("cache_ttl", td_readonly.DEFAULT_TTL))
    # Schlüssel über SQL und Parameter: Widgets mit gleicher Abfrage teilen sich das Ergebnis
    digest = hashlib.sha1(f"{sql}|{max_rows}|{json.dumps(params, default=str)}".encode()).hexdigest()
    key = f"dash::{dashboard_id}::{digest}"
    try:
        result, from_cache = td_readonly.cached(key, lambda: td_readonly.query(sql, params, max_rows), ttl)
    except td_readonly.ReadOnlyViolation as e:
        raise DashboardError(500, f"Widget '{widget_id}': {e}")
    except Exception as e:
        logger.exception("Widget %s/%s", dashboard_id, widget_id)
        raise DashboardError(502, f"Abfrage fehlgeschlagen: {e}")

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
    }
    if dash.get("datenstand"):
        meta["datenstand"] = datenstand(dashboard_id, dash)
    return {"columns": result["columns"], "rows": rows, "meta": meta}


def datenstand(dashboard_id: str, dash: Optional[dict] = None) -> Optional[str]:
    dash = dash or _load_dashboard(dashboard_id)
    if not dash.get("datenstand"):
        return None
    sql, params, _ = _render_sql(dash, None, dash["datenstand"], {})
    try:
        res, _ = td_readonly.cached(f"dash::{dashboard_id}::__datenstand",
                                    lambda: td_readonly.query(sql, params, 1),
                                    int(dash.get("cache_ttl", td_readonly.DEFAULT_TTL)))
    except Exception as e:
        logger.warning("Datenstand %s: %s", dashboard_id, e)
        return None
    return res["rows"][0][0] if res["rows"] else None


def refresh(dashboard_id: str) -> int:
    _safe_id(dashboard_id)
    return td_readonly.invalidate(f"dash::{dashboard_id}::")


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


def object_status(refs: list[str]) -> dict:
    """Je 'DB.OBJEKT': {existiert, art, zeilen, fehler}. Nicht auflösbare Verweise → fehler."""
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
        for ref, (db, obj) in targets.items():
            entry = {"objekt": f"{db}.{obj}", "existiert": False}
            try:
                kind = td_readonly.query(
                    "SELECT TableKind FROM DBC.TablesV WHERE DatabaseName = ? AND TableName = ?",
                    [db, obj], 1)["rows"]
                if kind:
                    entry["existiert"] = True
                    entry["art"] = {"T": "Tabelle", "O": "Tabelle", "V": "View"}.get(kind[0][0], kind[0][0])
                    entry["zeilen"] = td_readonly.query(
                        f"LOCKING ROW FOR ACCESS SELECT COUNT(*) FROM {db}.{obj}", (), 1)["rows"][0][0]
            except Exception as e:
                entry["fehler"] = str(e).splitlines()[0][:200]
            res[ref] = entry
        return res

    key = "dashboards::status::" + json.dumps(sorted(targets.items()))
    found, _ = td_readonly.cached(key, _load)
    out.update(found)
    return out


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
