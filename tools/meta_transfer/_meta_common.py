"""
Gemeinsame Helfer für den Meta-Schema-Transport (Export/Import).

Bewusst ohne Abhängigkeit zu `app.config`, damit die Skripte eigenständig
transportiert und auf dem Air-Gapped-Zielserver ausgeführt werden können.
Benötigt nur: teradatasql, PyYAML (beide im daita-studio-venv vorhanden).
"""
from __future__ import annotations

import base64
import datetime as _dt
import json
from decimal import Decimal
from pathlib import Path

import teradatasql
import yaml

# Bevorzugte Insert-Reihenfolge (Eltern vor Kindern – FK-sicher).
# Unbekannte Tabellen werden alphabetisch hinten angehängt.
PREFERRED_ORDER = [
    "META_LAYER",
    "META_AREA_CATEGORY",
    "META_AREA",
    "META_DATABASE",
    "META_TABLE",
    "META_COLUMN",
    "META_INDEX",
    "META_INDEX_COLUMN",
    "META_FOREIGN_KEY",
]


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
def default_config_path() -> Path:
    """cfg/database.yml relativ zu diesem Skript (daita-studio/cfg/database.yml)."""
    return Path(__file__).resolve().parents[2] / "cfg" / "database.yml"


def load_db_config(config_path: str | None, overrides: dict) -> dict:
    """
    Lädt Teradata-Verbindungsdaten aus database.yml und wendet CLI-Overrides an.

    Rückgabe-Dict: host, user, password, database, tmode, schema
    """
    cfg: dict = {}
    path = Path(config_path) if config_path else default_config_path()
    if path.exists():
        with open(path, "r") as f:
            cfg = yaml.safe_load(f) or {}

    td = cfg.get("teradata", {})
    meta = cfg.get("metadata", {})

    resolved = {
        "host": td.get("host", ""),
        "user": td.get("user", ""),
        "password": td.get("password", ""),
        "database": td.get("database", "dbc"),
        "tmode": td.get("transaction_mode", "ANSI"),
        "schema": meta.get("schema", "MDP01_META"),
    }
    # Overrides (nur gesetzte Werte übernehmen)
    for key, val in overrides.items():
        if val:
            resolved[key] = val
    return resolved


def connect(cfg: dict):
    """Öffnet eine teradatasql-Verbindung anhand des aufgelösten Config-Dicts."""
    return teradatasql.connect(
        host=cfg["host"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg.get("database", "dbc"),
        tmode=cfg.get("tmode", "ANSI"),
    )


# ---------------------------------------------------------------------------
# Tabellen-Auswahl
# ---------------------------------------------------------------------------
def parse_list(value: str | None) -> list[str]:
    """'A,B , c' -> ['A', 'B', 'C'] (uppercase, getrimmt, leere weg)."""
    if not value:
        return []
    return [t.strip().upper() for t in value.split(",") if t.strip()]


def select_tables(all_tables: list[str], only: list[str], exclude: list[str]) -> list[str]:
    """Wendet --tables (Whitelist) und --exclude (Blacklist) an, case-insensitiv."""
    upper_map = {t.upper(): t for t in all_tables}
    if only:
        chosen = [upper_map[t] for t in only if t in upper_map]
        missing = [t for t in only if t not in upper_map]
        if missing:
            print(f"  ! Nicht gefunden und übersprungen: {', '.join(missing)}")
    else:
        chosen = list(all_tables)
    if exclude:
        chosen = [t for t in chosen if t.upper() not in set(exclude)]
    return chosen


def order_for_import(tables: list[str]) -> list[str]:
    """Sortiert nach PREFERRED_ORDER; unbekannte alphabetisch ans Ende."""
    rank = {name: i for i, name in enumerate(PREFERRED_ORDER)}
    return sorted(tables, key=lambda t: (rank.get(t.upper(), len(rank)), t.upper()))


# ---------------------------------------------------------------------------
# Wert-Serialisierung (typ-erhaltend, JSON-fähig)
# ---------------------------------------------------------------------------
def serialize_value(v):
    """Python-Wert -> JSON-serialisierbar; Sondertypen mit Marker-Dict."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, Decimal):
        return {"__dec__": str(v)}
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return {"__dt__": v.isoformat()}
    if isinstance(v, (bytes, bytearray)):
        return {"__b64__": base64.b64encode(bytes(v)).decode("ascii")}
    return str(v)


def deserialize_value(v):
    """Umkehrung von serialize_value für das Insert auf dem Ziel."""
    if isinstance(v, dict):
        if "__dec__" in v:
            return v["__dec__"]          # als String binden -> DECIMAL/NUMBER ok
        if "__dt__" in v:
            return v["__dt__"]           # ISO-String -> DATE/TIMESTAMP ok (ANSI)
        if "__b64__" in v:
            return base64.b64decode(v["__b64__"])
    return v


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
def write_manifest(out_dir: Path, manifest: dict):
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def read_manifest(in_dir: Path) -> dict:
    return json.loads((in_dir / "manifest.json").read_text(encoding="utf-8"))
