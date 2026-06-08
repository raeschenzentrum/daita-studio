"""
Source System Service
=====================

Service für externe Quellsysteme:
- Source Systems verwalten
- Tabellen/Spalten Discovery aus externen DBs
- TPT Job Erstellung

Autor: DWH MVP Team
Datum: 2026-03-18
"""
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    import teradatasql as td_module
    TeradataConnection = td_module.TeradataConnection
else:
    TeradataConnection = Any

import yaml

try:
    import teradatasql
except ImportError:
    teradatasql = None

try:
    import pymssql
except ImportError:
    pymssql = None

from ..models.source_models import (
    SourceSystem, SourceSystemCreate,
    SourceTable, SourceColumn, SourceTableList,
    TPTJobCreateRequest, TPTJobCreateResponse,
    TableImportStatus
)

logger = logging.getLogger(__name__)


# =============================================================================
# Data Type Mappings: Source → Teradata
# =============================================================================

MSSQL_TO_TERADATA = {
    # Integer Types
    'bigint': 'BIGINT',
    'int': 'INTEGER',
    'smallint': 'SMALLINT',
    'tinyint': 'BYTEINT',
    'bit': 'BYTEINT',
    
    # Decimal Types
    'decimal': 'DECIMAL',
    'numeric': 'DECIMAL',
    'money': 'DECIMAL(19,4)',
    'smallmoney': 'DECIMAL(10,4)',
    'float': 'FLOAT',
    'real': 'REAL',
    
    # String Types
    'char': 'CHAR',
    'varchar': 'VARCHAR',
    'nchar': 'CHAR',
    'nvarchar': 'VARCHAR',
    'text': 'CLOB',
    'ntext': 'CLOB',
    
    # Date/Time Types
    'date': 'DATE',
    'time': 'TIME',
    'datetime': 'TIMESTAMP(0)',
    'datetime2': 'TIMESTAMP(6)',
    'smalldatetime': 'TIMESTAMP(0)',
    'datetimeoffset': 'TIMESTAMP(6) WITH TIME ZONE',
    
    # Binary Types
    'binary': 'BYTE',
    'varbinary': 'VARBYTE',
    'image': 'BLOB',
    
    # Other
    'uniqueidentifier': 'CHAR(36)',
    'xml': 'CLOB',
}


class SourceSystemService:
    """Service für Source System Operations"""
    
    # Cache für Datatype-Mappings aus META_DATATYPE_MAPPING
    _datatype_mappings_cache: Dict[str, List[Dict]] = {}
    
    def __init__(self, config_path: str = None):
        """Initialisiert Service mit Datenbankverbindung."""
        if config_path is None:
            # Suche database.yml: backend/app/services -> backend -> metadaita/cfg
            service_dir = Path(__file__).parent
            install_dir = service_dir.parent.parent.parent  # metadaita/
            config_path = str(install_dir / "cfg" / "database.yml")
            
            if not Path(config_path).exists():
                raise FileNotFoundError(
                    f"database.yml nicht gefunden: {config_path}"
                )
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        self.config = config
        self.db_config = config['teradata']
    
    def _get_td_connection(self):
        """Erstellt Teradata Connection."""
        # Nur Connection-Parameter, nicht autocommit/transaction_mode/batch_size
        conn_params = {
            'host': self.db_config.get('host'),
            'user': self.db_config.get('user'),
            'password': self.db_config.get('password'),
        }
        return teradatasql.connect(**conn_params)
    
    # =========================================================================
    # Source System CRUD
    # =========================================================================
    
    def get_all_source_systems(self, active_only: bool = False) -> List[SourceSystem]:
        """Gibt alle Source Systems zurück."""
        conn = self._get_td_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                SOURCE_SYSTEM_ID, SOURCE_SYSTEM_NAME, SOURCE_SYSTEM_CODE,
                SOURCE_TYPE, HOST_NAME, PORT_NUMBER,
                DEFAULT_DATABASE, DEFAULT_SCHEMA, ODBC_DSN_NAME,
                CREDENTIAL_USER_WALLET, CREDENTIAL_PASSWORD_WALLET,
                IS_ACTIVE, BESCHREIBUNG, VERANTWORTLICHER, KONTAKT_EMAIL,
                CREATE_TIMESTAMP, LAST_ALTER_TIMESTAMP
            FROM MDP01_META.META_SOURCE_SYSTEM
        """
        
        if active_only:
            query += " WHERE IS_ACTIVE = 'Y'"
        
        query += " ORDER BY SOURCE_SYSTEM_CODE"
        
        cursor.execute(query)
        
        systems = []
        for row in cursor.fetchall():
            systems.append(SourceSystem(
                source_system_id=row[0],
                source_system_name=row[1],
                source_system_code=row[2],
                source_type=row[3],
                host_name=row[4],
                port_number=row[5],
                default_database=row[6],
                default_schema=row[7],
                odbc_dsn_name=row[8],
                credential_user_wallet=row[9],
                credential_password_wallet=row[10],
                is_active=row[11],
                beschreibung=row[12],
                verantwortlicher=row[13],
                kontakt_email=row[14],
                create_timestamp=row[15],
                last_alter_timestamp=row[16]
            ))
        
        conn.close()
        return systems
    
    def get_source_system(self, source_system_id: int) -> Optional[SourceSystem]:
        """Gibt ein spezifisches Source System zurück."""
        conn = self._get_td_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                SOURCE_SYSTEM_ID, SOURCE_SYSTEM_NAME, SOURCE_SYSTEM_CODE,
                SOURCE_TYPE, HOST_NAME, PORT_NUMBER,
                DEFAULT_DATABASE, DEFAULT_SCHEMA, ODBC_DSN_NAME,
                CREDENTIAL_USER_WALLET, CREDENTIAL_PASSWORD_WALLET,
                IS_ACTIVE, BESCHREIBUNG, VERANTWORTLICHER, KONTAKT_EMAIL,
                CREATE_TIMESTAMP, LAST_ALTER_TIMESTAMP
            FROM MDP01_META.META_SOURCE_SYSTEM
            WHERE SOURCE_SYSTEM_ID = ?
        """, (source_system_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return SourceSystem(
            source_system_id=row[0],
            source_system_name=row[1],
            source_system_code=row[2],
            source_type=row[3],
            host_name=row[4],
            port_number=row[5],
            default_database=row[6],
            default_schema=row[7],
            odbc_dsn_name=row[8],
            credential_user_wallet=row[9],
            credential_password_wallet=row[10],
            is_active=row[11],
            beschreibung=row[12],
            verantwortlicher=row[13],
            kontakt_email=row[14],
            create_timestamp=row[15],
            last_alter_timestamp=row[16]
        )
    
    # =========================================================================
    # Source Table Discovery
    # =========================================================================
    
    def discover_tables(
        self,
        source_system_id: int,
        schema_filter: Optional[str] = None
    ) -> SourceTableList:
        """
        Entdeckt Tabellen im externen Quellsystem.
        
        Args:
            source_system_id: ID des Source Systems
            schema_filter: Optional Schema-Filter (default: default_schema)
        
        Returns:
            Liste von Tabellen mit Metadaten
        """
        # Source System laden
        source_system = self.get_source_system(source_system_id)
        if not source_system:
            raise ValueError(f"Source System {source_system_id} not found")
        
        schema = schema_filter or source_system.default_schema or 'dbo'
        
        if source_system.source_type == 'MSSQL':
            tables = self._discover_mssql_tables(source_system, schema)
        else:
            raise NotImplementedError(
                f"Discovery for {source_system.source_type} not implemented"
            )
        
        return SourceTableList(
            source_system_id=source_system_id,
            source_system_code=source_system.source_system_code,
            tables=tables,
            total_count=len(tables)
        )
    
    def _discover_mssql_tables(
        self,
        source_system: SourceSystem,
        schema: str
    ) -> List[SourceTable]:
        """Entdeckt Tabellen in MS SQL Server via pymssql."""
        if pymssql is None:
            raise ImportError("pymssql not installed - run: pip install pymssql")
        
        conn = self._get_mssql_connection(source_system)
        cursor = conn.cursor()
        
        logger.info(f"Discovering tables in {source_system.source_system_code}.{schema}")
        
        try:
            # Tabellen abfragen
            cursor.execute("""
                SELECT 
                    TABLE_SCHEMA,
                    TABLE_NAME,
                    TABLE_TYPE
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = %s
                  AND TABLE_TYPE IN ('BASE TABLE', 'VIEW')
                ORDER BY TABLE_NAME
            """, (schema,))
            
            tables = []
            for row in cursor.fetchall():
                table = SourceTable(
                    table_schema=row[0],
                    table_name=row[1],
                    table_type=row[2]
                )
                tables.append(table)
            
            conn.close()
            logger.info(f"Discovered {len(tables)} tables in {schema}")
            return tables
            
        except Exception as e:
            logger.error(f"MSSQL Discovery failed: {e}")
            raise
    
    def discover_schemas(self, source_system_id: int) -> List[str]:
        """
        Entdeckt alle Schemas im externen Quellsystem.
        
        Args:
            source_system_id: ID des Source Systems
        
        Returns:
            Liste von Schema-Namen
        """
        source_system = self.get_source_system(source_system_id)
        if not source_system:
            raise ValueError(f"Source System {source_system_id} not found")
        
        if source_system.source_type == 'MSSQL':
            return self._discover_mssql_schemas(source_system)
        else:
            raise NotImplementedError(
                f"Schema discovery for {source_system.source_type} not implemented"
            )
    
    def _discover_mssql_schemas(self, source_system: SourceSystem) -> List[str]:
        """Entdeckt alle Schemas in MS SQL Server."""
        if pymssql is None:
            raise ImportError("pymssql not installed")
        
        conn = self._get_mssql_connection(source_system)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT DISTINCT TABLE_SCHEMA 
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
                ORDER BY TABLE_SCHEMA
            """)
            
            schemas = [row[0] for row in cursor.fetchall()]
            conn.close()
            logger.info(f"Discovered {len(schemas)} schemas in {source_system.source_system_code}")
            return schemas
            
        except Exception as e:
            logger.error(f"Schema discovery failed: {e}")
            raise
    
    def _get_mssql_connection(self, source_system: SourceSystem):
        """Erstellt pymssql Connection zu MS SQL Server."""
        source_code = source_system.source_system_code.strip()
        
        # Credentials aus database.yml laden
        source_config = self.config.get('source_systems', {}).get(source_code)
        
        if not source_config:
            raise ValueError(
                f"Source System '{source_code}' nicht in database.yml konfiguriert. "
                f"Füge unter 'source_systems:' einen Eintrag für '{source_code}' hinzu."
            )
        
        host = source_config.get('host')
        port = source_config.get('port', 1433)
        database = source_config.get('database', 'master')
        user = source_config.get('user')
        password = source_config.get('password')
        
        if not host:
            raise ValueError(f"'host' nicht konfiguriert für {source_code} in database.yml")
        
        if not user or not password:
            raise ValueError(
                f"'user' und 'password' nicht konfiguriert für {source_code} in database.yml"
            )
        
        logger.info(f"Connecting to MSSQL: {host}:{port}/{database} as {user}")
        
        return pymssql.connect(
            server=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
    
    def get_table_columns(
        self,
        source_system_id: int,
        table_name: str,
        schema: Optional[str] = None
    ) -> List[SourceColumn]:
        """
        Holt Spalten für eine Tabelle aus dem externen System.
        
        Args:
            source_system_id: ID des Source Systems
            table_name: Tabellenname
            schema: Schema (default: default_schema)
        
        Returns:
            Liste von Spalten mit Datentypen
        """
        source_system = self.get_source_system(source_system_id)
        if not source_system:
            raise ValueError(f"Source System {source_system_id} not found")
        
        schema = schema or source_system.default_schema or 'dbo'
        
        if source_system.source_type == 'MSSQL':
            return self._get_mssql_columns(source_system, schema, table_name)
        else:
            raise NotImplementedError(
                f"Column discovery for {source_system.source_type} not implemented"
            )
    
    def _get_mssql_columns(
        self,
        source_system: SourceSystem,
        schema: str,
        table_name: str
    ) -> List[SourceColumn]:
        """Holt Spalten aus MS SQL Server via pymssql."""
        conn = self._get_mssql_connection(source_system)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COLUMN_NAME,
                DATA_TYPE,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                NUMERIC_SCALE,
                IS_NULLABLE,
                ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """, (schema, table_name))
        
        columns = []
        for row in cursor.fetchall():
            # Mapping aus META_DATATYPE_MAPPING holen
            td_type, tpt_multiplier, convert_template = self._map_to_teradata_type(
                row[1], row[2], row[3], row[4]
            )
            
            col = SourceColumn(
                column_name=row[0],
                data_type=row[1],
                max_length=row[2],
                precision=row[3],
                scale=row[4],
                is_nullable=(row[5] == 'YES'),
                ordinal_position=row[6],
                td_data_type=td_type,
                tpt_schema_multiplier=tpt_multiplier,
                convert_template=convert_template
            )
            columns.append(col)
        
        conn.close()
        return columns
    
    def _load_datatype_mappings(self, source_system: str = 'SQL_SERVER') -> List[Dict]:
        """
        Lädt Datatype-Mappings aus META_DATATYPE_MAPPING Tabelle.
        
        Cached die Ergebnisse pro Source System.
        
        Args:
            source_system: Source System Code (z.B. 'SQL_SERVER')
        
        Returns:
            Liste von Mapping-Dictionaries
        """
        # Cache prüfen
        if source_system in self._datatype_mappings_cache:
            return self._datatype_mappings_cache[source_system]
        
        conn = self._get_td_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    SOURCE_DATATYPE,
                    SOURCE_MAX_LENGTH,
                    SOURCE_PRECISION,
                    SOURCE_SCALE,
                    TARGET_DATATYPE,
                    TARGET_MAX_LENGTH,
                    TARGET_PRECISION,
                    TARGET_SCALE,
                    TPT_SCHEMA_MULTIPLIER,
                    CONVERT_TEMPLATE,
                    TYPE_FORMAT_TEMPLATE
                FROM MDP01_META.META_DATATYPE_MAPPING
                WHERE SOURCE_SYSTEM = ?
                  AND IS_ACTIVE = 1
                ORDER BY 
                    SOURCE_DATATYPE,
                    COALESCE(SOURCE_MAX_LENGTH, 0) DESC
            """, (source_system,))
            
            mappings = []
            for row in cursor.fetchall():
                mappings.append({
                    'source_datatype': row[0].lower() if row[0] else None,
                    'source_max_length': row[1],
                    'source_precision': row[2],
                    'source_scale': row[3],
                    'target_datatype': row[4],
                    'target_max_length': row[5],
                    'target_precision': row[6],
                    'target_scale': row[7],
                    'tpt_schema_multiplier': row[8] or 1,
                    'convert_template': row[9],
                    'type_format_template': row[10] or '{base}'  # Default: nur Basistyp
                })
            
            self._datatype_mappings_cache[source_system] = mappings
            logger.info(f"Loaded {len(mappings)} datatype mappings for {source_system}")
            return mappings
            
        finally:
            conn.close()
    
    def _map_to_teradata_type(
        self,
        mssql_type: str,
        max_length: Optional[int],
        precision: Optional[int],
        scale: Optional[int],
        source_system: str = 'SQL_SERVER'
    ) -> Tuple[str, int, Optional[str]]:
        """
        Mappt MS SQL Datentyp auf Teradata Datentyp via META_DATATYPE_MAPPING.
        
        Rein datengetrieben - keine Hardcoded-Logik für einzelne Datentypen!
        Alles wird aus META_DATATYPE_MAPPING gesteuert.
        
        Args:
            mssql_type: SQL Server Datentyp (z.B. 'nvarchar', 'int')
            max_length: Maximale Länge (Zeichen, nicht Bytes)
            precision: Numerische Precision
            scale: Numerische Scale
            source_system: Source System Code
        
        Returns:
            Tuple (td_type, tpt_multiplier, convert_template)
        """
        mssql_type_lower = mssql_type.lower()
        
        # Lade Mappings aus DB
        mappings = self._load_datatype_mappings(source_system)
        
        # Finde passendes Mapping (erstes Match gewinnt)
        mapping = None
        for m in mappings:
            if m['source_datatype'] == mssql_type_lower:
                mapping = m
                break
        
        # Fallback wenn kein Mapping gefunden
        if not mapping:
            logger.warning(f"No mapping found for {mssql_type}, using VARCHAR(255)")
            return ('VARCHAR(255)', 1, None)
        
        # Werte aus Mapping extrahieren
        target_base = mapping['target_datatype']
        multiplier = mapping['tpt_schema_multiplier'] or 1
        convert_template = mapping['convert_template']
        target_max = mapping['target_max_length']
        target_prec = mapping['target_precision']
        target_scale = mapping['target_scale']
        type_format = mapping['type_format_template']
        
        # Ziel-Typ zusammenbauen - rein template-basiert!
        target_type = self._build_target_type(
            type_format_template=type_format,
            target_base=target_base,
            source_length=max_length,
            source_precision=precision,
            source_scale=scale,
            multiplier=multiplier,
            target_max_length=target_max,
            target_precision=target_prec,
            target_scale=target_scale
        )
        
        return (target_type, multiplier, convert_template)
    
    def _build_target_type(
        self,
        type_format_template: str,
        target_base: str,
        source_length: Optional[int],
        source_precision: Optional[int],
        source_scale: Optional[int],
        multiplier: int,
        target_max_length: Optional[int],
        target_precision: Optional[int],
        target_scale: Optional[int]
    ) -> str:
        """
        Baut den vollständigen Teradata-Datentyp via Template-Substitution.
        
        100% datengetrieben - KEINE if-Bedingungen für Datentypen!
        Das Template kommt aus META_DATATYPE_MAPPING.TYPE_FORMAT_TEMPLATE.
        
        Templates:
        - '{base}'                    → INTEGER, BIGINT, DATE, ...
        - '{base}({length})'          → VARCHAR(200), CHAR(10), ...
        - '{base}({precision})'       → TIMESTAMP(6), TIME(3), ...
        - '{base}({precision},{scale})' → DECIMAL(18,2), ...
        """
        # Länge berechnen: source_length * multiplier (mit Obergrenze)
        calc_length = 0
        if source_length and source_length > 0:
            calc_length = source_length * multiplier
            if target_max_length:
                calc_length = min(calc_length, target_max_length)
            calc_length = min(calc_length, 64000)  # Teradata Maximum
        elif target_max_length:
            calc_length = target_max_length
        
        # Precision/Scale: Source-Werte oder Target-Defaults
        calc_precision = source_precision or target_precision or target_max_length or 6
        calc_scale = source_scale if source_scale is not None else (target_scale or 0)
        
        # Template-Substitution - keine if-Bedingungen für Typen!
        result = type_format_template.format(
            base=target_base,
            length=calc_length,
            precision=calc_precision,
            scale=calc_scale
        )
        
        return result
    
    # =========================================================================
    # TPT Job Creation
    # =========================================================================
    
    def create_tpt_job(
        self,
        request: TPTJobCreateRequest
    ) -> TPTJobCreateResponse:
        """
        Erstellt einen kompletten TPT Load Job.
        
        Erstellt:
        - META_ETL_JOB Eintrag
        - META_ETL_JOB_STEP mit TPT_LOAD Step
        - Optional: META_TABLE + META_COLUMN Einträge
        
        Args:
            request: TPTJobCreateRequest mit allen Parametern
        
        Returns:
            TPTJobCreateResponse mit Job-Details
        """
        logger.info(f"Creating TPT Job for {request.source_table}")
        
        # Source System und Spalten laden
        source_system = self.get_source_system(request.source_system_id)
        if not source_system:
            raise ValueError(f"Source System {request.source_system_id} not found")
        
        # Tabellen/Schema parsen
        parts = request.source_table.split('.')
        if len(parts) == 2:
            source_schema, source_table_name = parts
        else:
            source_schema = source_system.default_schema or 'dbo'
            source_table_name = request.source_table
        
        # Spalten vom Source System holen
        columns = self.get_table_columns(
            request.source_system_id, 
            source_table_name, 
            source_schema
        )
        
        if not columns:
            raise ValueError(f"No columns found for {source_schema}.{source_table_name}")
        
        # Target Table Name
        target_table = request.target_table or source_table_name
        job_name = request.job_name or f"load_{target_table}"
        
        # Teradata Connection
        conn = self._get_td_connection()
        cursor = conn.cursor()
        
        try:
            # 1. Source-Tabelle registrieren (externes System in META_TABLE)
            source_db_name = f"EXT_{source_system.source_system_code.strip()}"
            source_table_id = self._register_table_metadata(
                cursor, source_db_name, source_table_name, columns, is_external=True
            )
            
            # 2. Target-Tabelle registrieren (optional, aber empfohlen)
            target_table_id = source_table_id  # Default: gleiche ID
            if request.register_in_meta_table:
                target_table_id = self._register_table_metadata(
                    cursor, request.target_database, target_table, columns, is_external=False
                )
            
            # 3. META_ETL_JOB erstellen
            # PRÜFUNG: Job-Name bereits vergeben?
            cursor.execute("SELECT ETL_JOB_ID FROM MDP01_META.META_ETL_JOB WHERE JOB_NAME = ?", [job_name])
            existing_job = cursor.fetchone()
            if existing_job:
                raise ValueError(f"Job mit Namen '{job_name}' existiert bereits (ID: {existing_job[0]})")
            
            cursor.execute("""
                SELECT COALESCE(MAX(ETL_JOB_ID), 0) + 1 FROM MDP01_META.META_ETL_JOB
            """)
            new_job_id = cursor.fetchone()[0]
            
            cursor.execute("""
                INSERT INTO MDP01_META.META_ETL_JOB (
                    ETL_JOB_ID, JOB_NAME, JOB_TYPE,
                    SOURCE_TABLE_ID, TARGET_TABLE_ID,
                    SOURCE_LAYER_ID, TARGET_LAYER_ID,
                    IS_ACTIVE, BESCHREIBUNG,
                    CREATED_BY, CREATE_TIMESTAMP, 
                    MODIFIED_BY, LAST_ALTER_TIMESTAMP
                ) VALUES (
                    ?, ?, 'TPT_LOAD',
                    ?, ?,
                    1, 1,
                    'Y', ?,
                    USER, CURRENT_TIMESTAMP(6),
                    USER, CURRENT_TIMESTAMP(6)
                )
            """, (
                new_job_id,
                job_name,
                source_table_id,
                target_table_id,
                request.beschreibung or f"TPT Load von {source_system.source_system_code}.{source_table_name}"
            ))
            
            # 3. META_ETL_JOB_STEP erstellen (TPT_LOAD Step)
            
            # Column Mappings verarbeiten: entweder vom Request oder vom Source
            if request.column_mappings:
                # Benutzer hat eigene Mappings definiert
                columns_for_tpt = []
                for m in request.column_mappings:
                    col_entry = {
                        "source_name": m.source_column,
                        "target_name": m.target_column,
                        "source_type": m.source_type,
                        "td_type": m.target_type,
                        "nullable": True
                    }
                    # TPT-spezifische Felder wenn vorhanden
                    if m.tpt_schema_type:
                        col_entry["tpt_schema_type"] = m.tpt_schema_type
                    if m.convert_expression:
                        col_entry["convert_expression"] = m.convert_expression
                    columns_for_tpt.append(col_entry)
            else:
                # Standard: Source Name = Target Name + TPT-Felder aus DB-Mapping
                columns_for_tpt = []
                for col in columns:
                    col_entry = {
                        "source_name": col.column_name,
                        "target_name": col.column_name,
                        "source_type": col.data_type,
                        "td_type": col.td_data_type,
                        "nullable": col.is_nullable
                    }
                    # TPT-spezifische Felder aus META_DATATYPE_MAPPING
                    # CHARACTER_MAXIMUM_LENGTH ist bereits in Zeichen (nicht Bytes)
                    source_len = col.max_length or 255
                    
                    # Effektive Länge für TPT Schema berechnen
                    # Bei CONVERT mit fester Länge (z.B. VARCHAR(30)) diese Länge verwenden
                    # Bei CONVERT mit {len} Platzhalter die source_len verwenden
                    effective_len = source_len
                    if col.convert_template and 'VARCHAR(' in col.convert_template:
                        import re
                        # Suche nach fester Länge: VARCHAR(30) aber nicht VARCHAR({len})
                        match = re.search(r'VARCHAR\((\d+)\)', col.convert_template)
                        if match:
                            effective_len = int(match.group(1))  # Feste Länge aus CONVERT
                    
                    if col.tpt_schema_multiplier and col.tpt_schema_multiplier > 1:
                        # TPT Schema Type berechnen (VARCHAR(effective_len * multiplier))
                        tpt_len = min(effective_len * col.tpt_schema_multiplier, 64000)
                        col_entry["tpt_schema_type"] = f"VARCHAR({tpt_len})"
                    if col.convert_template:
                        # convert_template hat Platzhalter: [{col}] für Spaltennamen, {len} für Länge
                        expr = col.convert_template.replace('[{col}]', f'[{col.column_name}]')
                        expr = expr.replace('{len}', str(source_len))
                        col_entry["convert_expression"] = expr
                    columns_for_tpt.append(col_entry)
            
            parameters = {
                "source_system_id": request.source_system_id,
                "source_table": f"{source_schema}.{source_table_name}",
                "target_database": request.target_database,
                "target_table": target_table,
                "tpt_generate": True,
                "tpt_operator_type": request.tpt_operator_type,
                "tpt_max_sessions": request.tpt_max_sessions,
                "tpt_min_sessions": request.tpt_min_sessions,
                "use_staging": request.use_staging,
                "staging_suffix": request.staging_suffix,
                # Columns für TPT Generator mit Source/Target Mapping
                "columns": columns_for_tpt
            }
            
            # 5 Job-Steps erstellen
            job_steps = [
                {
                    "step_order": 10,
                    "step_name": f"TPT Cleanup {source_table_name}",
                    "step_category": "CLEANUP",
                    "python_module": "tpt_executor",
                    "python_function": "cleanup_tpt",
                    "is_critical": "N",
                    "beschreibung": f"Bereinigt TPT-Artefakte: Drop _ET/_UV/_WT/_LG Tabellen, Release MLOAD, Delete Checkpoints"
                },
                {
                    "step_order": 20,
                    "step_name": f"Drop Tables {source_table_name}",
                    "step_category": "DDL",
                    "python_module": "ddl_executor",
                    "python_function": "drop_tables",
                    "is_critical": "N",
                    "beschreibung": f"Löscht bestehende Target-Tabellen (optional)"
                },
                {
                    "step_order": 30,
                    "step_name": f"Create Tables {source_table_name}",
                    "step_category": "DDL",
                    "python_module": "ddl_executor",
                    "python_function": "create_tables",
                    "is_critical": "Y",
                    "beschreibung": f"Erstellt Target- und Load-Tabellen"
                },
                {
                    "step_order": 40,
                    "step_name": f"Generate TPT {source_table_name}",
                    "step_category": "TPT_GEN",
                    "python_module": "tpt_generator",
                    "python_function": "generate_script",
                    "is_critical": "Y",
                    "beschreibung": f"Generiert TPT-Script aus Template"
                },
                {
                    "step_order": 50,
                    "step_name": f"Execute TPT {source_table_name}",
                    "step_category": "TPT_EXEC",
                    "python_module": "tpt_executor",
                    "python_function": "run_tpt",
                    "is_critical": "Y",
                    "beschreibung": f"Führt TPT-Load von {source_system.source_system_code}.{source_table_name} aus"
                }
            ]
            
            for step in job_steps:
                cursor.execute("""
                    INSERT INTO MDP01_META.META_ETL_JOB_STEP (
                        ETL_JOB_ID, STEP_NAME, STEP_ORDER, STEP_CATEGORY,
                        PYTHON_MODULE, PYTHON_FUNCTION, PARAMETERS,
                        IS_CRITICAL, IS_ACTIVE, BESCHREIBUNG,
                        CREATED_BY, CREATE_TIMESTAMP,
                        MODIFIED_BY, LAST_ALTER_TIMESTAMP
                    ) VALUES (
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, 'Y', ?,
                        USER, CURRENT_TIMESTAMP(6),
                        USER, CURRENT_TIMESTAMP(6)
                    )
                """, (
                    new_job_id,
                    step["step_name"],
                    step["step_order"],
                    step["step_category"],
                    step["python_module"],
                    step["python_function"],
                    json.dumps(parameters),
                    step["is_critical"],
                    step["beschreibung"]
                ))
            
            conn.commit()
            
            logger.info(f"Created TPT Job: {job_name} (ID: {new_job_id}) with 5 steps")
            
            return TPTJobCreateResponse(
                success=True,
                etl_job_id=new_job_id,
                job_name=job_name,
                steps_created=5,
                message=f"TPT Job '{job_name}' erfolgreich erstellt mit 5 Steps und {len(columns)} Spalten"
            )
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating TPT Job: {e}")
            raise
        finally:
            conn.close()
    
    def _register_table_metadata(
        self,
        cursor,
        database_name: str,
        table_name: str,
        columns: List[SourceColumn],
        is_external: bool = False
    ) -> int:
        """Registriert Tabelle und Spalten in META_TABLE/META_COLUMN."""
        
        # Database ID finden oder erstellen
        cursor.execute("""
            SELECT DATABASE_ID FROM MDP01_META.META_DATABASE
            WHERE DATABASE_NAME = ?
        """, (database_name,))
        row = cursor.fetchone()
        
        if row:
            database_id = row[0]
        else:
            # Database erstellen
            cursor.execute("""
                SELECT COALESCE(MAX(DATABASE_ID), 0) + 1 FROM MDP01_META.META_DATABASE
            """)
            database_id = cursor.fetchone()[0]
            
            # LAYER_ID: 0 für externe Systeme, 1 für Teradata
            layer_id = 0 if is_external else 1
            cursor.execute("""
                INSERT INTO MDP01_META.META_DATABASE (
                    DATABASE_ID, DATABASE_NAME, LAYER_ID,
                    ERSTERFASSUNGSDATUM, AENDERUNGSDATUM
                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
            """, (database_id, database_name, layer_id))
            
            logger.info(f"Registered database {database_name} (ID: {database_id}, external={is_external})")
        
        # Prüfen ob Tabelle schon existiert
        cursor.execute("""
            SELECT TABLE_ID FROM MDP01_META.META_TABLE
            WHERE DATABASE_ID = ? AND TABLE_NAME = ?
        """, (database_id, table_name))
        row = cursor.fetchone()
        
        if row:
            table_id = row[0]
            logger.info(f"Table {table_name} already registered (ID: {table_id})")
        else:
            # Table erstellen
            cursor.execute("""
                SELECT COALESCE(MAX(TABLE_ID), 0) + 1 FROM MDP01_META.META_TABLE
            """)
            table_id = cursor.fetchone()[0]
            
            # LAYER_ID: 0 für externe Systeme, 1 für Teradata
            layer_id = 0 if is_external else 1
            cursor.execute("""
                INSERT INTO MDP01_META.META_TABLE (
                    TABLE_ID, DATABASE_ID, TABLE_NAME, LAYER_ID,
                    TABLE_KIND, CREATE_TIMESTAMP, LAST_ALTER_TIMESTAMP
                ) VALUES (?, ?, ?, ?, 'T', CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
            """, (table_id, database_id, table_name, layer_id))
            
            logger.info(f"Registered table {table_name} (ID: {table_id})")
        
        # Columns registrieren (wenn noch nicht vorhanden)
        for col in columns:
            cursor.execute("""
                SELECT COLUMN_ID FROM MDP01_META.META_COLUMN
                WHERE TABLE_ID = ? AND COLUMN_NAME = ?
            """, (table_id, col.column_name))
            
            if not cursor.fetchone():
                cursor.execute("""
                    SELECT COALESCE(MAX(COLUMN_ID), 0) + 1 FROM MDP01_META.META_COLUMN
                """)
                column_id = cursor.fetchone()[0]
                
                cursor.execute("""
                    INSERT INTO MDP01_META.META_COLUMN (
                        COLUMN_ID, TABLE_ID, COLUMN_NAME, COLUMN_POSITION,
                        DATATYPE_ID, COLUMN_TYPE, NULLABLE,
                        ERSTERFASSUNGSDATUM, AENDERUNGSDATUM
                    ) VALUES (?, ?, ?, ?, 1, ?, ?, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
                """, (
                    column_id, table_id, col.column_name, col.ordinal_position,
                    col.td_data_type, 'Y' if col.is_nullable else 'N'
                ))
        
        return table_id
    
    # =========================================================================
    # Import Status
    # =========================================================================
    
    def get_table_import_status(
        self,
        source_system_id: int,
        tables: List[str]
    ) -> List[TableImportStatus]:
        """
        Gibt Import-Status für mehrere Tabellen zurück.
        
        Zeigt an ob Tabelle:
        - In META_TABLE registriert ist
        - TPT Job existiert
        - Letzter Load Status
        """
        conn = self._get_td_connection()
        cursor = conn.cursor()
        
        results = []
        for table_name in tables:
            # Prüfe ob TPT Job existiert
            cursor.execute("""
                SELECT j.ETL_JOB_ID, r.STATUS, r.END_TIME
                FROM MDP01_META.META_ETL_JOB j
                LEFT JOIN (
                    SELECT ETL_JOB_ID, STATUS, END_TIME,
                           ROW_NUMBER() OVER (PARTITION BY ETL_JOB_ID ORDER BY END_TIME DESC) as rn
                    FROM MDP01_META.META_ETL_JOB_RUN
                ) r ON j.ETL_JOB_ID = r.ETL_JOB_ID AND r.rn = 1
                WHERE j.JOB_TYPE = 'TPT_LOAD'
                  AND j.JOB_NAME LIKE ?
            """, (f"%{table_name}%",))
            
            row = cursor.fetchone()
            
            status = TableImportStatus(
                source_table=table_name,
                is_registered=False,
                has_tpt_job=row is not None,
                etl_job_id=row[0] if row else None,
                last_load_status=row[1] if row else None,
                last_load_time=row[2] if row else None
            )
            results.append(status)
        
        conn.close()
        return results


# =============================================================================
# Dependency Injection
# =============================================================================

_source_service: Optional[SourceSystemService] = None


def get_source_service() -> SourceSystemService:
    """Dependency Injection für FastAPI."""
    global _source_service
    if _source_service is None:
        _source_service = SourceSystemService()
    return _source_service
