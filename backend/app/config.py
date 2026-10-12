"""
Configuration Management
=========================

Lädt Konfiguration aus:
- cfg/config.yml  (Pfade, ETL-Settings)
- cfg/database.yml (Credentials, Source Systems)
"""
import json
import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from .models import LLMConnection

# =============================================================================
# Projekt-Root: relativ zu dieser Datei ermitteln
# config.py liegt in: daita-studio/backend/app/config.py
# → .parent.parent.parent = daita-studio/
# =============================================================================
STUDIO_ROOT = Path(__file__).parent.parent.parent
CFG_DIR = STUDIO_ROOT / "cfg"


def _load_yaml(filename: str) -> dict:
    """Lädt YAML-Datei aus cfg/"""
    filepath = CFG_DIR / filename
    if filepath.exists():
        with open(filepath, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}


# Config laden
_config = _load_yaml('config.yml')
_database = _load_yaml('database.yml')

# Install-Root aus config.yml (Fallback: automatisch ermittelt)
_install_root = Path(_config.get('install_root', str(STUDIO_ROOT)))

# =============================================================================
# PATHS aus config.yml (relativ zu install_root)
# =============================================================================
_paths_config = _config.get('paths', {})

PATHS = {
    "root":          _install_root,
    "cfg":           CFG_DIR,
    "frontend":      _install_root / "frontend",
    "ddl_output":    _install_root / _paths_config.get('ddl_output', 'ddl/generated'),
    "tpt_output":    _install_root / _paths_config.get('tpt_output', 'tpt/generated'),
    "tpt_log":       _install_root / _paths_config.get('tpt_log', 'log/tpt'),
    "sql_templates": _install_root / _paths_config.get('sql_templates', 'ddl/sql_templates'),
    "sql_output":    _install_root / _paths_config.get('sql_output', 'sql/generated'),
    "export_layers": _install_root / _paths_config.get('export_layers', 'sql/export_layers'),
    "etl_jobs":      _install_root / _paths_config.get('etl_jobs', 'etl/jobs'),
    "log":           _install_root / _paths_config.get('log', 'log'),
    "diagrams":      _install_root / _paths_config.get('diagrams', 'diagrams'),
}

# Ensure all output directories exist
for key, path in PATHS.items():
    if "output" in key or key in ("log", "tpt_log", "diagrams", "etl_jobs"):
        path.mkdir(parents=True, exist_ok=True)

# =============================================================================
# ETL Config (aus database.yml)
# =============================================================================
ETL_CONFIG = {
    'autocommit':        _database.get('teradata', {}).get('autocommit', False),
    'transaction_mode':  _database.get('teradata', {}).get('transaction_mode', 'ANSI'),
    'batch_size':        _database.get('teradata', {}).get('batch_size', 10000),
}
METADATA_CONFIG = _database.get('metadata', {})
LOGGING_CONFIG   = _config.get('logging', {})

# =============================================================================
# Auth / RBAC Config (aus config.yml → auth:)
# =============================================================================
_auth_config = _config.get('auth', {})
TOKEN_TTL_HOURS = _auth_config.get('token_ttl_hours', 8)

# ---------------------------------------------------------------------------
# Rechte-Matrix je Modul (Modul × Aktion → Mindestrolle)
# Aktionen: view (GET/HEAD), edit (POST/PUT/PATCH), delete (DELETE)
# Wird in cfg/config.yml unter auth.modules gepflegt; auth.default greift,
# wenn ein Modul (oder eine Aktion) dort nicht gesetzt ist.
# ---------------------------------------------------------------------------
_DEFAULT_PERM = {"view": "Viewer", "edit": "Editor", "delete": "Admin"}
AUTH_MODULE_PERMS = _auth_config.get('modules', {}) or {}
AUTH_DEFAULT_PERM = {**_DEFAULT_PERM, **(_auth_config.get('default', {}) or {})}

# Secret zum Signieren der Tokens. Wenn nicht in config.yml gesetzt, wird beim
# Start ein Zufalls-Secret erzeugt (Folge: nach jedem Neustart müssen sich
# Nutzer neu anmelden). Für stabile Tokens ein festes Secret in config.yml
# hinterlegen (auth.token_secret).
import secrets as _secrets
TOKEN_SECRET = _auth_config.get('token_secret') or _secrets.token_hex(32)
if not _auth_config.get('token_secret'):
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "auth.token_secret ist nicht gesetzt - es wird ein flüchtiges "
        "Zufalls-Secret verwendet. Für stabile Logins in cfg/config.yml setzen."
    )

# =============================================================================
# Database Config (aus database.yml)
# =============================================================================
TERADATA_CONFIG = _database.get('teradata', {})
SOURCE_SYSTEMS  = _database.get('source_systems', {})

# =============================================================================
# Legacy Pfade (für Kompatibilität mit bestehendem Code)
# =============================================================================
INSTALL_DIR      = _install_root
CONFIG_DIR       = _install_root / "backend" / "app" / "config"
CONNECTIONS_FILE = CFG_DIR / "connections.json"
OUTPUT_DIR       = _install_root / "lineage_reports"

# Ensure directories exist
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class ConnectionManager:
    """Verwaltet LLM Connections"""

    def __init__(self):
        self.connections: Dict[str, LLMConnection] = {}
        self._load_connections()

    def _load_connections(self):
        """Lädt Connections aus JSON Datei"""
        if CONNECTIONS_FILE.exists():
            with open(CONNECTIONS_FILE, 'r') as f:
                data = json.load(f)
                for conn_data in data.get('connections', []):
                    conn = LLMConnection(**conn_data)
                    self.connections[conn.id] = conn

    def get_all(self) -> List[LLMConnection]:
        return list(self.connections.values())

    def get(self, conn_id: str) -> LLMConnection:
        if conn_id not in self.connections:
            raise KeyError(f"Connection '{conn_id}' nicht gefunden")
        return self.connections[conn_id]

    def save(self, connection: LLMConnection):
        self.connections[connection.id] = connection
        self._persist()

    def delete(self, conn_id: str):
        if conn_id in self.connections:
            del self.connections[conn_id]
            self._persist()

    def _persist(self):
        data = {"connections": [c.dict() for c in self.connections.values()]}
        with open(CONNECTIONS_FILE, 'w') as f:
            json.dump(data, f, indent=2)


# Singleton
connection_manager = ConnectionManager()

# =============================================================================
# Environments (Meta-Datenbank-Auswahl, session-scoped per Request-Header)
# =============================================================================
# cfg/environments.yml listet mehrere Metadaten-Umgebungen (z.B. MDP01_META,
# SEM_DEV_MET_BASE, ...), jede mit eigenem Host/User/Passwort/Schema. Das
# aktive Environment wird PRO REQUEST über eine ContextVar gehalten (gesetzt
# von EnvironmentMiddleware in main.py anhand des Headers "X-Env-Id") - dadurch
# bleibt der Wechsel session-/tab-scoped und ist nebenläufig sicher (kein
# globaler mutable State, der zwischen parallelen Requests kollidieren könnte).
import contextvars

_environments_raw = _load_yaml('environments.yml')
_ENV_LIST = _environments_raw.get('environments', []) or []
ENVIRONMENTS: Dict[str, dict] = {e['id']: e for e in _ENV_LIST if e.get('id')}

# Fallback ohne environments.yml: ein "default"-Environment aus database.yml,
# damit der Proxy-Mechanismus unten immer funktioniert.
if not ENVIRONMENTS:
    ENVIRONMENTS = {
        "default": {
            "id": "default",
            "label": "Standard (database.yml)",
            "host": TERADATA_CONFIG.get("host", ""),
            "user": TERADATA_CONFIG.get("user", ""),
            "password": TERADATA_CONFIG.get("password", ""),
            "connect_timeout": TERADATA_CONFIG.get("connect_timeout", 10000),
            "schema": METADATA_CONFIG.get("schema", "MDP01_META"),
        }
    }

DEFAULT_ENV_ID = _environments_raw.get('default') or next(iter(ENVIRONMENTS))
if DEFAULT_ENV_ID not in ENVIRONMENTS:
    DEFAULT_ENV_ID = next(iter(ENVIRONMENTS))

_active_env_id_var: contextvars.ContextVar = contextvars.ContextVar(
    "active_env_id", default=DEFAULT_ENV_ID
)


def list_environments() -> List[dict]:
    """Für's Frontend: nur id+label, NIE Host/User/Passwort."""
    return [{"id": e["id"], "label": e.get("label", e["id"])} for e in ENVIRONMENTS.values()]


def get_default_env_id() -> str:
    return DEFAULT_ENV_ID


def get_active_env_id() -> str:
    return _active_env_id_var.get()


def set_active_env_id(env_id: str) -> str:
    """Setzt das aktive Environment für den aktuellen Request (ContextVar).
    Unbekannte/leere IDs fallen still auf den Default zurück."""
    _active_env_id_var.set(env_id if env_id in ENVIRONMENTS else DEFAULT_ENV_ID)
    return _active_env_id_var.get()


def get_active_env() -> dict:
    return ENVIRONMENTS.get(get_active_env_id(), ENVIRONMENTS[DEFAULT_ENV_ID])


def get_active_schema() -> str:
    return get_active_env().get("schema", "MDP01_META")


def get_active_teradata_config() -> dict:
    """Connection-Parameter (host/user/password/connect_timeout) des aktiven Environments."""
    env = get_active_env()
    return {
        "host": env.get("host", TERADATA_CONFIG.get("host", "")),
        "user": env.get("user", TERADATA_CONFIG.get("user", "")),
        "password": env.get("password", TERADATA_CONFIG.get("password", "")),
        "connect_timeout": env.get("connect_timeout", TERADATA_CONFIG.get("connect_timeout", 10000)),
    }


def get_etl_jobs_path(base: Optional[Path] = None) -> Path:
    """Verzeichnis der Step-Parameter-Dateien (etl/jobs/{env_id}/) des aktiven Environments.

    Job- und Step-IDs sind nur innerhalb einer Meta-DB eindeutig (geklonte
    Umgebungen haben dieselben IDs), daher ein Unterordner je Environment.
    """
    return Path(base or PATHS["etl_jobs"]) / get_active_env_id()


# =============================================================================
# Modeler-Konfiguration (META-Schema + Tabellennamen)
# =============================================================================
class _DynamicSchema:
    """String-artiger Proxy: liefert immer das META-Schema des AKTIVEN Environments.

    So bleiben alle bestehenden `from ..config import META_SCHEMA` +
    f"{META_SCHEMA}.META_TABLE" Stellen unveraendert funktionsfaehig, obwohl
    sich der Wert nun je nach Request/Environment aendert.
    """
    def _value(self) -> str:
        return get_active_schema()

    def __str__(self):
        return self._value()

    def __repr__(self):
        return self._value()

    def __format__(self, spec):
        return format(self._value(), spec)

    def __add__(self, other):
        return self._value() + other

    def __radd__(self, other):
        return other + self._value()

    def __eq__(self, other):
        return self._value() == other

    def __ne__(self, other):
        return self._value() != other

    def __hash__(self):
        return hash(self._value())

    def __getattr__(self, name):
        return getattr(self._value(), name)


class _DynamicDBConfig:
    """Dict-artiger Proxy: liefert host/username/password/database des aktiven Environments."""
    def _value(self) -> dict:
        cfg = get_active_teradata_config()
        return {
            "host": cfg["host"],
            "username": cfg["user"],
            "password": cfg["password"],
            "database": "dbc",
        }

    def __getitem__(self, key):
        return self._value()[key]

    def get(self, key, default=None):
        return self._value().get(key, default)

    def __contains__(self, key):
        return key in self._value()

    def __iter__(self):
        return iter(self._value())

    def keys(self):
        return self._value().keys()

    def items(self):
        return self._value().items()

    def __repr__(self):
        return repr(self._value())


# Kompatibilitäts-Alias für daita-modeler-Services (erwarten DB_CONFIG)
DB_CONFIG = _DynamicDBConfig()

META_SCHEMA = _DynamicSchema()

META_TABLES = {
    "tables":     "META_TABLE",
    "columns":    "META_COLUMN",
    "fk":         "META_FOREIGN_KEY",
    "index":      "META_INDEX",
    "index_col":  "META_INDEX_COLUMN",
    "area":       "META_AREA",
    "area_cat":   "META_AREA_CATEGORY",
    "database":   "META_DATABASE",
    "layer":      "META_LAYER",
}
