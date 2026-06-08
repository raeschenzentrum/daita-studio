"""
TPT Script Generator für Metadata-Driven ETL Framework
=======================================================

Generiert TPT Scripts basierend auf Metadaten aus META_COLUMN.

Autor: DWH MVP Team
Datum: 2026-03-18
Version: 1.0
"""

import logging
import tempfile
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

try:
    import teradatasql
except ImportError:
    teradatasql = None

from .type_utils import td_typecode_to_ddl

logger = logging.getLogger(__name__)


# =============================================================================
# Config Loading
# =============================================================================

def _load_config() -> Dict[str, Any]:
    """Lädt database.yml Konfiguration."""
    # Pfad: backend/app/services/ -> backend -> metadaita/cfg/
    service_dir = Path(__file__).parent
    install_dir = service_dir.parent.parent.parent
    config_path = install_dir / "cfg" / "database.yml"
    
    if not config_path.exists():
        raise FileNotFoundError(f"database.yml nicht gefunden: {config_path}")
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


# =============================================================================
# Data Types Mapping: Teradata → TPT Schema
# =============================================================================

TERADATA_TO_TPT_TYPE = {
    # Integer Types
    'BYTEINT': 'BYTEINT',
    'SMALLINT': 'SMALLINT',
    'INTEGER': 'INTEGER',
    'BIGINT': 'BIGINT',
    
    # Decimal Types
    'DECIMAL': 'DECIMAL',
    'NUMERIC': 'DECIMAL',
    'FLOAT': 'FLOAT',
    'REAL': 'FLOAT',
    'DOUBLE PRECISION': 'FLOAT',
    
    # Character Types
    'CHAR': 'CHAR',
    'VARCHAR': 'VARCHAR',
    'CLOB': 'VARCHAR(64000)',
    
    # Date/Time Types
    'DATE': 'VARCHAR(50)',  # TPT ODBC: als String lesen
    'TIME': 'VARCHAR(50)',
    'TIMESTAMP': 'VARCHAR(50)',
    
    # Binary
    'BYTE': 'BYTE',
    'VARBYTE': 'VARBYTE',
    'BLOB': 'VARBYTE(64000)',
}


@dataclass
class ColumnInfo:
    """Spalteninfo aus META_COLUMN oder Parameters."""
    column_name: str  # Target Column Name (für DDL/INSERT)
    column_type: str
    column_length: Optional[int]
    decimal_total_digits: Optional[int]
    decimal_fractional_digits: Optional[int]
    nullable: str
    column_position: int
    source_column_name: Optional[str] = None  # Source Column Name (für SELECT), falls unterschiedlich
    source_type: Optional[str] = None  # Source Datentyp (z.B. 'uniqueidentifier', 'datetime2')
    tpt_schema_type: Optional[str] = None  # TPT ODBC Schema Typ (z.B. 'VARCHAR(200)'), vorberechnet
    convert_expression: Optional[str] = None  # SQL Server CONVERT Expression für SELECT
    
    @property
    def select_name(self) -> str:
        """Name für SELECT Statement (Source)."""
        return self.source_column_name or self.column_name
    
    @property
    def insert_name(self) -> str:
        """Name für INSERT Statement (Target)."""
        return self.column_name


class TPTGenerator:
    """
    Generiert TPT Scripts basierend auf Metadaten.
    
    Example:
        >>> generator = TPTGenerator(conn)
        >>> script_path = generator.generate(source_system, parameters)
    """
    
    def __init__(self, conn: 'teradatasql.TeradataConnection'):
        self.conn = conn
        self.config = _load_config()
        self._datatype_mappings = None  # Lazy loaded
    
    def generate(
        self,
        source_system: 'SourceSystemInfo',
        parameters: Dict[str, Any]
    ) -> str:
        """
        Generiert TPT Script und speichert es.
        
        Args:
            source_system: Source System Verbindungsinfos
            parameters: Job Step Parameter
        
        Returns:
            Pfad zum generierten TPT Script
        """
        # ERST: Columns aus Parametern (falls vorhanden), DANN aus META_COLUMN
        columns = self._get_columns(parameters)
        
        if not columns:
            raise ValueError(
                f"No columns found for table: "
                f"{parameters['target_database']}.{parameters['target_table']}. "
                f"Either provide 'columns' in parameters or ensure table exists in META_TABLE."
            )
        
        logger.info(f"Generating TPT script for {len(columns)} columns")
        
        # Build script sections
        job_name = f"load_{parameters['target_table']}"
        
        schema_def = self._build_schema_definition(columns)
        odbc_operator = self._build_odbc_operator(source_system, parameters, columns)
        td_operator = self._build_td_operator(parameters)
        apply_stmt = self._build_apply_statement(parameters, columns)
        
        # Assemble full script
        script = self._assemble_script(
            job_name=job_name,
            schema_def=schema_def,
            odbc_operator=odbc_operator,
            td_operator=td_operator,
            apply_stmt=apply_stmt
        )
        
        # Save script
        script_dir = Path(parameters.get('tpt_script_dir', '/tmp/tpt_scripts'))
        script_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        script_path = script_dir / f"{job_name}_{timestamp}.tpt"
        
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script)
        
        logger.info(f"TPT script saved: {script_path}")
        return str(script_path)
    
    def _get_columns(self, parameters: Dict[str, Any]) -> List[ColumnInfo]:
        """
        Holt Spalten - Priorität:
        1. Aus parameters['columns'] (direkt übergeben)
        2. Aus META_COLUMN (wenn Tabelle registriert)
        """
        # ERST: Columns aus Parameters verwenden
        if 'columns' in parameters and parameters['columns']:
            logger.info("Using columns from parameters")
            return self._columns_from_parameters(parameters['columns'])
        
        # FALLBACK: Aus META_COLUMN holen
        logger.info("Getting columns from META_COLUMN")
        cursor = self.conn.cursor()
        
        # Lookup table_id via META_TABLE
        cursor.execute("""
            SELECT t.TABLE_ID
            FROM MDP01_META.META_TABLE t
            JOIN MDP01_META.META_DATABASE d ON t.DATABASE_ID = d.DATABASE_ID
            WHERE d.DATABASE_NAME = ?
              AND t.TABLE_NAME = ?
        """, (parameters['target_database'], parameters['target_table']))
        
        row = cursor.fetchone()
        if not row:
            logger.warning(
                f"Table not found in META_TABLE: "
                f"{parameters['target_database']}.{parameters['target_table']}"
            )
            return []
        
        table_id = row[0]
        
        # Get columns
        cursor.execute("""
            SELECT 
                COLUMN_NAME,
                COLUMN_TYPE,
                COLUMN_LENGTH,
                DECIMAL_TOTAL_DIGITS,
                DECIMAL_FRACTIONAL_DIGITS,
                NULLABLE,
                COLUMN_POSITION
            FROM MDP01_META.META_COLUMN
            WHERE TABLE_ID = ?
            ORDER BY COLUMN_POSITION
        """, (table_id,))
        
        columns = []
        for row in cursor.fetchall():
            columns.append(ColumnInfo(
                column_name=row[0],
                column_type=row[1],
                column_length=row[2],
                decimal_total_digits=row[3],
                decimal_fractional_digits=row[4],
                nullable=row[5],
                column_position=row[6]
            ))
        
        return columns
    
    def _columns_from_parameters(self, cols: List[Dict[str, Any]]) -> List[ColumnInfo]:
        """
        Konvertiert Parameter-Columns zu ColumnInfo.
        
        Unterstützt zwei Formate:
        - Alt: {"name": "col", "td_type": "INTEGER", ...}
        - Neu: {"source_name": "col", "target_name": "new_col", "td_type": "INTEGER",
                "tpt_schema_type": "VARCHAR(200)", "convert_expression": "CONVERT(...)"}
        """
        columns = []
        for i, col in enumerate(cols):
            # Target Name hat Priorität, dann name (alt)
            col_name = col.get('target_name') or col.get('name')
            # Source Name für SELECT Statement
            source_name = col.get('source_name') or col.get('name')
            td_type = col.get('td_type', 'VARCHAR(255)')
            nullable = col.get('nullable', True)
            
            # NEU: tpt_schema_type und convert_expression direkt aus JSON
            tpt_schema_type = col.get('tpt_schema_type')  # z.B. 'VARCHAR(200)'
            convert_expression = col.get('convert_expression')  # z.B. 'CONVERT(VARCHAR(36), [rowguid])'
            
            # Parse Type für Length/Precision
            length = None
            precision = None
            scale = None
            
            if '(' in td_type:
                base_type = td_type.split('(')[0].upper()
                params = td_type.split('(')[1].rstrip(')')
                if ',' in params:
                    precision, scale = int(params.split(',')[0]), int(params.split(',')[1])
                else:
                    length = int(params)
            else:
                base_type = td_type.upper()
            
            # Source Type für Mapping-Lookup speichern
            source_type = col.get('source_type', '')
            # Nur den Basis-Typ extrahieren (z.B. 'nvarchar(50)' -> 'nvarchar')
            source_base_type = source_type.split('(')[0].lower() if source_type else ''
            
            columns.append(ColumnInfo(
                column_name=col_name,
                source_column_name=source_name,  # Für SELECT im ODBC
                column_type=td_type,
                column_length=length,
                decimal_total_digits=precision,
                decimal_fractional_digits=scale,
                nullable='Y' if nullable else 'N',
                column_position=i + 1,
                source_type=source_base_type,  # Für Datatype Mapping Lookup
                tpt_schema_type=tpt_schema_type,  # TPT Schema Typ (vorberechnet)
                convert_expression=convert_expression  # SQL Server CONVERT für SELECT
            ))
        
        return columns
    
    def _build_schema_definition(self, columns: List[ColumnInfo]) -> str:
        """Baut DEFINE SCHEMA Block - TPT Schema verwendet SOURCE Namen (für ODBC Reader)."""
        lines = []
        
        for i, col in enumerate(columns):
            tpt_type = self._get_tpt_type(col)
            comma = ',' if i < len(columns) - 1 else ''
            # TPT Schema: Source-Namen verwenden (für ODBC Reader SELECT)
            # Anführungszeichen für reservierte Wörter wie "Name"
            lines.append(f'        "{col.select_name}" {tpt_type}{comma}')
        
        return '\n'.join(lines)
    
    def _get_tpt_type(self, col: ColumnInfo) -> str:
        """Konvertiert Teradata Typ zu TPT Schema Typ.

        PRIORITÄT:
        1. col.tpt_schema_type falls vorhanden (vorberechnet im JSON)
        2. Rohe DBC Typecodes (I8, CV, DA ...) über td_typecode_to_ddl auflösen
        3. Bereits aufgelöste DDL-Typen direkt über TERADATA_TO_TPT_TYPE mappen
        """
        # 1. Vorberechneter TPT Schema Typ aus JSON
        if col.tpt_schema_type:
            return col.tpt_schema_type

        raw = col.column_type.strip() if col.column_type else ''

        # 2. Rohe DBC Typecodes erkennen: kurz (≤3 Zeichen) und kein Leerzeichen
        #    z.B. 'I8', 'CV', 'DA', 'TS', 'I ', 'D ' ...
        #    Aufgelöste DDL-Typen wären 'BIGINT', 'VARCHAR(...)' etc.
        if raw and (len(raw.rstrip()) <= 3 or raw.rstrip()[-1].isdigit()):
            ddl_type = td_typecode_to_ddl(
                raw,
                col.column_length,
                col.decimal_total_digits,
                col.decimal_fractional_digits,
            )
        else:
            ddl_type = raw

        base_type = ddl_type.upper().split('(')[0].strip()

        if base_type in ('CHAR', 'VARCHAR'):
            length = col.column_length or 255
            return f"VARCHAR({length})"

        elif base_type in ('DECIMAL', 'NUMERIC'):
            precision = col.decimal_total_digits or 18
            scale = col.decimal_fractional_digits or 0
            return f"DECIMAL({precision},{scale})"

        elif base_type in TERADATA_TO_TPT_TYPE:
            return TERADATA_TO_TPT_TYPE[base_type]

        else:
            logger.warning(f"Unknown type '{col.column_type}' for {col.column_name}, using VARCHAR(255)")
            return "VARCHAR(255)"
    
    def _build_odbc_operator(
        self,
        source_system: 'SourceSystemInfo',
        parameters: Dict[str, Any],
        columns: List[ColumnInfo]
    ) -> str:
        """Baut ODBC Reader Operator."""
        source_table = parameters.get('source_table', parameters['target_table'])
        
        # source_table kann bereits Schema.Table sein (z.B. "Person.PersonPhone")
        # In dem Fall nicht nochmal default_schema voranstellen
        if '.' in source_table:
            full_table_name = source_table  # Schon Schema.Table
        else:
            schema = source_system.default_schema or 'dbo'
            full_table_name = f"{schema}.{source_table}"
        
        # Build SELECT columns - SQL Server braucht [name] für reservierte Wörter
        # NEU: Nutze convert_expression falls vorhanden (z.B. für uniqueidentifier, datetime)
        select_cols = []
        for col in columns:
            if col.convert_expression:
                # CONVERT Expression mit Alias: CONVERT(VARCHAR(36), [rowguid]) AS rowguid
                select_cols.append(f"{col.convert_expression} AS {col.select_name}")
            else:
                select_cols.append(f'[{col.select_name}]')
        select_stmt = ', '.join(select_cols)
        
        # Credentials aus database.yml holen
        # source_system_id kann numerische ID (1) oder String ('ZEMIS') sein
        source_system_id = parameters.get('source_system_id', 'ZEMIS')
        
        # Wenn numerische ID, dann SOURCE_SYSTEM_CODE aus DB holen
        if isinstance(source_system_id, int) or (isinstance(source_system_id, str) and source_system_id.isdigit()):
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT SOURCE_SYSTEM_CODE FROM MDP01_META.META_SOURCE_SYSTEM 
                WHERE SOURCE_SYSTEM_ID = ?
            ''', (int(source_system_id),))
            row = cursor.fetchone()
            source_system_code = row[0] if row else 'ZEMIS'
        else:
            source_system_code = source_system_id
        
        source_cfg = self.config.get('source_systems', {}).get(source_system_code, {})
        
        # ODBC DSN aus database.yml - muss in /etc/odbc.ini konfiguriert sein
        odbc_dsn = source_cfg.get('odbc_dsn', 'SQL_Server_Wire_Protocol')
        odbc_user = source_cfg.get('user', 'sa')
        odbc_password = source_cfg.get('password', '')
        
        return f"""    DEFINE OPERATOR odbc_reader 
    TYPE ODBC 
    SCHEMA source_schema 
    ATTRIBUTES 
        (
        VARCHAR SelectStmt = 'SELECT {select_stmt} FROM {full_table_name}',
        VARCHAR PrivateLogName      = 'odbc_reader_log', 
        VARCHAR DSNName             = '{odbc_dsn}', 
        VARCHAR Username = '{odbc_user}', 
        VARCHAR UserPassword = '{odbc_password}' 
        );"""
    
    def _build_td_operator(self, parameters: Dict[str, Any]) -> str:
        """Baut Teradata Writer Operator."""
        target_db = parameters['target_database']
        target_table = parameters['target_table']
        suffix = parameters.get('staging_suffix', '_LOAD') if parameters.get('use_staging', True) else ''
        
        operator_type = parameters.get('tpt_operator_type', 'UPDATE')
        max_sessions = parameters.get('tpt_max_sessions', 4)
        min_sessions = parameters.get('tpt_min_sessions', 1)
        
        # Teradata Credentials aus database.yml
        td_cfg = self.config.get('teradata', {})
        tdpid = td_cfg.get('host', '192.168.114.21')
        td_user = td_cfg.get('user', 'dbc')
        td_password = td_cfg.get('password', 'dbc')
        
        return f"""    DEFINE OPERATOR td_writer 
    TYPE {operator_type} 
    SCHEMA source_schema 
    ATTRIBUTES 
        ( 
        VARCHAR PrivateLogName  = 'td_writer_log', 
        VARCHAR TdpId           = '{tdpid}', 
        VARCHAR UserName        = '{td_user}', 
        VARCHAR UserPassword    = '{td_password}', 
        VARCHAR WorkingDatabase = '{target_db}',
        VARCHAR TargetTable     = '{target_db}.{target_table}{suffix}', 
        VARCHAR LogTable        = '{target_db}.{target_table}{suffix}_log', 
        VARCHAR ErrorTable1     = '{target_db}.{target_table}{suffix}_err1', 
        VARCHAR ErrorTable2     = '{target_db}.{target_table}{suffix}_err2', 
        INTEGER MaxSessions     = {max_sessions}, 
        INTEGER MinSessions     = {min_sessions}, 
        VARCHAR ErrorList       = '3807', 
        VARCHAR InsertMissingUpdateRows = 'Y' 
        );"""
    
    def _load_datatype_mappings(self) -> Dict[str, Dict]:
        """
        Lädt Datatype Mappings aus META_DATATYPE_MAPPING.
        
        Returns:
            Dict mit source_datatype (lowercase) als Key
        """
        if self._datatype_mappings is not None:
            return self._datatype_mappings
        
        self._datatype_mappings = {}
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT source_datatype, target_datatype, target_max_length,
                       target_precision, target_scale, requires_cast, cast_expression
                FROM MDP01_META.META_DATATYPE_MAPPING
                WHERE source_system = 'SQL_SERVER'
                  AND is_active = 1
            """)
            
            for row in cursor.fetchall():
                source_type = row[0].lower().strip() if row[0] else ''
                self._datatype_mappings[source_type] = {
                    'target_datatype': row[1],
                    'target_max_length': row[2],
                    'target_precision': row[3],
                    'target_scale': row[4],
                    'requires_cast': row[5] == 1,
                    'cast_expression': row[6]
                }
            
            logger.info(f"Loaded {len(self._datatype_mappings)} datatype mappings from META_DATATYPE_MAPPING")
        except Exception as e:
            logger.warning(f"Could not load datatype mappings: {e}. Using fallback logic.")
            self._datatype_mappings = {}
        
        return self._datatype_mappings
    
    def _get_value_placeholder(self, col: ColumnInfo, mappings: Dict[str, Dict]) -> str:
        """
        Generiert den VALUE Placeholder für eine Spalte.
        
        Mit dem neuen JSON-Format ist die Logik vereinfacht:
        - CONVERT passiert bereits auf SQL Server Seite (via convert_expression)
        - Hier nur noch CAST für TIMESTAMP/DATE weil ODBC VARCHAR liefert
        """
        target_type = col.column_type.upper() if col.column_type else ''
        
        # CAST nur für TIMESTAMP/DATE weil ODBC diese als VARCHAR liefert
        if 'TIMESTAMP' in target_type:
            return f'CAST(:"{col.select_name}" AS {col.column_type})'
        elif target_type == 'DATE':
            return f'CAST(:"{col.select_name}" AS DATE)'
        
        # Alle anderen Typen: kein CAST nötig (CONVERT schon auf SQL Server Seite)
        return f':"{col.select_name}"'
    
    def _build_apply_statement(
        self,
        parameters: Dict[str, Any],
        columns: List[ColumnInfo]
    ) -> str:
        """Baut APPLY INSERT Statement mit Source->Target Mapping."""
        target_db = parameters['target_database']
        target_table = parameters['target_table']
        
        # Staging suffix - muss mit TargetTable übereinstimmen!
        suffix = parameters.get('staging_suffix', '_LOAD') if parameters.get('use_staging', True) else ''
        
        # Datatype Mappings laden
        mappings = self._load_datatype_mappings()
        
        # INSERT INTO: TARGET Namen (insert_name)
        col_names = [f'"{col.insert_name}"' for col in columns]
        col_list = ', '.join(col_names)
        
        # VALUES: SOURCE Namen mit CAST basierend auf META_DATATYPE_MAPPING
        placeholders = []
        for col in columns:
            placeholder = self._get_value_placeholder(col, mappings)
            placeholders.append(placeholder)
        placeholder_list = ', '.join(placeholders)
        
        return f"""    APPLY 
        ('INSERT INTO {target_db}.{target_table}{suffix} ({col_list}) VALUES ({placeholder_list});') 
    TO OPERATOR (td_writer) 
    SELECT * FROM OPERATOR (odbc_reader);"""
    
    def _assemble_script(
        self,
        job_name: str,
        schema_def: str,
        odbc_operator: str,
        td_operator: str,
        apply_stmt: str
    ) -> str:
        """Assembliert das komplette TPT Script."""
        return f"""USING CHARACTER SET UTF8
DEFINE JOB {job_name}
DESCRIPTION 'Load data for {job_name.replace("load_", "")}'
(
    /* ----------------------------------------------------------------------------- 
       Definition des SQL Server Source 
       -----------------------------------------------------------------------------*/ 
    DEFINE SCHEMA source_schema 
        ( 
{schema_def}
        ); 


    /* -----------------------------------------------------------------------------
       ODBC Operator für SQL Server Quelle 
       -----------------------------------------------------------------------------*/
{odbc_operator}


    /* ----------------------------------------------------------------------------- 
       UPDATE Operator für Teradata Ziel 
       -----------------------------------------------------------------------------*/ 
{td_operator}

    /* ----------------------------------------------------------------------------- 
       Execute 
       -----------------------------------------------------------------------------*/ 
{apply_stmt}
);
"""


# =============================================================================
# Orchestrator Wrapper Function
# =============================================================================

def generate_script(
    conn: 'teradatasql.TeradataConnection',
    parameters: Dict[str, Any],
    context: Dict[str, Any] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Generiert TPT Script aus Parametern.
    
    Diese Funktion wird vom Orchestrator aufgerufen wenn:
        STEP_CATEGORY    = 'TPT_GEN'
        PYTHON_MODULE    = 'tpt_generator'
        PYTHON_FUNCTION  = 'generate_script'
    
    Args:
        conn: Teradata Connection
        parameters: Dict mit source_system_id, source_table, target_database, target_table, columns
        context: Optional zusätzlicher Kontext
    
    Returns:
        Tuple (success: bool, result: Dict)
    """
    from .source_service import SourceSystemService
    
    try:
        # Source System Info holen
        source_system_id = parameters.get('source_system_id')
        if not source_system_id:
            return (False, {"error_message": "source_system_id nicht in parameters"})
        
        service = SourceSystemService()
        source_system = service.get_source_system(source_system_id)
        
        if not source_system:
            return (False, {"error_message": f"Source System {source_system_id} nicht gefunden"})
        
        # Konvertiere zu SourceSystemInfo
        from .tpt_executor import SourceSystemInfo
        source_info = SourceSystemInfo(
            source_system_id=source_system.source_system_id,
            source_system_name=source_system.source_system_name,
            source_system_code=source_system.source_system_code,
            source_type=source_system.source_type,
            odbc_dsn_name=source_system.odbc_dsn_name,
            default_schema=source_system.default_schema,
            credential_user_wallet=source_system.credential_user_wallet,
            credential_password_wallet=source_system.credential_password_wallet
        )
        
        # TPT Script generieren
        generator = TPTGenerator(conn)
        script_path = generator.generate(source_info, parameters)
        
        return (True, {
            "script_path": script_path,
            "message": f"TPT Script generiert: {script_path}"
        })
        
    except Exception as e:
        logger.error(f"TPT Script generation failed: {e}")
        return (False, {"error_message": str(e)})
