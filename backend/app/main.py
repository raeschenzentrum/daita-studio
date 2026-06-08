"""
metadaita - FastAPI Backend
Column Lineage Analysis with LLM Enhancement + ETL Orchestrator Dashboard
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List
import traceback

from .models import (
    SQLParseRequest, 
    LineageResult, 
    LLMConnection, 
    HealthResponse,
    ColumnMapping,
    ConversionRequest,
    ConversionResult,
    ConversionConfig as ConversionConfigModel
)
from .config import connection_manager
from .lineage_service import LineageService
from .conversion_service import conversion_service
import yaml
from pathlib import Path

# Import Routers
from .api import etl as etl_router
from .api import metadata as metadata_router
from .api import source_api as source_router
from .api import jobs as jobs_router
from .api import templates as templates_router

# FastAPI App
app = FastAPI(
    title="metadaita API",
    description="Column Lineage Analysis with LLM Enhancement + ETL Orchestrator + Metadata Management",
    version="1.1.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In Production: Spezifische Origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(etl_router.router)
app.include_router(metadata_router.router)
app.include_router(source_router.router, prefix="/api")
app.include_router(jobs_router.router)  # Job Management (AF-001 bis AF-005)
app.include_router(templates_router.router)  # Templates (AF-006)

# Services
lineage_service = LineageService()


@app.get("/", response_model=HealthResponse)
async def health_check():
    """Health Check Endpoint"""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        available_connections=len(connection_manager.get_all())
    )


@app.get("/api/connections", response_model=List[LLMConnection])
async def get_connections():
    """Gibt alle LLM Connections zurück"""
    return connection_manager.get_all()


@app.get("/api/connections/{connection_id}", response_model=LLMConnection)
async def get_connection(connection_id: str):
    """Gibt eine spezifische Connection zurück"""
    try:
        return connection_manager.get(connection_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/connections", response_model=LLMConnection)
async def create_connection(connection: LLMConnection):
    """Erstellt neue LLM Connection"""
    try:
        return connection_manager.add(connection)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/connections/{connection_id}", response_model=LLMConnection)
async def update_connection(connection_id: str, connection: LLMConnection):
    """Aktualisiert LLM Connection"""
    try:
        return connection_manager.update(connection_id, connection)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/connections/{connection_id}")
async def delete_connection(connection_id: str):
    """Löscht LLM Connection"""
    try:
        connection_manager.delete(connection_id)
        return {"message": "Connection gelöscht"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/lineage/parse", response_model=LineageResult)
async def parse_sql_lineage(request: SQLParseRequest):
    """
    Parsed SQL und generiert Column Lineage mit optionalen LLM-Beschreibungen
    """
    try:
        # 1. Parse SQL
        parse_result = lineage_service.parse_sql(request.sql, request.dialect)
        
        # 2. Optional: LLM Enrichment
        columns = parse_result['columns']
        llm_used = None
        llm_success_count = 0
        
        if request.llm_connection_id:
            try:
                connection = connection_manager.get(request.llm_connection_id)
                llm_used = connection.name
                # Convert Pydantic model to dict for service layer
                enriched_columns = lineage_service.enrich_with_llm(columns, connection.model_dump())
                columns = [col.model_dump() for col in enriched_columns]
                llm_success_count = sum(1 for col in columns if col.get('llm_description'))
            except Exception as e:
                print(f"LLM Enrichment failed: {e}")
                traceback.print_exc()
        
        # 3. Convert to ColumnMapping objects
        column_mappings = [ColumnMapping(**col) for col in columns]
        
        # 4. Generate Mermaid
        mermaid_code = lineage_service.generate_mermaid(column_mappings)
        
        # 5. Optional: Generate HTML
        html_file = None
        if request.generate_html:
            html_file = lineage_service.generate_html(
                column_mappings, 
                mermaid_code, 
                llm_used or "N/A",
                request.sql
            )
        
        return LineageResult(
            success=True,
            columns=column_mappings,
            source_tables=parse_result['tables'],
            mermaid_code=mermaid_code,
            html_file=html_file,
            stats={
                'total_columns': len(columns),
                'llm_enriched': llm_success_count,
                'llm_backend': llm_used
            }
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/api/lineage/report/{filename}")
async def download_report(filename: str):
    """Download HTML Report"""
    from .config import OUTPUT_DIR
    file_path = OUTPUT_DIR / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Report nicht gefunden")
    
    return FileResponse(
        path=str(file_path),
        media_type="text/html",
        filename=filename
    )


# =============================================================================
# CONFIG ENDPOINTS
# =============================================================================

@app.get("/api/config/layers")
async def get_layer_config():
    """Layer-Konfiguration aus parameter_rules.yml"""
    cfg_dir = Path(__file__).parent.parent.parent / "cfg"
    param_rules_yml = cfg_dir / "parameter_rules.yml"
    
    if param_rules_yml.exists():
        with open(param_rules_yml, 'r') as f:
            rules = yaml.safe_load(f)
            return rules.get('layers', {})
    else:
        # Fallback wenn keine Config existiert
        return {
            "raw": {"database": "MDP01_RAW_LAYER"},
            "discoverable": {"database": "MDP01_DISCOVERABLE_LAYER", "history_suffix": "_HISTORY"},
            "reusable": {"database": "MDP01_REUSABLE_LAYER", "history_suffix": "_HISTORY"},
            "consumable": {"database": "MDP01_CONSUMABLE_LAYER"}
        }


# =============================================================================
# SQL DIALECT CONVERSION ENDPOINTS
# =============================================================================

@app.get("/api/conversion/config", response_model=ConversionConfigModel)
async def get_conversion_config():
    """Get allowed target dialects for SQL conversion"""
    return ConversionConfigModel(
        allowed_target_dialects=conversion_service.config.allowed_target_dialects,
        default_target_dialect=conversion_service.config.default_target_dialect
    )


@app.post("/api/conversion/translate", response_model=ConversionResult)
async def convert_sql(request: ConversionRequest):
    """
    Convert SQL from source dialect to target dialect with optional LLM review
    
    Example Request:
    ```json
    {
        "sql": "SELECT * FROM dbo.Users WHERE Status = 1",
        "source_dialect": "tsql",
        "target_dialect": "teradata",
        "llm_connection_ids": ["ollama-llama32", "llm-farm-deepseek"]
    }
    ```
    """
    try:
        # Get LLM connections if requested (max 2 for dual review)
        llm_connections = []
        if request.llm_connection_ids:
            for conn_id in request.llm_connection_ids[:2]:  # Max 2 LLMs
                conn = connection_manager.get(conn_id)
                if conn:
                    # Convert Pydantic model to dict
                    llm_connections.append(conn.model_dump())
        
        # Convert SQL
        result = conversion_service.convert_sql(
            sql=request.sql,
            source_dialect=request.source_dialect,
            target_dialect=request.target_dialect,
            llm_connection=llm_connections[0] if llm_connections else None
        )
        
        # Get second LLM review if available
        if len(llm_connections) > 1:
            second_reviews = conversion_service._get_llm_reviews(
                request.sql,
                result.get("converted_sql", ""),
                request.source_dialect,
                request.target_dialect,
                [llm_connections[1]]
            )
            result["llm_reviews"].extend(second_reviews)
        
        return ConversionResult(**result)
    
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Conversion error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
