"""
Template Service
================

Verwaltung von Job- und Step-Templates.
Ermöglicht wiederverwendbare ETL-Patterns.

Autor: metadaita Team
Datum: 2026-04-15
"""
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

import teradatasql
import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models
# =============================================================================

class JobTemplate(BaseModel):
    """Job-Vorlage"""
    template_id: int
    template_name: str
    template_code: str
    source_layer_id: Optional[int] = None
    target_layer_id: Optional[int] = None
    job_type: str
    category: Optional[str] = None
    tags: Optional[str] = None
    beschreibung: Optional[str] = None
    usage_notes: Optional[str] = None
    is_active: str = 'Y'
    # Defaults
    default_primary_key_columns: Optional[str] = None
    default_hash_columns: Optional[str] = None
    default_valid_from_column: Optional[str] = None
    default_valid_to_column: Optional[str] = None
    default_is_current_column: Optional[str] = None


class StepTemplate(BaseModel):
    """Step-Vorlage"""
    step_template_id: int
    template_id: Optional[int] = None  # NULL = eigenständiger Baustein
    step_name: str
    step_code: Optional[str] = None
    step_order: int
    step_category: str
    sql_template_path: Optional[str] = None
    sql_inline: Optional[str] = None
    default_parameters: Optional[Dict[str, Any]] = None
    required_parameters: Optional[str] = None
    optional_parameters: Optional[str] = None
    beschreibung: Optional[str] = None
    is_active: str = 'Y'


class CreateJobTemplateRequest(BaseModel):
    """Request für Template-Erstellung"""
    template_name: str
    template_code: str
    job_type: str
    source_layer_id: Optional[int] = None
    target_layer_id: Optional[int] = None
    category: Optional[str] = None
    beschreibung: Optional[str] = None


class CreateStepTemplateRequest(BaseModel):
    """Request für Step-Template-Erstellung"""
    template_id: Optional[int] = None  # NULL = eigenständiger Baustein
    step_name: str
    step_code: Optional[str] = None
    step_order: int = 10
    step_category: str
    sql_template_path: Optional[str] = None
    sql_inline: Optional[str] = None
    default_parameters: Optional[Dict[str, Any]] = None
    required_parameters: Optional[str] = None
    beschreibung: Optional[str] = None


class CreateJobFromTemplateRequest(BaseModel):
    """Request: Job aus Template erstellen"""
    template_id: Optional[int] = None  # Wird aus URL übernommen
    job_name: str
    source_table_id: int
    # Target: entweder ID oder Name (für neue Tabellen)
    target_table_id: Optional[int] = None
    target_table_name: Optional[str] = None
    target_layer: Optional[str] = None  # z.B. "DISC", "REUS", etc.
    source_table_name: Optional[str] = None  # Für Anzeige/Logging
    # Parameter-Substitution + Spaltenwahl (AF-011)
    parameters: Optional[Dict[str, Any]] = None  # z.B. {"select_columns": [...], "primary_key_columns": [...]}


# =============================================================================
# Template Service
# =============================================================================

class TemplateService:
    """
    Service für Template-Verwaltung.
    
    Verantwortlichkeiten:
    - Job-Templates listen und verwalten
    - Step-Templates listen und verwalten
    - Job aus Template erstellen (mit Step-Kopie)
    - Einzelnen Step aus Template zu Job hinzufügen
    """
    
    def __init__(self):
        """Initialisiert Service mit DB-Config und Parameter-Regeln"""
        cfg_dir = Path("/home/tdops/ps_toolbox/PS_ROOT/subsystem/metadaita/cfg")
        database_yml = cfg_dir / "database.yml"
        
        with open(database_yml, 'r') as f:
            db_config = yaml.safe_load(f)
        
        self.db_config = db_config.get('teradata', {})
        
        # Parameter-Regeln laden
        param_rules_yml = cfg_dir / "parameter_rules.yml"
        if param_rules_yml.exists():
            with open(param_rules_yml, 'r') as f:
                self.param_rules = yaml.safe_load(f)
        else:
            logger.warning("parameter_rules.yml nicht gefunden - Default-Regeln verwenden")
            self.param_rules = {
                'prefixes': {'key_table': 'KEY_', 'staging': 'temp_'},
                'suffixes': {'staging': '_staging'},
                'core_name_extraction': {'remove_prefixes': ['TAAA_', 'TAAS_', 'TAA_', 'zas_', 'ZAS_']}
            }
    
    def _get_connection(self) -> teradatasql.TeradataConnection:
        """Erstellt neue DB Connection"""
        return teradatasql.connect(
            host=self.db_config.get('host'),
            user=self.db_config.get('user'),
            password=self.db_config.get('password')
        )
    
    def _load_scd2_column_names(self) -> Dict[str, str]:
        """
        Lädt SCD2-Spaltennamen aus Config (cfg/parameter_rules.yml).
        
        Returns:
            Dict mit: surrogate_key, valid_from, valid_to, is_current, 
                      record_hash, created_timestamp, last_updated_timestamp,
                      created_by, last_updated_by
        """
        # Defaults falls Config nicht verfügbar
        defaults = {
            'surrogate_key': 'SURROGATE_KEY',
            'valid_from': 'VALID_FROM',
            'valid_to': 'VALID_TO',
            'is_current': 'IS_CURRENT',
            'record_hash': 'RECORD_HASH',
            'created_timestamp': 'CREATED_TIMESTAMP',
            'last_updated_timestamp': 'LAST_UPDATED_TIMESTAMP',
            'created_by': 'CREATED_BY',
            'last_updated_by': 'LAST_UPDATED_BY'
        }
        
        scd2_config = self.param_rules.get('scd2_technical_columns', {})
        
        # Defaults mit Config überschreiben
        for key in defaults:
            if key in scd2_config:
                defaults[key] = scd2_config[key]
        
        return defaults
    
    # =========================================================================
    # Job Templates
    # =========================================================================
    
    def get_job_templates(
        self, 
        source_layer_id: Optional[int] = None,
        target_layer_id: Optional[int] = None,
        job_type: Optional[str] = None
    ) -> List[JobTemplate]:
        """
        Liste aller Job-Templates.
        
        Optional filtern nach:
        - source_layer_id: Für welchen Source-Layer
        - target_layer_id: Für welchen Target-Layer  
        - job_type: z.B. "SCD_TYPE_2"
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            sql = """
                SELECT 
                    TEMPLATE_ID,
                    TEMPLATE_NAME,
                    TEMPLATE_CODE,
                    SOURCE_LAYER_ID,
                    TARGET_LAYER_ID,
                    JOB_TYPE,
                    CATEGORY,
                    TAGS,
                    BESCHREIBUNG,
                    USAGE_NOTES,
                    IS_ACTIVE,
                    DEFAULT_PRIMARY_KEY_COLUMNS,
                    DEFAULT_HASH_COLUMNS,
                    DEFAULT_VALID_FROM_COLUMN,
                    DEFAULT_VALID_TO_COLUMN,
                    DEFAULT_IS_CURRENT_COLUMN
                FROM MDP01_META.META_ETL_JOB_TEMPLATE
                WHERE IS_ACTIVE = 'Y'
            """
            
            conditions = []
            params = []
            
            if source_layer_id is not None:
                conditions.append("(SOURCE_LAYER_ID = ? OR SOURCE_LAYER_ID IS NULL)")
                params.append(source_layer_id)
            
            if target_layer_id is not None:
                conditions.append("(TARGET_LAYER_ID = ? OR TARGET_LAYER_ID IS NULL)")
                params.append(target_layer_id)
            
            if job_type:
                conditions.append("JOB_TYPE = ?")
                params.append(job_type)
            
            if conditions:
                sql += " AND " + " AND ".join(conditions)
            
            sql += " ORDER BY TEMPLATE_NAME"
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            templates = []
            for row in rows:
                templates.append(JobTemplate(
                    template_id=row[0],
                    template_name=row[1],
                    template_code=row[2],
                    source_layer_id=row[3],
                    target_layer_id=row[4],
                    job_type=row[5],
                    category=row[6],
                    tags=row[7],
                    beschreibung=row[8],
                    usage_notes=row[9],
                    is_active=row[10].strip() if row[10] else 'Y',
                    default_primary_key_columns=row[11],
                    default_hash_columns=row[12],
                    default_valid_from_column=row[13],
                    default_valid_to_column=row[14],
                    default_is_current_column=row[15]
                ))
            
            return templates
            
        finally:
            cursor.close()
            conn.close()
    
    def get_job_template(self, template_id: int) -> Optional[JobTemplate]:
        """Einzelnes Job-Template laden"""
        templates = self.get_job_templates()
        for t in templates:
            if t.template_id == template_id:
                return t
        return None
    
    def create_job_template(self, request: CreateJobTemplateRequest) -> int:
        """Neues Job-Template erstellen. Gibt template_id zurück."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO MDP01_META.META_ETL_JOB_TEMPLATE (
                    TEMPLATE_NAME, TEMPLATE_CODE, JOB_TYPE,
                    SOURCE_LAYER_ID, TARGET_LAYER_ID,
                    CATEGORY, BESCHREIBUNG
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                request.template_name,
                request.template_code,
                request.job_type,
                request.source_layer_id,
                request.target_layer_id,
                request.category,
                request.beschreibung
            ])
            conn.commit()
            
            # ID des neuen Templates holen
            cursor.execute("""
                SELECT TEMPLATE_ID 
                FROM MDP01_META.META_ETL_JOB_TEMPLATE 
                WHERE TEMPLATE_CODE = ?
            """, [request.template_code])
            row = cursor.fetchone()
            
            return row[0] if row else 0
            
        finally:
            cursor.close()
            conn.close()
    
    # =========================================================================
    # Step Templates
    # =========================================================================
    
    def get_step_templates(
        self, 
        template_id: Optional[int] = None,
        standalone_only: bool = False
    ) -> List[StepTemplate]:
        """
        Liste aller Step-Templates.
        
        Args:
            template_id: Nur Steps eines bestimmten Job-Templates
            standalone_only: Nur eigenständige Bausteine (template_id IS NULL)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            sql = """
                SELECT 
                    STEP_TEMPLATE_ID,
                    TEMPLATE_ID,
                    STEP_NAME,
                    STEP_CODE,
                    STEP_ORDER,
                    STEP_CATEGORY,
                    SQL_TEMPLATE_PATH,
                    SQL_INLINE,
                    DEFAULT_PARAMETERS,
                    REQUIRED_PARAMETERS,
                    OPTIONAL_PARAMETERS,
                    BESCHREIBUNG,
                    IS_ACTIVE
                FROM MDP01_META.META_ETL_JOB_STEP_TEMPLATE
                WHERE IS_ACTIVE = 'Y'
            """
            
            params = []
            
            if template_id is not None:
                sql += " AND TEMPLATE_ID = ?"
                params.append(template_id)
            elif standalone_only:
                sql += " AND TEMPLATE_ID IS NULL"
            
            sql += " ORDER BY STEP_ORDER"
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            templates = []
            for row in rows:
                # Parse JSON parameters
                params_json = None
                if row[8]:
                    try:
                        params_json = json.loads(row[8])
                    except:
                        pass
                
                templates.append(StepTemplate(
                    step_template_id=row[0],
                    template_id=row[1],
                    step_name=row[2],
                    step_code=row[3],
                    step_order=row[4],
                    step_category=row[5],
                    sql_template_path=row[6],
                    sql_inline=row[7],
                    default_parameters=params_json,
                    required_parameters=row[9],
                    optional_parameters=row[10],
                    beschreibung=row[11],
                    is_active=row[12].strip() if row[12] else 'Y'
                ))
            
            return templates
            
        finally:
            cursor.close()
            conn.close()
    
    def create_step_template(self, request: CreateStepTemplateRequest) -> int:
        """Neues Step-Template erstellen. Gibt step_template_id zurück."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            params_json = json.dumps(request.default_parameters) if request.default_parameters else None
            
            cursor.execute("""
                INSERT INTO MDP01_META.META_ETL_JOB_STEP_TEMPLATE (
                    TEMPLATE_ID, STEP_NAME, STEP_CODE, STEP_ORDER,
                    STEP_CATEGORY, SQL_TEMPLATE_PATH, SQL_INLINE,
                    DEFAULT_PARAMETERS, REQUIRED_PARAMETERS, BESCHREIBUNG
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                request.template_id,
                request.step_name,
                request.step_code,
                request.step_order,
                request.step_category,
                request.sql_template_path,
                request.sql_inline,
                params_json,
                request.required_parameters,
                request.beschreibung
            ])
            conn.commit()
            
            # ID holen (letzter Insert)
            cursor.execute("""
                SELECT MAX(STEP_TEMPLATE_ID) 
                FROM MDP01_META.META_ETL_JOB_STEP_TEMPLATE
            """)
            row = cursor.fetchone()
            
            return row[0] if row else 0
            
        finally:
            cursor.close()
            conn.close()
    
    # =========================================================================
    # Job aus Template erstellen
    # =========================================================================
    
    def create_job_from_template(self, request: CreateJobFromTemplateRequest) -> int:
        """
        Erstellt neuen Job aus Template inkl. aller Steps.
        
        1. Template laden
        2. Target-Tabelle ermitteln (ID oder Name)
        3. Neuen Job in META_ETL_JOB erstellen
        4. Alle Step-Templates kopieren nach META_ETL_JOB_STEP
        5. Parameter substituieren ({{PLACEHOLDER}} → Wert)
        
        Returns: Neue job_id
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 1. Template laden
            template = self.get_job_template(request.template_id)
            if not template:
                raise ValueError(f"Template {request.template_id} nicht gefunden")
            
            # 2. Source Layer ID ermitteln
            cursor.execute("""
                SELECT LAYER_ID FROM MDP01_META.META_TABLE 
                WHERE TABLE_ID = ?
            """, [request.source_table_id])
            src_layer = cursor.fetchone()
            source_layer_id = src_layer[0] if src_layer else template.source_layer_id
            
            # Target-Layer bestimmen (Source Layer + 1)
            expected_target_layer_id = source_layer_id + 1 if source_layer_id else template.target_layer_id
            
            # 3. Target ermitteln:
            #    - Wenn target_table_id gegeben → verwenden
            #    - Wenn nur target_table_name → im TARGET-LAYER suchen oder neu anlegen
            target_table_id = request.target_table_id
            target_layer_id = expected_target_layer_id
            
            if not target_table_id and request.target_table_name:
                # Erst versuchen, Tabelle im TARGET-LAYER zu finden (NICHT im Source-Layer!)
                cursor.execute("""
                    SELECT TABLE_ID, LAYER_ID FROM MDP01_META.META_TABLE 
                    WHERE TABLE_NAME = ? AND LAYER_ID = ?
                    SAMPLE 1
                """, [request.target_table_name, expected_target_layer_id])
                existing = cursor.fetchone()
                
                if existing:
                    target_table_id = existing[0]
                    target_layer_id = existing[1]
                else:
                    # Target-Tabelle neu anlegen im Ziel-Layer
                    next_layer_id = expected_target_layer_id
                    
                    # Database ID für nächsten Layer holen
                    cursor.execute("""
                        SELECT DATABASE_ID FROM MDP01_META.META_DATABASE
                        WHERE LAYER_ID = ?
                        SAMPLE 1
                    """, [next_layer_id])
                    db_row = cursor.fetchone()
                    target_db_id = db_row[0] if db_row else 1  # Fallback
                    
                    # Nächste freie TABLE_ID holen (keine IDENTITY in Tabelle)
                    cursor.execute("SELECT COALESCE(MAX(TABLE_ID), 0) + 1 FROM MDP01_META.META_TABLE")
                    next_table_id = cursor.fetchone()[0]
                    
                    # Neue Tabelle in META_TABLE anlegen
                    cursor.execute("""
                        INSERT INTO MDP01_META.META_TABLE (
                            TABLE_ID, TABLE_NAME, DATABASE_ID, LAYER_ID
                        ) VALUES (?, ?, ?, ?)
                    """, [next_table_id, request.target_table_name, target_db_id, next_layer_id])
                    conn.commit()
                    
                    target_table_id = next_table_id
                    target_layer_id = next_layer_id
                    logger.info(f"Neue Target-Tabelle erstellt: {request.target_table_name} (ID={next_table_id})")
            
            if not target_table_id:
                raise ValueError("Target-Tabelle konnte nicht ermittelt oder erstellt werden")
            
            # SICHERHEIT: Source und Target dürfen nicht identisch sein!
            if request.source_table_id == target_table_id:
                raise ValueError(
                    f"Source und Target dürfen nicht dieselbe Tabelle sein! "
                    f"(table_id={target_table_id}). "
                    f"Bitte eine andere Zieltabelle wählen."
                )
            
            # PRÜFUNG: Job-Name bereits vergeben?
            cursor.execute("SELECT ETL_JOB_ID FROM MDP01_META.META_ETL_JOB WHERE JOB_NAME = ?", [request.job_name])
            existing_job = cursor.fetchone()
            if existing_job:
                raise ValueError(f"Job mit Namen '{request.job_name}' existiert bereits (ID: {existing_job[0]})")
            
            # 4. Job erstellen
            # Nächste freie Job-ID holen (keine IDENTITY in Tabelle)
            cursor.execute("SELECT COALESCE(MAX(ETL_JOB_ID), 0) + 1 FROM MDP01_META.META_ETL_JOB")
            next_job_id = cursor.fetchone()[0]
            
            cursor.execute("""
                INSERT INTO MDP01_META.META_ETL_JOB (
                    ETL_JOB_ID, JOB_NAME, JOB_TYPE,
                    SOURCE_TABLE_ID, TARGET_TABLE_ID,
                    SOURCE_LAYER_ID, TARGET_LAYER_ID,
                    PRIMARY_KEY_COLUMNS, HASH_COLUMNS,
                    VALID_FROM_COLUMN, VALID_TO_COLUMN, IS_CURRENT_COLUMN,
                    IS_ACTIVE, RETRY_COUNT, TIMEOUT_SECONDS
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Y', 3, 3600)
            """, [
                next_job_id,
                request.job_name,
                template.job_type,
                request.source_table_id,
                target_table_id,
                source_layer_id,
                target_layer_id,
                template.default_primary_key_columns,
                template.default_hash_columns,
                template.default_valid_from_column,
                template.default_valid_to_column,
                template.default_is_current_column
            ])
            conn.commit()
            
            # Job-ID ist bereits bekannt (next_job_id)
            job_id = next_job_id
            
            # 5. Step-Templates kopieren
            step_templates = self.get_step_templates(template_id=request.template_id)
            
            # =================================================================
            # Parameter-Generierung: FRISCH aus User-Input + Config-Regeln
            # Template-Parameter-WERTE werden ignoriert! Nur Struktur zählt.
            # =================================================================
            
            # User-Input extrahieren (case-insensitive Lookup)
            def get_param_ci(params: dict, key: str, default=''):
                """Case-insensitive Parameter-Lookup"""
                if not params:
                    return default
                key_lower = key.lower()
                for k, v in params.items():
                    if k.lower() == key_lower:
                        return v
                return default
            
            # Core-Name aus Tabellennamen extrahieren (basierend auf Config)
            def extract_core_name(table_name: str) -> str:
                """Extrahiert Kern: TAAA_IDENTITAET → IDENTITAET"""
                if not table_name:
                    return ''
                prefixes = self.param_rules.get('core_name_extraction', {}).get('remove_prefixes', [])
                name_upper = table_name.upper()
                for prefix in prefixes:
                    if name_upper.startswith(prefix.upper()):
                        return table_name[len(prefix):]
                # Fallback: nach erstem _ splitten wenn Präfix kurz
                if '_' in table_name:
                    parts = table_name.split('_', 1)
                    if len(parts[0]) <= 4:
                        return parts[1]
                return table_name
            
            # ================================================================
            # Source-Infos automatisch aus source_table_id laden
            # ================================================================
            cursor.execute("""
                SELECT t.TABLE_NAME, d.DATABASE_NAME 
                FROM MDP01_META.META_TABLE t
                JOIN MDP01_META.META_DATABASE d ON t.DATABASE_ID = d.DATABASE_ID
                WHERE t.TABLE_ID = ?
            """, [request.source_table_id])
            src_row = cursor.fetchone()
            source_table_name = src_row[0] if src_row else ''
            source_database_name = src_row[1] if src_row else ''
            
            # Spalten aus META_COLUMN laden (für SELECT_COLUMNS)
            cursor.execute("""
                SELECT COLUMN_NAME FROM MDP01_META.META_COLUMN 
                WHERE TABLE_ID = ? 
                ORDER BY COLUMN_POSITION
            """, [request.source_table_id])
            all_source_columns = [r[0].upper() for r in cursor.fetchall()]
            
            # Primary Keys aus META_COLUMN laden (für BUSINESS_KEY)
            cursor.execute("""
                SELECT COLUMN_NAME FROM MDP01_META.META_COLUMN 
                WHERE TABLE_ID = ? AND IS_BUSINESS_KEY = 'Y'
                ORDER BY COLUMN_POSITION
            """, [request.source_table_id])
            pk_from_meta = [r[0].upper() for r in cursor.fetchall()]
            
            # Werte aus User-Input (mit Fallback auf auto-geladene Werte)
            new_source = get_param_ci(request.parameters, 'source_table', request.source_table_name or source_table_name)
            new_target = get_param_ci(request.parameters, 'target_table', request.target_table_name or '')
            pk_columns = get_param_ci(request.parameters, 'primary_key_columns', pk_from_meta)
            hash_columns = get_param_ci(request.parameters, 'hash_columns', all_source_columns)  # Default: alle Spalten hashen
            select_columns = get_param_ci(request.parameters, 'select_columns', all_source_columns)
            
            # Core-Name aus Source-Tabelle (oder Target als Fallback)
            core_name = extract_core_name(new_source) if new_source else extract_core_name(new_target)
            
            # Layer-Config laden (basierend auf target_layer_id)
            layers_config = self.param_rules.get('layers', {})
            staging_config = self.param_rules.get('staging', {})
            
            # Layer-Name ermitteln (ID -> Name Mapping)
            layer_id_to_name = {1: 'raw', 2: 'discoverable', 3: 'reusable', 4: 'consumable'}
            target_layer_name = layer_id_to_name.get(target_layer_id, 'discoverable')
            target_layer_config = layers_config.get(target_layer_name, {})
            
            # Werte aus Layer-Config
            key_table_prefix = target_layer_config.get('key_prefix', 'KEY_')
            key_database = target_layer_config.get('database', 'MDP01_DISCOVERABLE_LAYER')
            history_suffix = target_layer_config.get('history_suffix', '_HISTORY')
            
            # Staging aus eigener Config
            staging_prefix = staging_config.get('prefix', 'temp_')
            staging_suffix = staging_config.get('suffix', '_staging')
            
            # Key-Tabellen-Name generieren
            key_table_name = f"{key_table_prefix}{core_name.upper()}" if core_name else ''
            
            # SK-Spaltenname aus Config generieren
            scd2_config = self.param_rules.get('scd2_technical_columns', {})
            sk_config = scd2_config.get('surrogate_key', {})
            if isinstance(sk_config, dict):
                sk_pattern = sk_config.get('pattern', '{core_name}_SK')
                sk_fallback = sk_config.get('fallback', 'SURROGATE_KEY')
                sk_column_name = sk_pattern.replace('{core_name}', core_name.upper()) if core_name else sk_fallback
            else:
                # Legacy: nur String-Wert
                sk_column_name = sk_config if sk_config else 'SURROGATE_KEY'
            
            # Generierte Parameter-Werte (berechnet aus User-Input + Config)
            generated_values = {
                'SOURCE_TABLE': new_source,
                'TARGET_TABLE': new_target,
                'source_table': new_source,
                'target_table': new_target,
                'KEY_TABLE': key_table_name,
                'KEY_DATABASE': key_database,
                'TARGET_DATABASE': key_database,  # Target-Tabelle liegt im gleichen Layer wie Key-Tabellen
                'SOURCE_DATABASE': source_database_name or layers_config.get('raw', {}).get('database', 'MDP01_RAW_LAYER'),
                'NATURAL_KEY_COL': pk_columns[0] if pk_columns else '',
                'BUSINESS_KEY': ', '.join(pk_columns) if isinstance(pk_columns, list) else pk_columns,
                'STAGING_TABLE': f"{staging_prefix}{new_source.lower()}{staging_suffix}" if new_source else '',
                'NEW_RECORDS_TABLE': f"{staging_prefix}{new_source.lower()}_new" if new_source else '',
                'CHANGED_RECORDS_TABLE': f"{staging_prefix}{new_source.lower()}_changed" if new_source else '',
                'HASH_COLUMNS': ', '.join(hash_columns) if isinstance(hash_columns, list) else hash_columns,
                'SELECT_COLUMNS': ', '.join(select_columns) if isinstance(select_columns, list) else select_columns,
                'INSERT_COLUMNS': select_columns,  # Spalten für INSERT = select_columns
                'primary_key_columns': pk_columns,
                'hash_columns': hash_columns,
                'select_columns': select_columns,
                'SK_COLUMN': sk_column_name,  # z.B. AUFENTHALT_SK
                'CORE_NAME': core_name.upper() if core_name else '',
            }
            
            logger.debug(f"Parameter-Generierung: source={new_source}, core_name={core_name}, pk_columns={pk_columns}, select_columns={len(select_columns)} Spalten")
            
            for step_tpl in step_templates:
                # ALLE generierten Parameter setzen (nicht nur die aus Template!)
                # Dies ist wichtig, da die Template DEFAULT_PARAMETERS oft NULL sind
                parameters = generated_values.copy()
                
                # Template-Defaults hinzufügen falls vorhanden (überschreibt nicht)
                if step_tpl.default_parameters:
                    for key, value in step_tpl.default_parameters.items():
                        if key not in parameters:
                            parameters[key] = value
                
                # User-Parameter überschreiben (explizit mitgegeben)
                if request.parameters:
                    for key, value in request.parameters.items():
                        parameters[key] = value
                
                # SQL_INLINE: Platzhalter {{KEY}} durch generierte Werte ersetzen
                if step_tpl.sql_inline:
                    sql_inline = step_tpl.sql_inline
                    # Alle generierten Parameter-Platzhalter ersetzen
                    for key, value in parameters.items():
                        if isinstance(value, str):
                            sql_inline = sql_inline.replace(f"{{{{{key}}}}}", value)
                        elif isinstance(value, list):
                            sql_inline = sql_inline.replace(f"{{{{{key}}}}}", ", ".join(value))
                    step_sql_inline = sql_inline
                else:
                    step_sql_inline = step_tpl.sql_inline
                
                cursor.execute("""
                    INSERT INTO MDP01_META.META_ETL_JOB_STEP (
                        ETL_JOB_ID, STEP_NAME, STEP_ORDER, STEP_CATEGORY,
                        SQL_TEMPLATE_PATH, SQL_INLINE,
                        PARAMETERS, IS_CRITICAL, ROLLBACK_ON_ERROR, IS_ACTIVE,
                        RETRY_COUNT, TIMEOUT_SECONDS
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Y', 'Y', 'Y', 3, 300)
                """, [
                    job_id,
                    step_tpl.step_name,
                    step_tpl.step_order,
                    step_tpl.step_category,
                    step_tpl.sql_template_path,
                    step_sql_inline,
                    json.dumps(parameters) if parameters else None
                ])
            
            conn.commit()
            logger.info(f"Job {job_id} aus Template {request.template_id} erstellt mit {len(step_templates)} Steps")
            
            # Key-Tabelle automatisch erstellen wenn nicht vorhanden
            if key_table_name and key_database:
                self._ensure_key_table_exists(cursor, conn, key_database, key_table_name)
            
            # Ziel-Tabelle automatisch erstellen wenn nicht vorhanden (AF-009)
            if new_target and key_database:
                self._ensure_target_table_exists(
                    cursor, conn, 
                    key_database, 
                    new_target,
                    request.source_table_id,
                    pk_columns if isinstance(pk_columns, list) else [],
                    core_name=core_name
                )
            
            return job_id
            
        finally:
            cursor.close()
            conn.close()
    
    def _ensure_key_table_exists(self, cursor, conn, database: str, table_name: str):
        """
        Prüft ob Key-Tabelle existiert, erstellt sie wenn nicht.
        
        Key-Tabellen haben eine Standard-Struktur für Surrogate Key Management.
        """
        fqn = f"{database}.{table_name}"
        
        # Prüfen ob Tabelle existiert
        try:
            cursor.execute(f"""
                SELECT 1 FROM dbc.TablesV 
                WHERE DatabaseName = '{database}' 
                AND TableName = '{table_name}'
                AND TableKind = 'T'
            """)
            if cursor.fetchone():
                logger.debug(f"Key-Tabelle {fqn} existiert bereits")
                return
        except Exception as e:
            logger.warning(f"Fehler beim Prüfen der Key-Tabelle: {e}")
        
        # Key-Tabelle erstellen
        ddl = f"""
            CREATE SET TABLE {fqn}
            (
                SURROGATE_KEY               BIGINT NOT NULL,
                NATURAL_KEY_VALUE           VARCHAR(255) CHARACTER SET UNICODE NOT NULL,
                NATURAL_KEY_DOMAIN          VARCHAR(50) CHARACTER SET UNICODE NOT NULL,
                NATURAL_KEY_HASH            BYTE(20),
                IS_MASKED                   CHAR(1) CHARACTER SET UNICODE DEFAULT 'N',
                MASKED_VALUE                VARCHAR(255) CHARACTER SET UNICODE,
                CREATED_TIMESTAMP           TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                CREATED_BY                  VARCHAR(100) CHARACTER SET UNICODE DEFAULT 'ETL_KEY_GEN',
                PRIMARY KEY (SURROGATE_KEY)
            )
            UNIQUE INDEX idx_{table_name.lower()}_natural (NATURAL_KEY_DOMAIN, NATURAL_KEY_VALUE)
        """
        
        try:
            cursor.execute(ddl)
            conn.commit()
            logger.info(f"Key-Tabelle {fqn} erstellt")
            
            # Default-Eintrag (-1, UNKNOWN)
            cursor.execute(f"""
                INSERT INTO {fqn} (
                    SURROGATE_KEY, NATURAL_KEY_VALUE, NATURAL_KEY_DOMAIN, IS_MASKED, CREATED_BY
                ) VALUES (-1, 'UNKNOWN', 'SYSTEM', 'N', 'DDL_INIT')
            """)
            conn.commit()
            logger.info(f"Default-Eintrag in {fqn} erstellt")
            
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Key-Tabelle {fqn}: {e}")
            # Kein raise - Job wurde bereits erstellt, Key-Tabelle kann später manuell erstellt werden
    
    def _ensure_target_table_exists(
        self, 
        cursor, 
        conn, 
        target_database: str, 
        target_table: str,
        source_table_id: int,
        pk_columns: List[str],
        core_name: str = ''
    ):
        """
        Prüft ob Ziel-Tabelle existiert, erstellt sie wenn nicht.
        
        Ziel-Tabelle = Source-Spalten + SCD2-Spalten (aus Config: cfg/parameter_rules.yml)
        DDL-Optionen (SET/MULTISET, PRIMARY INDEX) ebenfalls aus Config.
        
        Args:
            core_name: Kern-Name der Tabelle (z.B. 'aufenthalt') für SK-Spaltenname
        """
        fqn = f"{target_database}.{target_table}"
        
        # Prüfen ob Tabelle existiert
        try:
            cursor.execute(f"""
                SELECT 1 FROM dbc.TablesV 
                WHERE DatabaseName = '{target_database}' 
                AND TableName = '{target_table}'
                AND TableKind = 'T'
            """)
            if cursor.fetchone():
                logger.debug(f"Ziel-Tabelle {fqn} existiert bereits")
                return
        except Exception as e:
            logger.warning(f"Fehler beim Prüfen der Ziel-Tabelle: {e}")
        
        # Source-Spalten aus META_COLUMN laden (inkl. COLUMN_LENGTH!)
        cursor.execute("""
            SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_LENGTH 
            FROM MDP01_META.META_COLUMN 
            WHERE TABLE_ID = ?
            ORDER BY COLUMN_POSITION
        """, [source_table_id])
        source_columns = cursor.fetchall()
        
        if not source_columns:
            # Fallback: Direkt aus dbc.ColumnsV laden
            cursor.execute("""
                SELECT t.TABLE_NAME, d.DATABASE_NAME
                FROM MDP01_META.META_TABLE t
                JOIN MDP01_META.META_DATABASE d ON t.DATABASE_ID = d.DATABASE_ID
                WHERE t.TABLE_ID = ?
            """, [source_table_id])
            src_info = cursor.fetchone()
            if src_info:
                cursor.execute(f"""
                    SELECT ColumnName, ColumnType, ColumnLength
                    FROM dbc.ColumnsV
                    WHERE DatabaseName = '{src_info[1]}' AND TableName = '{src_info[0]}'
                    ORDER BY ColumnId
                """)
                source_columns = cursor.fetchall()
        
        if not source_columns:
            logger.error(f"Keine Spalten für Source-Tabelle {source_table_id} gefunden")
            return
        
        # =================================================================
        # Config laden: SCD2-Spalten + DDL-Optionen
        # =================================================================
        scd2_config = self.param_rules.get('scd2_technical_columns', {})
        ddl_config = self.param_rules.get('target_table_ddl', {})
        
        # Helper: Spalten-Definition aus Config erstellen
        def build_column_def(col_key: str, config: dict) -> tuple:
            """Gibt (spalten_name, spalten_definition) zurück"""
            if isinstance(config, dict):
                # Neues Format mit pattern, type, nullable, default
                if 'pattern' in config:
                    # SK mit Pattern
                    pattern = config.get('pattern', '{core_name}_SK')
                    fallback = config.get('fallback', 'SURROGATE_KEY')
                    col_name = pattern.replace('{core_name}', core_name.upper()) if core_name else fallback
                else:
                    col_name = config.get('name', col_key.upper())
                
                col_type = config.get('type', 'VARCHAR(255)')
                nullable = config.get('nullable', True)
                default = config.get('default', None)
                
                # Definition zusammenbauen
                parts = [col_name, col_type]
                if not nullable:
                    parts.append('NOT NULL')
                if default:
                    parts.append(f'DEFAULT {default}')
                
                return col_name, ' '.join(parts)
            else:
                # Legacy: nur String-Wert (Spaltenname)
                return config, f"{config} VARCHAR(255)"
        
        # DDL generieren
        columns_ddl = []
        
        # SK-Spalte (erste Spalte)
        sk_config = scd2_config.get('surrogate_key', {})
        sk_name, sk_def = build_column_def('surrogate_key', sk_config)
        columns_ddl.append(sk_def)
        
        # Source-Spalten
        for row in source_columns:
            col_name = row[0].strip().upper()
            col_type = row[1].strip() if row[1] else None
            col_length = row[2] if len(row) > 2 else None
            
            # Typ-Mapping für Teradata
            if col_type:
                if col_type.startswith('I'):
                    td_type = 'INTEGER'
                elif col_type.startswith('D') or col_type.startswith('N'):
                    td_type = 'DECIMAL(18,2)'
                elif col_type.startswith('DA'):
                    td_type = 'DATE'
                elif col_type.startswith('TS') or col_type.startswith('SZ'):
                    td_type = 'TIMESTAMP(6)'
                elif col_type.startswith('CV'):
                    length = int(col_length) if col_length else 255
                    td_type = f'VARCHAR({length})'
                elif col_type.startswith('CF'):
                    length = int(col_length) if col_length else 1
                    td_type = f'CHAR({length})'
                else:
                    td_type = 'VARCHAR(255)'
            else:
                td_type = 'VARCHAR(255)'
            columns_ddl.append(f"{col_name} {td_type}")
        
        # SCD2-Spalten am Ende (aus Config)
        scd2_order = ['record_hash', 'valid_from', 'valid_to', 'is_current', 
                      'created_timestamp', 'last_updated_timestamp', 
                      'created_by', 'last_updated_by']
        
        scd2_names = {}  # Speichern für PRIMARY INDEX
        for col_key in scd2_order:
            col_config = scd2_config.get(col_key, {})
            col_name, col_def = build_column_def(col_key, col_config)
            scd2_names[col_key] = col_name
            columns_ddl.append(col_def)
        
        # =================================================================
        # PRIMARY INDEX aus Config (nicht PRIMARY KEY!)
        # =================================================================
        pi_config = ddl_config.get('primary_index', {})
        pi_columns = pi_config.get('columns', ['{sk_column}', '{valid_from}'])
        
        # Platzhalter ersetzen
        pi_cols_resolved = []
        for col in pi_columns:
            resolved = col.replace('{sk_column}', sk_name)
            resolved = resolved.replace('{valid_from}', scd2_names.get('valid_from', 'VALID_FROM'))
            pi_cols_resolved.append(resolved)
        
        pi_def = f"PRIMARY INDEX ({', '.join(pi_cols_resolved)})"
        
        # Table Type aus Config
        table_type = ddl_config.get('table_type', 'SET')
        
        ddl = f"""
            CREATE {table_type} TABLE {fqn}
            (
                {', '.join(columns_ddl)}
            )
            {pi_def}
        """
        
        try:
            cursor.execute(ddl)
            conn.commit()
            logger.info(f"Ziel-Tabelle {fqn} erstellt mit {len(source_columns)} Source-Spalten + SCD2-Spalten (SK={sk_name})")
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Ziel-Tabelle {fqn}: {e}\nDDL: {ddl}")
            # Kein raise - Job wurde bereits erstellt
    
    def add_step_from_template(
        self, 
        job_id: int, 
        step_template_id: int,
        step_order: Optional[int] = None,
        parameters: Optional[Dict[str, str]] = None
    ) -> int:
        """
        Fügt einzelnen Step aus Template zu bestehendem Job hinzu.
        
        Args:
            job_id: Ziel-Job
            step_template_id: Step-Template (eigenständiger Baustein)
            step_order: Position im Job (None = ans Ende)
            parameters: Platzhalter-Ersetzungen
            
        Returns: Neue step_id
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Step-Template laden
            cursor.execute("""
                SELECT 
                    STEP_NAME, STEP_ORDER, STEP_CATEGORY,
                    SQL_TEMPLATE_PATH, SQL_INLINE,
                    DEFAULT_PARAMETERS
                FROM MDP01_META.META_ETL_JOB_STEP_TEMPLATE
                WHERE STEP_TEMPLATE_ID = ?
            """, [step_template_id])
            
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Step-Template {step_template_id} nicht gefunden")
            
            # Step-Order bestimmen
            if step_order is None:
                cursor.execute("""
                    SELECT COALESCE(MAX(STEP_ORDER), 0) + 10
                    FROM MDP01_META.META_ETL_JOB_STEP
                    WHERE ETL_JOB_ID = ?
                """, [job_id])
                order_row = cursor.fetchone()
                step_order = order_row[0] if order_row else 10
            
            # Parameter substituieren
            step_params = {}
            if row[5]:
                try:
                    step_params = json.loads(row[5])
                except:
                    pass
            
            if parameters:
                params_str = json.dumps(step_params)
                for key, value in parameters.items():
                    params_str = params_str.replace(f"{{{{{key}}}}}", value)
                step_params = json.loads(params_str)
            
            # Step einfügen
            cursor.execute("""
                INSERT INTO MDP01_META.META_ETL_JOB_STEP (
                    ETL_JOB_ID, STEP_NAME, STEP_ORDER, STEP_CATEGORY,
                    SQL_TEMPLATE_PATH, SQL_INLINE,
                    PARAMETERS, IS_CRITICAL, ROLLBACK_ON_ERROR, IS_ACTIVE
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Y', 'Y', 'Y')
            """, [
                job_id,
                row[0],  # STEP_NAME
                step_order,
                row[2],  # STEP_CATEGORY
                row[3],  # SQL_TEMPLATE_PATH
                row[4],  # SQL_INLINE
                json.dumps(step_params) if step_params else None
            ])
            conn.commit()
            
            # Step-ID holen
            cursor.execute("""
                SELECT MAX(ETL_JOB_STEP_ID)
                FROM MDP01_META.META_ETL_JOB_STEP
                WHERE ETL_JOB_ID = ?
            """, [job_id])
            step_row = cursor.fetchone()
            
            return step_row[0] if step_row else 0
            
        finally:
            cursor.close()
            conn.close()
    
    # =========================================================================
    # Job als Template speichern
    # =========================================================================
    
    def check_template_exists_by_name(self, template_name: str) -> Optional[int]:
        """
        Prüft ob ein Template mit diesem NAMEN bereits existiert.
        
        Returns: template_id wenn existiert, sonst None
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT TEMPLATE_ID 
                FROM MDP01_META.META_ETL_JOB_TEMPLATE
                WHERE TEMPLATE_NAME = ?
            """, [template_name])
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            cursor.close()
            conn.close()
    
    def delete_template(self, template_id: int) -> bool:
        """
        Löscht ein Template inkl. aller Step-Templates.
        
        Returns: True wenn erfolgreich
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Erst Step-Templates löschen
            cursor.execute("""
                DELETE FROM MDP01_META.META_ETL_JOB_STEP_TEMPLATE
                WHERE TEMPLATE_ID = ?
            """, [template_id])
            
            # Dann Job-Template löschen
            cursor.execute("""
                DELETE FROM MDP01_META.META_ETL_JOB_TEMPLATE
                WHERE TEMPLATE_ID = ?
            """, [template_id])
            
            conn.commit()
            logger.info(f"Template {template_id} gelöscht inkl. Steps")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Löschen von Template {template_id}: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()
    
    def save_job_as_template(
        self, 
        job_id: int, 
        template_name: Optional[str] = None,
        template_code: Optional[str] = None,
        category: Optional[str] = None,
        beschreibung: Optional[str] = None,
        overwrite: bool = False
    ) -> dict:
        """
        Speichert bestehenden Job als neues Template.
        
        1. Job laden (für Name + Typ)
        2. Prüfen ob Template bereits existiert
        3. Bei overwrite=True: altes Template löschen
        4. Job-Template erstellen
        5. Alle Steps als Step-Templates kopieren
        
        Returns: dict mit template_id, created (bool), message
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 1. Job laden für Name und Typ
            cursor.execute("""
                SELECT 
                    JOB_NAME, JOB_TYPE, SOURCE_LAYER_ID, TARGET_LAYER_ID,
                    PRIMARY_KEY_COLUMNS, HASH_COLUMNS,
                    VALID_FROM_COLUMN, VALID_TO_COLUMN, IS_CURRENT_COLUMN,
                    BESCHREIBUNG
                FROM MDP01_META.META_ETL_JOB
                WHERE ETL_JOB_ID = ?
            """, [job_id])
            
            job_row = cursor.fetchone()
            if not job_row:
                raise ValueError(f"Job {job_id} nicht gefunden")
            
            job_name = job_row[0]
            
            # Template-Name/Code aus Job-Namen ableiten wenn nicht angegeben
            final_template_name = template_name or job_name
            final_template_code = template_code or final_template_name.upper().replace(' ', '_').replace('-', '_')
            
            # 2. Prüfen ob Template mit gleichem NAMEN bereits existiert
            cursor.execute("""
                SELECT TEMPLATE_ID, TEMPLATE_CODE
                FROM MDP01_META.META_ETL_JOB_TEMPLATE
                WHERE TEMPLATE_NAME = ?
            """, [final_template_name])
            existing = cursor.fetchone()
            
            if existing and not overwrite:
                # Template existiert und kein overwrite → Fehler zurückgeben
                return {
                    "template_id": existing[0],
                    "created": False,
                    "exists": True,
                    "message": f"Template '{final_template_name}' existiert bereits (ID: {existing[0]}). Mit overwrite=true überschreiben."
                }
            
            # 3. Bei overwrite: altes Template löschen (close+reopen wegen separater connection)
            if existing and overwrite:
                cursor.close()
                conn.close()
                self.delete_template(existing[0])
                conn = self._get_connection()
                cursor = conn.cursor()
            
            # 4. Job-Template erstellen
            cursor.execute("""
                INSERT INTO MDP01_META.META_ETL_JOB_TEMPLATE (
                    TEMPLATE_NAME, TEMPLATE_CODE, JOB_TYPE,
                    SOURCE_LAYER_ID, TARGET_LAYER_ID,
                    DEFAULT_PRIMARY_KEY_COLUMNS, DEFAULT_HASH_COLUMNS,
                    DEFAULT_VALID_FROM_COLUMN, DEFAULT_VALID_TO_COLUMN,
                    DEFAULT_IS_CURRENT_COLUMN,
                    CATEGORY, BESCHREIBUNG
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                final_template_name,
                final_template_code,
                job_row[1],  # JOB_TYPE
                job_row[2],  # SOURCE_LAYER_ID
                job_row[3],  # TARGET_LAYER_ID
                job_row[4],  # PRIMARY_KEY_COLUMNS
                job_row[5],  # HASH_COLUMNS
                job_row[6],  # VALID_FROM_COLUMN
                job_row[7],  # VALID_TO_COLUMN
                job_row[8],  # IS_CURRENT_COLUMN
                category,
                beschreibung or job_row[9]
            ])
            conn.commit()
            
            # Template-ID holen
            cursor.execute("""
                SELECT TEMPLATE_ID 
                FROM MDP01_META.META_ETL_JOB_TEMPLATE
                WHERE TEMPLATE_CODE = ?
            """, [final_template_code])
            tpl_row = cursor.fetchone()
            template_id = tpl_row[0] if tpl_row else 0
            
            if not template_id:
                raise ValueError("Template konnte nicht erstellt werden")
            
            # 5. Steps kopieren
            cursor.execute("""
                SELECT 
                    STEP_NAME, STEP_ORDER, STEP_CATEGORY,
                    SQL_TEMPLATE_PATH, SQL_INLINE, PARAMETERS,
                    IS_CRITICAL, ROLLBACK_ON_ERROR, BESCHREIBUNG
                FROM MDP01_META.META_ETL_JOB_STEP
                WHERE ETL_JOB_ID = ?
                ORDER BY STEP_ORDER
            """, [job_id])
            
            steps = cursor.fetchall()
            
            for step in steps:
                cursor.execute("""
                    INSERT INTO MDP01_META.META_ETL_JOB_STEP_TEMPLATE (
                        TEMPLATE_ID, STEP_NAME, STEP_ORDER, STEP_CATEGORY,
                        SQL_TEMPLATE_PATH, SQL_INLINE, DEFAULT_PARAMETERS,
                        DEFAULT_IS_CRITICAL, DEFAULT_ROLLBACK_ON_ERROR,
                        BESCHREIBUNG
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    template_id,
                    step[0],  # STEP_NAME
                    step[1],  # STEP_ORDER
                    step[2],  # STEP_CATEGORY
                    step[3],  # SQL_TEMPLATE_PATH
                    step[4],  # SQL_INLINE
                    step[5],  # PARAMETERS → DEFAULT_PARAMETERS
                    step[6],  # IS_CRITICAL
                    step[7],  # ROLLBACK_ON_ERROR
                    step[8]   # BESCHREIBUNG
                ])
            
            conn.commit()
            logger.info(f"Job {job_id} als Template {template_id} gespeichert mit {len(steps)} Steps")
            
            return {
                "template_id": template_id,
                "created": True,
                "exists": False,
                "message": f"Template '{final_template_code}' erfolgreich erstellt mit {len(steps)} Steps."
            }
            
        finally:
            cursor.close()
            conn.close()
