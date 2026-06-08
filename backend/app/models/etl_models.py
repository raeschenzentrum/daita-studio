"""
ETL Orchestrator Models
=======================

Pydantic Models für ETL Jobs, Steps, Runs und Monitoring.
Getrennt von Lineage Models - modulare Struktur.

Autor: DWH MVP Team
Datum: 2026-01-19
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class JobStatus(str, Enum):
    """Job Run Status"""
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class StepCategory(str, Enum):
    """Step Kategorien"""
    STAGING = "STAGING"
    TRANSFORMATION = "TRANSFORMATION"
    SCD_TYPE2 = "SCD_TYPE2"
    VALIDATION = "VALIDATION"
    STATISTICS = "STATISTICS"


# =============================================================================
# ETL Job Models
# =============================================================================

class ETLJobBase(BaseModel):
    """Base Model für ETL Job"""
    job_name: str
    job_type: str
    source_table_id: Optional[int] = None
    target_table_id: Optional[int] = None
    is_active: str = "Y"
    retry_count: int = 3
    timeout_seconds: int = 3600


class ETLJob(ETLJobBase):
    """ETL Job (DB Entity)"""
    etl_job_id: int
    create_timestamp: datetime
    last_alter_timestamp: datetime
    
    class Config:
        from_attributes = True


class ETLJobWithDetails(ETLJob):
    """ETL Job mit zusätzlichen Informationen"""
    source_table_name: Optional[str] = None
    target_table_name: Optional[str] = None
    source_layer_id: Optional[int] = None
    target_layer_id: Optional[int] = None
    step_count: int = 0
    last_run_status: Optional[str] = None
    last_run_time: Optional[datetime] = None


# =============================================================================
# ETL Job Step Models
# =============================================================================

class ETLJobStepBase(BaseModel):
    """Base Model für Job Step"""
    etl_job_id: int
    step_name: str
    step_order: int
    step_category: str
    sql_template_path: Optional[str] = None
    sql_inline: Optional[str] = None
    python_module: Optional[str] = None
    python_function: Optional[str] = None
    parameters: Optional[str] = None  # JSON String
    condition_sql: Optional[str] = None
    skip_on_empty: str = "N"
    is_critical: str = "Y"
    rollback_on_error: str = "Y"
    is_active: str = "Y"


class ETLJobStep(ETLJobStepBase):
    """ETL Job Step (DB Entity)"""
    etl_job_step_id: int
    create_timestamp: datetime
    last_alter_timestamp: datetime
    
    class Config:
        from_attributes = True


# =============================================================================
# ETL Job Run Models
# =============================================================================

class ETLJobRunBase(BaseModel):
    """Base Model für Job Run"""
    etl_job_id: int
    start_time: datetime
    status: str = "RUNNING"


class ETLJobRun(ETLJobRunBase):
    """ETL Job Run (DB Entity)"""
    etl_job_run_id: int
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    error_stack: Optional[str] = None
    create_timestamp: datetime
    
    class Config:
        from_attributes = True


class ETLJobRunWithSteps(ETLJobRun):
    """Job Run mit Step Details"""
    job_name: str
    step_runs: List['ETLJobStepRunWithDetails'] = []


# =============================================================================
# ETL Job Step Run Models
# =============================================================================

class ETLJobStepRunBase(BaseModel):
    """Base Model für Step Run"""
    etl_job_run_id: int
    etl_job_step_id: int
    start_time: datetime
    status: str = "RUNNING"


class ETLJobStepRun(ETLJobStepRunBase):
    """ETL Job Step Run (DB Entity)"""
    etl_job_step_run_id: int
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    rows_read: Optional[int] = 0
    rows_inserted: Optional[int] = 0
    rows_updated: Optional[int] = 0
    rows_deleted: Optional[int] = 0
    error_message: Optional[str] = None
    error_stack: Optional[str] = None
    was_skipped: str = "N"
    skip_reason: Optional[str] = None
    create_timestamp: datetime
    
    class Config:
        from_attributes = True


class ETLJobStepRunWithDetails(ETLJobStepRun):
    """Step Run mit Step-Informationen"""
    step_name: str
    step_order: int
    step_category: str
    parameters: Optional[str] = None  # Step parameters (JSON string)


# =============================================================================
# Request/Response Models
# =============================================================================

class ExecuteJobRequest(BaseModel):
    """Request für Job Execution"""
    initial_load_mode: bool = False
    dry_run: bool = False


class ExecuteJobResponse(BaseModel):
    """Response für Job Execution"""
    etl_job_run_id: int
    status: str
    message: str


class JobRunHistoryRequest(BaseModel):
    """Request für Job Run History"""
    etl_job_id: Optional[int] = None
    status: Optional[str] = None
    limit: int = 50
    offset: int = 0


class JobPerformanceStats(BaseModel):
    """Performance Statistiken für einen Job"""
    etl_job_id: int
    job_name: str
    total_runs: int
    success_count: int
    failed_count: int
    avg_duration_seconds: Optional[float] = None
    min_duration_seconds: Optional[float] = None
    max_duration_seconds: Optional[float] = None
    success_rate: Optional[float] = None


class DashboardStats(BaseModel):
    """Dashboard Übersichts-Statistiken"""
    total_jobs: int
    active_jobs: int
    running_jobs: int
    recent_runs: List[ETLJobRun]
    failed_runs_24h: int
    success_rate_24h: Optional[float] = None
