"""
Read-only-Zugriff auf Teradata für Auswertungen (Dashboards).

- Verbindung immer über das AKTIVE Environment (X-Env-Id). Zwei Arten:
    "meta"  – Verbindung des Environments (DB_CONFIG, Metadaten, DBC)
    "daten" – eigene Lese-Verbindung für Fachdaten aus `dashboards_db:` des
              Environments (cfg/environments.yml: user, password, optional host);
              ohne Angabe dieselbe wie "meta". Zweck: Konsumenten-User mit Leserolle
              statt des technischen Users.
- Nur ein einzelnes SELECT (optional mit LOCKING ... FOR ACCESS davor);
  alles andere wird vor der Ausführung abgewiesen.
- Ergebnis als {columns, rows} mit JSON-tauglichen Werten.
- TTL-Cache je Environment (Schlüssel "{env}::{key}").

Hinweis: meta_service.py hat eigene, gleichartige Helfer (_query/_cached).
Zusammenführen ist ein bekannter offener Punkt.
"""

import datetime as _dt
import decimal
import re
import threading
import time
from typing import Any, Callable, Optional

import teradatasql

from app.config import DB_CONFIG, get_active_env, get_active_env_id

DEFAULT_MAX_ROWS = 5000
DEFAULT_TTL = 300  # Sekunden

_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()


class ReadOnlyViolation(ValueError):
    """SQL ist kein einzelnes SELECT."""


# ---------------------------------------------------------------------------
# SQL-Prüfung
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_STRING_RE = re.compile(r"'(?:[^']|'')*'")
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|UPSERT|DROP|CREATE|REPLACE|ALTER|RENAME|"
    r"GRANT|REVOKE|COLLECT|CALL|EXEC|EXECUTE|COMMIT|ROLLBACK|ABORT)\b",
    re.I,
)


def check_select(sql: str) -> str:
    """Gibt das SQL ohne abschließendes Semikolon zurück oder wirft ReadOnlyViolation."""
    stripped = _COMMENT_RE.sub(" ", sql).strip().rstrip(";").strip()
    probe = _STRING_RE.sub("''", stripped)
    if ";" in probe:
        raise ReadOnlyViolation("Nur ein einzelnes Statement erlaubt")
    head = probe.upper()
    if head.startswith("LOCKING"):
        if not re.match(r"LOCKING\s+(ROW|TABLE\s+\S+|VIEW\s+\S+|DATABASE\s+\S+)?\s*FOR\s+ACCESS\b", head):
            raise ReadOnlyViolation("LOCKING nur als '... FOR ACCESS' erlaubt")
        head = re.sub(r"^LOCKING\s+.*?FOR\s+ACCESS\s*", "", head, count=1, flags=re.S)
    if not (head.startswith("SELECT") or head.startswith("SEL ") or head.startswith("WITH")):
        raise ReadOnlyViolation("Nur SELECT-Abfragen erlaubt")
    if _FORBIDDEN.search(probe):
        raise ReadOnlyViolation("Abfrage enthält ein nicht erlaubtes Schlüsselwort")
    return stripped


# ---------------------------------------------------------------------------
# Ausführung
# ---------------------------------------------------------------------------

def _json_value(v: Any) -> Any:
    if isinstance(v, decimal.Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat()
    if isinstance(v, str):
        return v.rstrip()
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    return v


def hat_eigene_datenverbindung() -> bool:
    return bool((get_active_env().get("dashboards_db") or {}).get("user"))


def _connect(art: str = "meta"):
    eigen = get_active_env().get("dashboards_db") or {}
    if art == "daten" and eigen.get("user"):
        return teradatasql.connect(
            host=eigen.get("host") or DB_CONFIG["host"],
            user=eigen["user"],
            password=eigen.get("password", ""),
        )
    return teradatasql.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["username"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
    )


def connection(art: str = "meta"):
    """Eine Verbindung für mehrere Abfragen (with td_readonly.connection() as conn: query(..., conn=conn))."""
    return _connect(art)


def query(sql: str, params: tuple | list = (), max_rows: int = DEFAULT_MAX_ROWS, conn=None,
          art: str = "meta") -> dict:
    """Führt ein geprüftes SELECT aus. Liefert {columns, rows, truncated}."""
    sql = check_select(sql)
    if conn is None:
        with _connect(art) as own:
            return query(sql, params, max_rows, own)
    with conn.cursor() as cur:
        cur.execute(sql, list(params))
        columns = [d[0] for d in cur.description]
        rows = cur.fetchmany(max_rows + 1)
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    return {
        "columns": columns,
        "rows": [[_json_value(v) for v in r] for r in rows],
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def cached(key: str, loader: Callable[[], Any], ttl: int = DEFAULT_TTL) -> tuple[Any, bool]:
    """(Daten, aus_cache). Schlüssel wird um das aktive Environment ergänzt."""
    full = f"{get_active_env_id()}::{key}"
    with _CACHE_LOCK:
        entry = _CACHE.get(full)
        if entry and (time.time() - entry["ts"]) < ttl:
            return entry["data"], True
    data = loader()
    with _CACHE_LOCK:
        _CACHE[full] = {"ts": time.time(), "data": data}
    return data, False


def invalidate(prefix: Optional[str] = None) -> int:
    """Entfernt Cache-Einträge des aktiven Environments (optional nur mit Präfix)."""
    start = f"{get_active_env_id()}::{prefix or ''}"
    with _CACHE_LOCK:
        keys = [k for k in _CACHE if k.startswith(start)]
        for k in keys:
            del _CACHE[k]
    return len(keys)
