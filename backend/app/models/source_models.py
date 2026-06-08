"""
Source System Models
====================

Pydantic Models für externe Quellsysteme und TPT Job Erstellung.

Autor: DWH MVP Team
Datum: 2026-03-18
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# =============================================================================
# Source System Models
# =============================================================================

class SourceSystemBase(BaseModel):
    """Base Model für Source System"""
    source_system_name: str
    source_system_code: str
    source_type: str  # MSSQL, ORACLE, POSTGRESQL
    host_name: Optional[str] = None
    port_number: Optional[int] = None
    default_database: Optional[str] = None
    default_schema: Optional[str] = None
    odbc_dsn_name: Optional[str] = None
    credential_user_wallet: Optional[str] = None
    credential_password_wallet: Optional[str] = None
    is_active: str = "Y"
    beschreibung: Optional[str] = None
    verantwortlicher: Optional[str] = None
    kontakt_email: Optional[str] = None


class SourceSystem(SourceSystemBase):
    """Source System (DB Entity)"""
    source_system_id: int
    create_timestamp: datetime
    last_alter_timestamp: datetime
    
    class Config:
        from_attributes = True


class SourceSystemCreate(SourceSystemBase):
    """Model für Source System Erstellung"""
    source_system_id: int  # Manuell vergeben


# =============================================================================
# Source Table Discovery Models
# =============================================================================

class SourceColumn(BaseModel):
    """Spalte aus externem Quellsystem"""
    column_name: str
    data_type: str
    max_length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    is_nullable: bool = True
    ordinal_position: int
    # Teradata Mapping
    td_data_type: Optional[str] = None
    # TPT-spezifische Felder (aus META_DATATYPE_MAPPING)
    tpt_schema_multiplier: int = 1
    convert_template: Optional[str] = None


class SourceTable(BaseModel):
    """Tabelle aus externem Quellsystem"""
    table_schema: str
    table_name: str
    table_type: str = "BASE TABLE"
    row_count: Optional[int] = None
    columns: List[SourceColumn] = []


class SourceTableList(BaseModel):
    """Liste von Tabellen aus Source System"""
    source_system_id: int
    source_system_code: str
    tables: List[SourceTable]
    total_count: int


# =============================================================================
# Column Mapping Models
# =============================================================================

class ColumnMapping(BaseModel):
    """Mapping einer Source-Spalte auf Target-Spalte"""
    source_column: str
    target_column: str
    source_type: str
    target_type: str
    # TPT-spezifische Felder (optional)
    tpt_schema_type: Optional[str] = None
    tpt_schema_multiplier: int = 1
    convert_expression: Optional[str] = None


# =============================================================================
# TPT Job Creation Models
# =============================================================================

class TPTJobCreateRequest(BaseModel):
    """Request zum Erstellen eines TPT Load Jobs"""
    source_system_id: int
    source_table: str  # schema.table_name
    target_database: str  # Pflichtfeld - aus META_LAYER/META_DATABASE
    target_table: Optional[str] = None  # Default: gleicher Name wie Source
    
    # Column Mappings (optional - für benutzerdefinierte Spaltennamen/Typen)
    column_mappings: Optional[List[ColumnMapping]] = None
    
    # TPT Konfiguration
    tpt_operator_type: str = "UPDATE"
    tpt_max_sessions: int = 4
    tpt_min_sessions: int = 1
    use_staging: bool = True
    staging_suffix: str = "_LOAD"
    
    # Job Konfiguration
    job_name: Optional[str] = None  # Default: load_{target_table}
    beschreibung: Optional[str] = None
    
    # Optionen
    create_target_table: bool = False  # DDL für Zieltabelle generieren
    register_in_meta_table: bool = True  # In META_TABLE/META_COLUMN registrieren


class TPTJobCreateResponse(BaseModel):
    """Response nach TPT Job Erstellung"""
    success: bool
    etl_job_id: Optional[int] = None
    job_name: Optional[str] = None
    steps_created: int = 0
    message: str
    
    # Optional: generierte Artefakte
    target_table_ddl: Optional[str] = None
    tpt_script_preview: Optional[str] = None


class TableWithMappings(BaseModel):
    """Tabelle mit optionalen Column Mappings für Bulk-Erstellung"""
    table_name: str  # schema.table_name
    column_mappings: Optional[List[ColumnMapping]] = None


class BulkTPTJobCreateRequest(BaseModel):
    """Request zum Erstellen mehrerer TPT Jobs auf einmal"""
    source_system_id: int
    source_tables: List[str]  # Liste von schema.table_name (einfach)
    tables_with_mappings: Optional[List[TableWithMappings]] = None  # Alternativ: mit Mappings
    target_database: str  # Pflichtfeld - aus META_LAYER/META_DATABASE
    
    # Gemeinsame Konfiguration
    tpt_operator_type: str = "UPDATE"
    tpt_max_sessions: int = 4
    use_staging: bool = True
    
    # Optionen
    register_in_meta_table: bool = True


class BulkTPTJobCreateResponse(BaseModel):
    """Response nach Bulk Job Erstellung"""
    total_requested: int
    successful: int
    failed: int
    results: List[TPTJobCreateResponse]


# =============================================================================
# Import Status Models
# =============================================================================

class TableImportStatus(BaseModel):
    """Status einer Tabelle für Import-Übersicht"""
    source_table: str
    is_registered: bool = False  # In META_TABLE registriert?
    has_tpt_job: bool = False    # TPT Job existiert?
    etl_job_id: Optional[int] = None
    last_load_status: Optional[str] = None
    last_load_time: Optional[datetime] = None
    row_count_source: Optional[int] = None
    row_count_target: Optional[int] = None
