"""
Diagrams API – Diagramm-Layouts als JSON speichern / laden.
Storage: Dateien in PATHS["diagrams"]/*.json
"""

from fastapi import APIRouter, HTTPException, Request
import json
from app.config import PATHS

router = APIRouter(prefix="/api/diagrams", tags=["diagrams"])


def _safe_name(name: str) -> str:
    """Nur alphanumerisch + Bindestrich/Leerzeichen/Unterstrich erlaubt."""
    safe = "".join(c for c in name if c.isalnum() or c in "-_ ").strip()
    if not safe:
        raise HTTPException(status_code=400, detail="Ungültiger Diagramm-Name")
    return safe


def _path(name: str):
    return PATHS["diagrams"] / f"{_safe_name(name)}.json"


@router.get("")
def list_diagrams():
    """Alle gespeicherten Diagramme (Namen ohne .json)."""
    d = PATHS["diagrams"]
    d.mkdir(exist_ok=True)
    return sorted(f.stem for f in d.glob("*.json"))


@router.get("/{name}")
def load_diagram(name: str):
    p = _path(name)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Diagramm '{name}' nicht gefunden")
    return json.loads(p.read_text(encoding="utf-8"))


@router.post("/{name}")
async def save_diagram(name: str, request: Request):
    data = await request.json()
    p = _path(name)
    PATHS["diagrams"].mkdir(exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "ok", "name": _safe_name(name)}


@router.delete("/{name}")
def delete_diagram(name: str):
    p = _path(name)
    if p.exists():
        p.unlink()
    return {"status": "ok"}
