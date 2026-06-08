"""
Pydantic Models für metadaita API
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class LLMBackendType(str, Enum):
    """Verfügbare LLM Backend Typen"""
    ollama = "ollama"
    llm_farm = "llm-farm"
    openai = "openai"


class LLMConnection(BaseModel):
    """LLM Connection Configuration"""
    id: str = Field(..., description="Eindeutige Connection ID")
    name: str = Field(..., description="Anzeigename")
    backend_type: LLMBackendType
    url: str = Field(..., description="API Endpoint URL")
    model: str = Field(..., description="Modell Name")
    api_key: Optional[str] = Field(None, description="API Key (optional)")
    timeout: int = Field(90, description="Timeout in Sekunden", ge=10, le=300)


class SQLParseRequest(BaseModel):
    """Request für SQL Parsing und Lineage Generierung"""
    sql: str = Field(..., description="SQL Statement zum Analysieren")
    dialect: str = Field("tsql", description="SQL Dialect (tsql, postgres, mysql, etc.)")
    llm_connection_id: Optional[str] = Field(None, description="LLM Connection ID für Beschreibungen")
    generate_html: bool = Field(True, description="HTML Report generieren")


class ColumnMapping(BaseModel):
    """Column Lineage Mapping"""
    target_column: str
    source_expression: str
    transform_type: str
    transform_icon: str
    source_columns_d: List[str]
    source_columns_const: List[str]
    llm_description: Optional[str] = None


class LineageResult(BaseModel):
    """Ergebnis der Lineage Analyse"""
    success: bool
    columns: List[ColumnMapping]
    source_tables: List[Dict[str, Any]]
    mermaid_code: str
    html_file: Optional[str] = None
    error: Optional[str] = None
    stats: Dict[str, Any]


class ConversionRequest(BaseModel):
    """Request für SQL Dialect Conversion"""
    sql: str = Field(..., description="SQL Statement zum Konvertieren")
    source_dialect: str = Field("tsql", description="Quell-Dialect (tsql, postgres, mysql, etc.)")
    target_dialect: str = Field("teradata", description="Ziel-Dialect")
    llm_connection_ids: Optional[List[str]] = Field(None, description="LLM Connection IDs für Review (max 2)")


class LLMReview(BaseModel):
    """LLM Review eines konvertierten SQLs"""
    llm_name: str
    llm_model: str
    review: Optional[str] = None
    success: bool
    error: Optional[str] = None


class ConversionResult(BaseModel):
    """Ergebnis der SQL Dialect Conversion"""
    success: bool
    source_dialect: str
    target_dialect: str
    original_sql: str
    converted_sql: Optional[str] = None
    llm_reviews: List[LLMReview]
    error: Optional[str] = None
    stats: Dict[str, Any]


class ConversionConfig(BaseModel):
    """Configuration für verfügbare Ziel-Dialekte"""
    allowed_target_dialects: List[str]
    default_target_dialect: str


class HealthResponse(BaseModel):
    """Health Check Response"""
    status: str
    version: str
    available_connections: int
