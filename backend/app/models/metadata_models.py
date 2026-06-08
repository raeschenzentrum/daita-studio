"""
Generisches Metadaten-Modell für Metadaten-Verwaltung
Erweiterbar für Tabellen, Spalten, Views, Pipelines etc.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class MetadataObject(BaseModel):
    id: int
    name: str
    type: str = Field(..., description="Objekttyp, z.B. table, column, pipeline, ...")
    description: Optional[str] = None
    properties: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Zusätzliche Metadaten als JSON")

class MetadataObjectCreate(BaseModel):
    name: str
    type: str
    description: Optional[str] = None
    properties: Optional[Dict[str, Any]] = Field(default_factory=dict)

class MetadataObjectUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None
