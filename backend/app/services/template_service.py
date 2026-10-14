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

from .type_utils import td_typecode_to_ddl
from ..config import PATHS, get_active_teradata_config, get_etl_jobs_path, META_SCHEMA

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
    use_sk: str = 'N'  # F7: SK-Spalte verwenden (template-abhängiges Flag, unabhängig von SCD2)


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
        """Initialisiert Service mit Parameter-Regeln (DB-Config kommt pro
        Verbindung dynamisch aus dem aktiven Environment, siehe _get_connection)"""
        cfg_dir = PATHS["cfg"]

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
        """Erstellt neue DB Connection (aktives Environment, nicht gecacht)"""
        active_cfg = get_active_teradata_config()
        return teradatasql.connect(
            host=active_cfg.get('host'),
            user=active_cfg.get('user'),
            password=active_cfg.get('password'),
            connect_timeout=active_cfg.get('connect_timeout', 10000)
        )
    
    def _layers_config(self, cursor, layer_id_to_name: Dict[int, str]) -> Dict[str, dict]:
        """Layer-Config aus parameter_rules.yml, Datenbank je Layer aus META_DATABASE
        des aktiven Environments (parameter_rules.yml bleibt Fallback).

        Nur Layer mit genau einer Datenbank werden übernommen; sonst ist die
        Zuordnung nicht eindeutig.
        """
        layers = {name: dict(cfg or {}) for name, cfg in (self.param_rules.get('layers', {}) or {}).items()}
        try:
            cursor.execute(f"""
                SELECT LAYER_ID, MIN(DATABASE_NAME), COUNT(*)
                FROM {META_SCHEMA}.META_DATABASE
                WHERE LAYER_ID IN ({', '.join(str(i) for i in layer_id_to_name)})
                GROUP BY LAYER_ID
            """)
            for layer_id, db_name, anzahl in cursor.fetchall():
                if anzahl == 1 and db_name:
                    layers.setdefault(layer_id_to_name[layer_id], {})['database'] = db_name.strip()
                else:
                    logger.warning(f"META_DATABASE: Layer {layer_id} hat {anzahl} Datenbanken - "
                                   f"Datenbank aus parameter_rules.yml")
        except Exception as e:
            logger.warning(f"Layer-Datenbanken aus META_DATABASE nicht lesbar - parameter_rules.yml: {e}")
        return layers

    def _extract_core_name(self, table_name: str) -> str:
        """Extrahiert Kern: TAAA_IDENTITAET → IDENTITAET (Regeln: core_name_extraction)"""
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

    @staticmethod
    def _scd2_column_names_params(scd2_config: dict) -> Dict[str, str]:
        """Namen der Hash- und Audit-Spalten aus scd2_technical_columns als Parameter."""
        def name(key: str, default: str) -> str:
            cfg = scd2_config.get(key, {})
            return cfg.get('name', default) if isinstance(cfg, dict) else (cfg or default)
        return {
            'RECORD_HASH_COL': name('record_hash', 'RECORD_HASH'),
            'CREATED_TS_COL':  name('created_timestamp', 'CREATED_TIMESTAMP'),
            'UPDATED_TS_COL':  name('last_updated_timestamp', 'LAST_UPDATED_TIMESTAMP'),
            'CREATED_BY_COL':  name('created_by', 'CREATED_BY'),
            'UPDATED_BY_COL':  name('last_updated_by', 'LAST_UPDATED_BY'),
        }

    @staticmethod
    def _raw_delta_target_cfg(raw_delta: dict) -> Dict[str, dict]:
        """Zielspalten des Delta-Sets (Ladelauf, Lösch-Kennzeichen) mit Defaults."""
        tc = raw_delta.get('target_columns', {}) or {}
        load_id = {'name': 'DWH_LOAD_ID', 'type': 'BIGINT', **(tc.get('load_id') or {})}
        deleted = {'name': 'DWH_DELETED_IN_SOURCE', 'type': 'CHAR(1) CHARACTER SET UNICODE',
                   'default': "'N'", 'deleted_value': 'Y', 'not_deleted_value': 'N',
                   **(tc.get('deleted_in_source') or {})}
        return {'load_id': load_id, 'deleted_in_source': deleted}

    def _raw_delta_target_columns(self, raw_delta: dict) -> List[tuple]:
        """[(name, DDL-Definition)] der Zielspalten des Delta-Sets."""
        cols = []
        for cfg in self._raw_delta_target_cfg(raw_delta).values():
            parts = [cfg['name'], cfg['type']]
            if cfg.get('nullable') is False:
                parts.append('NOT NULL')
            if cfg.get('default'):
                parts.append(f"DEFAULT {cfg['default']}")
            cols.append((cfg['name'], ' '.join(parts)))
        return cols

    def _raw_delta_params(self, raw_delta: dict, job_id: int, source_table_id: int,
                          pk_columns: List[str], staging_prefix: str, source_table: str,
                          scd2_config: dict = None) -> Dict[str, str]:
        """Parameter für das Delta-Set aus cfg/parameter_rules.yml → raw_delta.

        LOAD_WATERMARK ist ein SQL-Ausdruck auf die Ladestand-Tabelle der Meta-DB,
        damit jeder Lauf den zuletzt bestätigten Stand liest (kein Laufzeitparameter nötig).
        """
        if not raw_delta:
            return {}
        ct = raw_delta.get('change_type_values', {}) or {}
        target_cfg = self._raw_delta_target_cfg(raw_delta)
        meta_db = str(META_SCHEMA)
        state_table = raw_delta.get('load_state_table', 'META_ETL_LOAD_STATE')
        # ADR-0016: Gültigkeitsbeginn des initialen Stands (leer = Snapshot-Zeit)
        vf_cfg = (scd2_config or {}).get('valid_from', {})
        initial_vf = vf_cfg.get('initial_value') if isinstance(vf_cfg, dict) else None
        snapshot_col = raw_delta.get('snapshot_column', '')
        return {
            'INITIAL_VALID_FROM_EXPR': f"TIMESTAMP '{initial_vf}'" if initial_vf else f"src.{snapshot_col}",
            'LOAD_ID_COL':      raw_delta.get('load_id_column', ''),
            'SNAPSHOT_COL':     raw_delta.get('snapshot_column', ''),
            'CHANGE_TYPE_COL':  raw_delta.get('change_type_column', ''),
            'CT_INSERT':        ct.get('insert', 'INSERTED'),
            'CT_UPDATE':        ct.get('update', 'UPDATED'),
            'CT_DELETE':        ct.get('delete', 'DELETED'),
            'OPEN_VALID_TO':    raw_delta.get('open_valid_to', '9999-12-31 23:59:59.999999'),
            'MAX_LOAD_ID':      str(raw_delta.get('max_load_id', 9223372036854775807)),
            'DWH_LOAD_ID_COL':  target_cfg['load_id']['name'],
            'DELETED_COL':      target_cfg['deleted_in_source']['name'],
            'DELETED_VAL':      target_cfg['deleted_in_source']['deleted_value'],
            'NOT_DELETED_VAL':  target_cfg['deleted_in_source']['not_deleted_value'],
            'META_DATABASE':    meta_db,
            'LOAD_STATE_TABLE': state_table,
            'ETL_JOB_ID':       str(job_id),
            'SOURCE_TABLE_ID':  str(source_table_id),
            'LOAD_WATERMARK':   (f"(SELECT COALESCE(MAX(LAST_LOAD_ID), 0) FROM {meta_db}.{state_table} "
                                 f"WHERE ETL_JOB_ID = {job_id})"),
            'VERSIONS_TABLE':   f"{staging_prefix}{source_table.lower()}_versions" if source_table else '',
            'BUSINESS_KEY_STG':  ', '.join(f'stg.{c}' for c in pk_columns),
            'BUSINESS_KEY_HIST': ', '.join(f'hist.{c}' for c in pk_columns),
            'BUSINESS_KEY_JOIN_TGT': ' AND '.join(f'tgt.{c} = f.{c}' for c in pk_columns),
            'BUSINESS_KEY_JOIN_PREV': ' AND '.join(f'stg.{c} = prev.{c}' for c in pk_columns),
        }

    def _check_delta_fk_mode(self, request) -> None:
        """Delta-Set: FK-Definitionen im Master-Modus ablehnen (siehe create_job_from_template)."""
        step_templates = self.get_step_templates(template_id=request.template_id)
        if not any(st.default_parameters and 'LOAD_WATERMARK' in st.default_parameters
                   for st in step_templates):
            return
        params = request.parameters or {}
        fk_defs = params.get('fk_definitions') or params.get('FK_DEFINITIONS') or []
        # fk_master_mappings (Wizard) sind erlaubt: _build_fk_defs_from_mappings liefert
        # dafür beim Delta-Set KEY-Modus-Definitionen
        if any(isinstance(d, dict) and d.get('master_mode') for d in fk_defs):
            raise ValueError(
                "Dieses Template-Set (Delta) braucht FK-Definitionen im KEY-Modus "
                "(key_table/domain/natural_key_expr). Der Master-Modus joint die Parent-History "
                "und liefert bei mehreren Parent-Versionen mehrere Zeilen je Satz."
            )

    @staticmethod
    def _add_missing_columns(cursor, conn, database: str, table: str, columns: List[tuple]) -> None:
        """Ergänzt fehlende Spalten [(name, definition)] einer bestehenden Tabelle per ALTER TABLE."""
        if not columns:
            return
        cursor.execute(
            "SELECT TRIM(ColumnName) FROM dbc.ColumnsV WHERE DatabaseName = ? AND TableName = ?",
            [database, table],
        )
        existing = {r[0].upper() for r in cursor.fetchall()}
        for name, definition in columns:
            if name.upper() in existing:
                continue
            cursor.execute(f"ALTER TABLE {database}.{table} ADD {definition}")
            conn.commit()
            logger.info(f"Spalte {name} in {database}.{table} ergänzt")

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
            sql = f"""
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
                    DEFAULT_IS_CURRENT_COLUMN,
                    USE_SK
                FROM {META_SCHEMA}.META_ETL_JOB_TEMPLATE
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
                    default_is_current_column=row[15],
                    use_sk=row[16].strip() if row[16] else 'N'
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
            cursor.execute(f"""
                INSERT INTO {META_SCHEMA}.META_ETL_JOB_TEMPLATE (
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
            cursor.execute(f"""
                SELECT TEMPLATE_ID 
                FROM {META_SCHEMA}.META_ETL_JOB_TEMPLATE 
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
            sql = f"""
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
                FROM {META_SCHEMA}.META_ETL_JOB_STEP_TEMPLATE
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
            
            cursor.execute(f"""
                INSERT INTO {META_SCHEMA}.META_ETL_JOB_STEP_TEMPLATE (
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
            cursor.execute(f"""
                SELECT MAX(STEP_TEMPLATE_ID) 
                FROM {META_SCHEMA}.META_ETL_JOB_STEP_TEMPLATE
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

            # Delta-Set: Parent-SKs nur aus KEY-Tabellen. Der Master-Modus joint die
            # Parent-History und liefert bei mehreren Parent-Versionen mehrere Zeilen.
            # Vor dem Anlegen des Jobs prüfen, damit kein halber Job entsteht.
            self._check_delta_fk_mode(request)

            # 2. Source Layer ID ermitteln
            cursor.execute(f"""
                SELECT LAYER_ID FROM {META_SCHEMA}.META_TABLE 
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
            target_created = False  # B2: Flag ob Zieltabelle neu angelegt wurde
            
            if not target_table_id and request.target_table_name:
                # Erst versuchen, Tabelle im TARGET-LAYER zu finden (NICHT im Source-Layer!)
                cursor.execute(f"""
                    SELECT TABLE_ID, LAYER_ID FROM {META_SCHEMA}.META_TABLE 
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
                    cursor.execute(f"""
                        SELECT DATABASE_ID FROM {META_SCHEMA}.META_DATABASE
                        WHERE LAYER_ID = ?
                        SAMPLE 1
                    """, [next_layer_id])
                    db_row = cursor.fetchone()
                    target_db_id = db_row[0] if db_row else 1  # Fallback
                    
                    # Nächste freie TABLE_ID holen (keine IDENTITY in Tabelle)
                    cursor.execute(f"SELECT COALESCE(MAX(TABLE_ID), 0) + 1 FROM {META_SCHEMA}.META_TABLE")
                    next_table_id = cursor.fetchone()[0]
                    
                    # Neue Tabelle in META_TABLE anlegen
                    cursor.execute(f"""
                        INSERT INTO {META_SCHEMA}.META_TABLE (
                            TABLE_ID, TABLE_NAME, DATABASE_ID, LAYER_ID
                        ) VALUES (?, ?, ?, ?)
                    """, [next_table_id, request.target_table_name, target_db_id, next_layer_id])
                    conn.commit()
                    
                    target_table_id = next_table_id
                    target_layer_id = next_layer_id
                    target_created = True  # B2: Neu angelegt
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
            cursor.execute(f"SELECT ETL_JOB_ID FROM {META_SCHEMA}.META_ETL_JOB WHERE JOB_NAME = ?", [request.job_name])
            existing_job = cursor.fetchone()
            if existing_job:
                raise ValueError(f"Job mit Namen '{request.job_name}' existiert bereits (ID: {existing_job[0]})")
            
            # 4. Job erstellen
            # Nächste freie Job-ID holen (keine IDENTITY in Tabelle)
            cursor.execute(f"SELECT COALESCE(MAX(ETL_JOB_ID), 0) + 1 FROM {META_SCHEMA}.META_ETL_JOB")
            next_job_id = cursor.fetchone()[0]
            
            cursor.execute(f"""
                INSERT INTO {META_SCHEMA}.META_ETL_JOB (
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
            extract_core_name = self._extract_core_name
            
            # ================================================================
            # Source-Infos automatisch aus source_table_id laden
            # ================================================================
            cursor.execute(f"""
                SELECT t.TABLE_NAME, d.DATABASE_NAME 
                FROM {META_SCHEMA}.META_TABLE t
                JOIN {META_SCHEMA}.META_DATABASE d ON t.DATABASE_ID = d.DATABASE_ID
                WHERE t.TABLE_ID = ?
            """, [request.source_table_id])
            src_row = cursor.fetchone()
            source_table_name = src_row[0] if src_row else ''
            source_database_name = src_row[1] if src_row else ''
            
            # Spalten aus META_COLUMN laden (für SELECT_COLUMNS)
            cursor.execute(f"""
                SELECT COLUMN_NAME FROM {META_SCHEMA}.META_COLUMN 
                WHERE TABLE_ID = ? 
                ORDER BY COLUMN_POSITION
            """, [request.source_table_id])
            all_source_columns = [r[0].upper() for r in cursor.fetchall()]
            
            # Primary Keys aus META_COLUMN laden (für BUSINESS_KEY)
            cursor.execute(f"""
                SELECT COLUMN_NAME FROM {META_SCHEMA}.META_COLUMN 
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

            # RAW-Technikspalten (Ladelauf, Snapshot-Zeit, Änderungsart) sind keine Fachspalten:
            # nie laden, nie hashen (cfg/parameter_rules.yml → raw_delta)
            raw_delta = self.param_rules.get('raw_delta', {}) or {}
            raw_tech_cols = {str(raw_delta.get(k, '')).upper()
                             for k in ('load_id_column', 'snapshot_column', 'change_type_column')} - {''}
            if raw_tech_cols:
                if isinstance(hash_columns, list):
                    hash_columns = [c for c in hash_columns if str(c).upper() not in raw_tech_cols]
                if isinstance(select_columns, list):
                    select_columns = [c for c in select_columns if str(c).upper() not in raw_tech_cols]

            # Delta-Set (z.B. RAW_TO_DISC_SCD2_DELTA): erkennbar am Parameter LOAD_WATERMARK
            is_delta_set = any(
                st.default_parameters and 'LOAD_WATERMARK' in st.default_parameters
                for st in step_templates
            )
            
            # Core-Name aus Source-Tabelle (oder Target als Fallback)
            core_name = extract_core_name(new_source) if new_source else extract_core_name(new_target)
            
            # Layer-Config laden (basierend auf target_layer_id)
            # Layer-ID -> Name Mapping
            layer_id_to_name = {1: 'raw', 2: 'discoverable', 3: 'reusable', 4: 'consumable'}
            layers_config = self._layers_config(cursor, layer_id_to_name)
            staging_config = self.param_rules.get('staging', {})

            target_layer_name = layer_id_to_name.get(target_layer_id, 'discoverable')
            target_layer_config = layers_config.get(target_layer_name, {})
            
            # Werte aus Layer-Config
            key_table_prefix = target_layer_config.get('key_prefix', 'KEY_')
            key_database = target_layer_config.get('database', 'MDP01_DISCOVERABLE_LAYER')
            history_suffix = target_layer_config.get('history_suffix', '_HISTORY')
            
            # Staging aus eigener Config
            staging_prefix = staging_config.get('prefix', 'temp_')
            staging_suffix = staging_config.get('suffix', '_staging')

            # Composite Key Separator aus Config
            ck_config = self.param_rules.get('composite_key', {})
            ck_separator = ck_config.get('separator', '~|~')
            ck_max_col_length = int(ck_config.get('max_col_length', 100))

            # Composite Key SQL-Ausdrücke generieren
            pk_list = pk_columns if isinstance(pk_columns, list) else ([pk_columns] if pk_columns else [])
            ck_params = self._build_composite_key_params(pk_list, ck_separator, ck_max_col_length)

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

            # SCD2-Spaltennamen + Flag-Werte aus Config (C-b: zentral aus parameter_rules.yml,
            # statt projektspezifischer REUS_-Defaults in den Step-Templates)
            vf_cfg = scd2_config.get('valid_from', {})
            vt_cfg = scd2_config.get('valid_to', {})
            ic_cfg = scd2_config.get('is_current', {})
            gueltigvon_col = vf_cfg.get('name', 'VALID_FROM') if isinstance(vf_cfg, dict) else 'VALID_FROM'
            gueltigbis_col = vt_cfg.get('name', 'VALID_TO') if isinstance(vt_cfg, dict) else 'VALID_TO'
            ist_aktuell_col = ic_cfg.get('name', 'IS_CURRENT') if isinstance(ic_cfg, dict) else 'IS_CURRENT'
            ist_aktuell_val = ic_cfg.get('current_value', 'Y') if isinstance(ic_cfg, dict) else 'Y'
            ist_aktuell_geschlossen = ic_cfg.get('closed_value', 'N') if isinstance(ic_cfg, dict) else 'N'

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
                'BUSINESS_KEY_TGT_JOIN': ' AND '.join([f'{key_database}.{new_target}.{c} = chg.{c}' for c in pk_columns]) if pk_columns else '',
                **ck_params,
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
                # SCD2-Spaltennamen + Flag-Werte aus Config (C-b)
                'GUELTIGVON_COL': gueltigvon_col,
                'GUELTIGBIS_COL': gueltigbis_col,
                'IST_AKTUELL_COL': ist_aktuell_col,
                'IST_AKTUELL_VAL': ist_aktuell_val,
                'IST_AKTUELL_GESCHLOSSEN': ist_aktuell_geschlossen,
                # Weitere SCD2-/Audit-Spaltennamen aus Config (für Templates ohne feste Namen)
                **self._scd2_column_names_params(scd2_config),
            }

            # Delta-Parameter (RAW_TO_DISC_SCD2_DELTA); für andere Sets wirkungslos,
            # weil der DEFAULT_PARAMETERS-Filter unten nur angeforderte Keys übernimmt
            generated_values.update(self._raw_delta_params(
                raw_delta=raw_delta,
                job_id=job_id,
                source_table_id=request.source_table_id,
                pk_columns=pk_columns if isinstance(pk_columns, list) else [],
                staging_prefix=staging_prefix,
                source_table=new_source,
                scd2_config=scd2_config,
            ))

            logger.debug(f"Parameter-Generierung: source={new_source}, core_name={core_name}, pk_columns={pk_columns}, select_columns={len(select_columns)} Spalten")

            # F6-Beladung: fk_definitions aus Master-Mappings ableiten (Master-Modus).
            # mappings: [{ table_id, source_column }]  → liefert FK_SK_COLUMNS/FK_INSERT_COLUMNS/FK_JOINS
            fk_master_mappings = []
            if request.parameters:
                raw_map = (request.parameters.get('fk_master_mappings')
                           or request.parameters.get('FK_MASTER_MAPPINGS') or [])
                if isinstance(raw_map, list):
                    fk_master_mappings = raw_map
            # Delta-Set: KEY-Modus (Parent-SK aus KEY_*), sonst Master-Modus wie bisher
            set_domain = next((st.default_parameters.get('DOMAIN') for st in step_templates
                               if st.default_parameters and st.default_parameters.get('DOMAIN')), '')
            derived_fk_definitions = (
                self._build_fk_defs_from_mappings(
                    cursor, fk_master_mappings,
                    key_mode=is_delta_set, domain=set_domain, layers_config=layers_config,
                )
                if fk_master_mappings else []
            )
            fk_column_names = [d['sk_column'] for d in derived_fk_definitions]
            if derived_fk_definitions:
                logger.info(f"F6-Beladung: {len(derived_fk_definitions)} FK-Definitionen abgeleitet: {fk_column_names}")

            for step_tpl in step_templates:
                # Alle Parameter zusammenführen (generated + defaults + user)
                all_params = generated_values.copy()

                # Template-Defaults hinzufügen falls vorhanden (überschreibt nicht)
                if step_tpl.default_parameters:
                    for key, value in step_tpl.default_parameters.items():
                        if key not in all_params:
                            all_params[key] = value

                # User-Parameter überschreiben (explizit mitgegeben)
                if request.parameters:
                    for key, value in request.parameters.items():
                        all_params[key] = value

                # DEFAULT_PARAMETERS Keys = exakte Liste der Parameter die dieser Step braucht
                # Werte kommen aus generated_values (überschreiben die Template-Defaults)
                if step_tpl.default_parameters:
                    parameters = {k: all_params[k] for k in step_tpl.default_parameters if k in all_params}
                else:
                    parameters = all_params

                # lowercase Listen aus generated_values ergänzen (für template_engine._prepare_parameters)
                # z.B. hash_columns (list) damit HASH_EXPRESSION gebaut werden kann
                for k, v in generated_values.items():
                    if isinstance(v, list) and k.upper() in parameters and k not in parameters:
                        parameters[k] = v

                # FK_DEFINITIONS (list) aus request.parameters in Step-Parameter übernehmen
                # (kommt vom Wizard, muss als lowercase 'fk_definitions' in parameters stehen
                #  damit template_engine._prepare_parameters es verarbeiten kann)
                if derived_fk_definitions:
                    # F6-Beladung: aus Master-Mappings abgeleitete FK-Definitionen (Master-Modus)
                    parameters['fk_definitions'] = derived_fk_definitions
                elif request.parameters and 'fk_definitions' in request.parameters:
                    parameters['fk_definitions'] = request.parameters['fk_definitions']
                elif request.parameters and 'FK_DEFINITIONS' in request.parameters:
                    parameters['fk_definitions'] = request.parameters['FK_DEFINITIONS']
                
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
                
                cursor.execute(f"""
                    INSERT INTO {META_SCHEMA}.META_ETL_JOB_STEP (
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
                    # Template-Prefix voranhängen: RAW_TO_DISC_SCD2/delete/delete_target_table.sql
                    f"{template.template_code}/{step_tpl.sql_template_path}" if step_tpl.sql_template_path else None,
                    step_sql_inline,
                    json.dumps(parameters) if parameters else None
                ])
            
            conn.commit()
            logger.info(f"Job {job_id} aus Template {request.template_id} erstellt mit {len(step_templates)} Steps")

            # F4-B: Parameter-JSONs für alle Steps in etl/jobs/{job_id}/ schreiben
            try:
                from .template_engine import write_step_parameters
                cursor.execute(
                    f"SELECT ETL_JOB_STEP_ID, PARAMETERS FROM {META_SCHEMA}.META_ETL_JOB_STEP WHERE ETL_JOB_ID = ?",
                    [job_id]
                )
                for step_row in cursor.fetchall():
                    s_id, s_params = step_row[0], step_row[1]
                    if s_params:
                        try:
                            params_dict = json.loads(s_params) if isinstance(s_params, str) else s_params
                            write_step_parameters(job_id, int(s_id), params_dict, get_etl_jobs_path())
                        except Exception as e:
                            logger.warning(f"Parameter-JSON für Step {s_id} nicht geschrieben: {e}")
            except Exception as e:
                logger.warning(f"Parameter-JSON Schreiben für Job {job_id} fehlgeschlagen: {e}")
            
            # Key-Tabelle automatisch erstellen wenn nicht vorhanden
            if key_table_name and key_database:
                self._ensure_key_table_exists(cursor, conn, key_database, key_table_name)
            
            # Ziel-Tabelle physisch in Teradata anlegen wenn nicht vorhanden (AF-009)
            target_ddl_generated = None
            if new_target and key_database:
                target_ddl_generated = self._ensure_target_table_exists(
                    cursor, conn,
                    key_database,
                    new_target,
                    request.source_table_id,
                    pk_columns if isinstance(pk_columns, list) else [],
                    core_name=core_name,
                    fk_columns=fk_column_names,
                    extra_columns=self._raw_delta_target_columns(raw_delta) if is_delta_set else None,
                )

            # B2a: IS_BUSINESS_KEY in Source-META_COLUMN setzen (falls noch nicht gesetzt)
            pk_list = pk_columns if isinstance(pk_columns, list) else ([pk_columns] if pk_columns else [])
            if pk_list:
                for pk_col in pk_list:
                    try:
                        cursor.execute(f"""
                            UPDATE {META_SCHEMA}.META_COLUMN
                            SET IS_BUSINESS_KEY = 'Y', AENDERUNGSDATUM = CURRENT_TIMESTAMP(6)
                            WHERE TABLE_ID = ? AND COLUMN_NAME = ?
                        """, [request.source_table_id, pk_col.upper()])
                    except Exception as e:
                        logger.warning(f"IS_BUSINESS_KEY Update für {pk_col} fehlgeschlagen: {e}")
                conn.commit()

            # B2b: META_COLUMN für neue Zieltabelle anlegen (Spalten + SCD2-Technische-Spalten)
            if target_created and target_table_id:
                sel_cols = select_columns if isinstance(select_columns, list) else ([select_columns] if select_columns else [])
                hash_list = hash_columns if isinstance(hash_columns, list) else ([hash_columns] if hash_columns else [])
                # F7: SK als Primary Index? (editierbar im Wizard, Default 'Y')
                sk_is_pi = 'Y'
                if request.parameters:
                    raw_sk_pi = (request.parameters.get('sk_is_pi')
                                 or request.parameters.get('SK_IS_PI') or 'Y')
                    sk_is_pi = 'Y' if str(raw_sk_pi).strip().upper() in ('Y', 'TRUE', '1') else 'N'
                self._populate_target_columns_in_meta(
                    cursor, conn,
                    target_table_id=target_table_id,
                    source_table_id=request.source_table_id,
                    select_columns=sel_cols,
                    core_name=core_name,
                    pk_columns=pk_list,
                    hash_columns=hash_list,
                    sk_is_pi=sk_is_pi,
                    fk_columns=fk_column_names,
                )

            # F6: FK über Master-Tabellen – FK-Spalte ({MASTER_SK}_FK) in META_COLUMN
            #     anlegen + META_FOREIGN_KEY-Beziehung schreiben (auch bei bestehender Zieltabelle)
            fk_master_ids = []
            if request.parameters:
                raw_master = (request.parameters.get('fk_master_table_ids')
                              or request.parameters.get('FK_MASTER_TABLE_IDS') or [])
                if isinstance(raw_master, list):
                    fk_master_ids = raw_master
            # Fallback: Master-IDs aus den Mappings ableiten (Wizard sendet beides)
            if not fk_master_ids and fk_master_mappings:
                fk_master_ids = [m.get('table_id') for m in fk_master_mappings if m.get('table_id')]
            if target_table_id and fk_master_ids:
                self._create_fk_from_master_tables(cursor, conn, target_table_id, fk_master_ids)

            # F5-A: DDLs + Cleanup-SQLs im Job-Folder ablegen
            self._write_job_folder_artifacts(
                job_id=job_id,
                target_database=key_database or '',
                target_table=new_target or '',
                key_database=key_database or '',
                key_table_name=key_table_name,
                core_name=core_name,
                source_table_id=request.source_table_id,
                cursor=cursor,
            )

            # F5-B: DDL-Steps am Anfang des Jobs einfügen (Create Target + Create SK)
            # step_category = 'DDL_CREATE' → Orchestrator ignoriert Error 3803 (bereits vorhanden)
            self._insert_ddl_steps(
                cursor, conn,
                job_id=job_id,
                target_database=key_database or '',
                target_table=new_target or '',
                key_database=key_database or '',
                key_table_name=key_table_name or '',
                target_ddl=target_ddl_generated,
            )

            return {"job_id": job_id, "target_table_id": target_table_id, "target_created": target_created}
            
        finally:
            cursor.close()
            conn.close()
    
    @staticmethod
    def _filter_params_for_step(
        all_params: dict,
        sql_template_path: Optional[str],
        template_base_dir: str
    ) -> dict:
        """
        Filtert Parameter für einen Step: Nur Keys zurückgeben die das Template wirklich braucht.

        Liest das Template-File, extrahiert alle ${KEY} Platzhalter aus nicht-Kommentar-Zeilen
        und gibt nur die passenden Keys aus all_params zurück.

        Falls das Template nicht gefunden wird, werden alle Parameter zurückgegeben (safe fallback).
        """
        if not sql_template_path:
            return all_params

        import re
        template_file = Path(template_base_dir) / sql_template_path
        if not template_file.exists():
            return all_params

        with open(template_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Nur nicht-Kommentar-Zeilen auswerten
        used_keys = set()
        for line in lines:
            if not line.lstrip().startswith('--'):
                for key in re.findall(r'\$\{([^}]+)\}', line):
                    used_keys.add(key)

        # Nur die benötigten Keys zurückgeben
        return {k: v for k, v in all_params.items() if k in used_keys}

    @staticmethod
    def _build_composite_key_params(pk_columns: list, separator: str, max_col_length: int = 100) -> dict:
        """
        Generiert SQL-Ausdrücke für Composite Natural Keys.

        Bei einem einzelnen PK-Schlüssel wird ein einfacher CAST erzeugt.
        Bei mehreren PK-Spalten werden die Werte mit dem Separator konkateniert:
          TRIM(CAST(col1 AS VARCHAR(n))) || 'sep' || TRIM(CAST(col2 AS VARCHAR(n)))

        Returns:
            Dict mit SQL-Ausdrücken für verschiedene Table-Alias-Kontexte.
        """
        if not pk_columns:
            return {
                'NATURAL_KEY_EXPRESSION':     '',
                'NATURAL_KEY_EXPRESSION_SRC': '',
                'NATURAL_KEY_EXPRESSION_STG': '',
                'BUSINESS_KEY_JOIN':          '',
                'BUSINESS_KEY_NULL_CHECK':    '',
                'BUSINESS_KEY_TGT_JOIN':      '',
                'PRIMARY_INDEX_COLS':         '',
            }

        # SQL-Trennzeichen: einfache Quotes escapen
        quoted_sep = separator.replace("'", "''")

        def make_expression(alias: str, cols: list) -> str:
            prefix = f"{alias}." if alias else ""
            if len(cols) == 1:
                return f"CAST({prefix}{cols[0]} AS VARCHAR(255))"
            parts = [f"TRIM(CAST({prefix}{c} AS VARCHAR({max_col_length})))" for c in cols]
            return f" || '{quoted_sep}' || ".join(parts)

        return {
            # Kein Alias (für direkte Tabellenreferenz ohne Alias)
            'NATURAL_KEY_EXPRESSION':     make_expression('', pk_columns),
            # Mit src. Alias (für INSERT-Templates)
            'NATURAL_KEY_EXPRESSION_SRC': make_expression('src', pk_columns),
            # Mit stg. Alias (für Staging-Templates)
            'NATURAL_KEY_EXPRESSION_STG': make_expression('stg', pk_columns),
            # JOIN-Bedingung: stg.col1 = hist.col1 AND stg.col2 = hist.col2
            'BUSINESS_KEY_JOIN':    ' AND '.join([f'stg.{c} = hist.{c}' for c in pk_columns]),
            # NULL-Check auf erste PK-Spalte (für identify_new_records)
            'BUSINESS_KEY_NULL_CHECK': f'hist.{pk_columns[0]} IS NULL',
            # PRIMARY INDEX Spalten (kommasepariert)
            'PRIMARY_INDEX_COLS':   ', '.join(pk_columns),
        }

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
    
    def _build_fk_defs_from_mappings(self, cursor, mappings: List[dict], key_mode: bool = False,
                                     domain: str = '', layers_config: Dict[str, dict] = None) -> list:
        """
        F6-Beladung: Leitet aus den Master-Mappings des Wizards `fk_definitions`
        ab (für template_engine._build_fk_expressions).

        mappings: [{ "table_id": <master_id>, "source_column": "<Quellspalte>" }, ...]

        Pro Master:
          - Master-DB/-Tabelle aus META_TABLE/META_DATABASE
          - Master-SK  (IS_PK='Y', Fallback IS_TECHNICAL_KEY='Y')
          - FK-Spaltenname {MASTER_SK}_FK

        Master-Modus (Standard, z.B. RAW_TO_DISC_SCD2_FK): Join auf die Master-Tabelle
        über ihren Business Key (IS_BUSINESS_KEY='Y'), master_mode=True.

        KEY-Modus (key_mode=True, Delta-Set RAW_TO_DISC_SCD2_DELTA): Join auf die
        KEY-Tabelle des Parents, abgeleitet wie KEY_TABLE beim Parent-Job:
        key_prefix + Kernname der Parent-Tabelle (ohne history_suffix), Datenbank
        der Parent-Schicht, Domain des Template-Sets. Unabhängig von der Version
        des Parents (kein Fan-out bei historisierten Parents).
        """
        col_tbl = f"{META_SCHEMA}.META_COLUMN"
        defs = []
        for m in (mappings or []):
            try:
                master_id = int(m.get('table_id'))
            except (TypeError, ValueError):
                continue
            source_col = (m.get('source_column') or '').strip()
            if not source_col:
                # Ohne gemappte Quellspalte kann keine Beladung gebaut werden
                continue

            # Master-DB/-Tabelle
            cursor.execute(f"""
                SELECT t.TABLE_NAME, d.DATABASE_NAME
                FROM {META_SCHEMA}.META_TABLE t
                JOIN {META_SCHEMA}.META_DATABASE d ON t.DATABASE_ID = d.DATABASE_ID
                WHERE t.TABLE_ID = ? SAMPLE 1
            """, [master_id])
            row = cursor.fetchone()
            if not row:
                logger.warning(f"F6-Beladung: Master-Tabelle {master_id} nicht gefunden, übersprungen")
                continue
            master_tbl, master_db = (row[0] or '').strip(), (row[1] or '').strip()

            # Master-SK (IS_PK, Fallback IS_TECHNICAL_KEY)
            cursor.execute(f"""
                SELECT COLUMN_NAME FROM {col_tbl}
                WHERE TABLE_ID = ? AND TRIM(IS_PK) = 'Y'
                ORDER BY COLUMN_POSITION SAMPLE 1
            """, [master_id])
            sk_row = cursor.fetchone()
            if not sk_row:
                cursor.execute(f"""
                    SELECT COLUMN_NAME FROM {col_tbl}
                    WHERE TABLE_ID = ? AND TRIM(IS_TECHNICAL_KEY) = 'Y'
                    ORDER BY COLUMN_POSITION SAMPLE 1
                """, [master_id])
                sk_row = cursor.fetchone()
            if not sk_row:
                logger.warning(f"F6-Beladung: Keine SK-Spalte in Master {master_id}, übersprungen")
                continue
            master_sk = (sk_row[0] or '').strip().upper()
            natural_key_expr = f"CAST(src.{source_col.upper()} AS VARCHAR(255))"

            if key_mode:
                key_db, key_tbl = self._parent_key_table(cursor, master_id, master_tbl, master_db,
                                                         layers_config or {})
                if not domain:
                    logger.warning(f"F6-Beladung: keine DOMAIN im Template-Set, FK zu Master {master_id} übersprungen")
                    continue
                defs.append({
                    'sk_column':        f"{master_sk}_FK",
                    'key_database':     key_db,
                    'key_table':        key_tbl,
                    'natural_key_expr': natural_key_expr,
                    'domain':           domain,
                })
                continue

            # Master-BK (IS_BUSINESS_KEY)
            cursor.execute(f"""
                SELECT COLUMN_NAME FROM {col_tbl}
                WHERE TABLE_ID = ? AND TRIM(IS_BUSINESS_KEY) = 'Y'
                ORDER BY COLUMN_POSITION SAMPLE 1
            """, [master_id])
            bk_row = cursor.fetchone()
            if not bk_row:
                logger.warning(f"F6-Beladung: Kein Business Key in Master {master_id}, übersprungen")
                continue
            master_bk = (bk_row[0] or '').strip().upper()

            defs.append({
                'sk_column':        f"{master_sk}_FK",
                'key_database':     master_db,
                'key_table':        master_tbl,
                'parent_sk_column': master_sk,
                'parent_bk_column': master_bk,
                'natural_key_expr': natural_key_expr,
                'master_mode':      True,
            })
        return defs

    def _parent_key_table(self, cursor, master_id: int, master_tbl: str, master_db: str,
                          layers_config: Dict[str, dict]) -> tuple:
        """(key_database, key_table) der KEY-Tabelle eines Parents.

        Gleiche Regeln wie KEY_TABLE/KEY_DATABASE beim Parent-Job: Kernname aus dem
        Tabellennamen (history_suffix der Parent-Schicht abgeschnitten), key_prefix und
        Datenbank der Parent-Schicht aus der Layer-Config.
        """
        layer_id_to_name = {1: 'raw', 2: 'discoverable', 3: 'reusable', 4: 'consumable'}
        cursor.execute(f"SELECT LAYER_ID FROM {META_SCHEMA}.META_TABLE WHERE TABLE_ID = ?", [master_id])
        row = cursor.fetchone()
        layer_cfg = layers_config.get(layer_id_to_name.get(row[0] if row else None, ''), {})
        base = master_tbl
        suffix = layer_cfg.get('history_suffix', '')
        if suffix and base.upper().endswith(suffix.upper()):
            base = base[: -len(suffix)]
        key_tbl = f"{layer_cfg.get('key_prefix', 'KEY_')}{self._extract_core_name(base).upper()}"
        key_db = layer_cfg.get('database', master_db)
        cursor.execute("SELECT 1 FROM dbc.TablesV WHERE DatabaseName = ? AND TableName = ?", [key_db, key_tbl])
        if not cursor.fetchone():
            logger.warning(f"F6-Beladung: KEY-Tabelle {key_db}.{key_tbl} des Parents {master_tbl} existiert nicht")
        return key_db, key_tbl

    def _create_fk_from_master_tables(
        self,
        cursor,
        conn,
        target_table_id: int,
        master_table_ids: List[int],
    ) -> None:
        """
        F6-B/C: FK über Master-Tabellen.

        Für jede Master-Tabelle:
          1. SK/PK-Spalte der Master-Tabelle ermitteln (IS_PK='Y', Fallback IS_TECHNICAL_KEY='Y')
          2. FK-Spalte {MASTER_SK}_FK in META_COLUMN der Zieltabelle anlegen (BIGINT, IS_FK='Y')
          3. META_FOREIGN_KEY-Beziehung schreiben (child=Ziel/FK-Spalte, parent=Master/SK)

        Idempotent: vorhandene FK-Spalten/Beziehungen werden übersprungen.
        """
        col_tbl = f"{META_SCHEMA}.META_COLUMN"
        fk_tbl  = f"{META_SCHEMA}.META_FOREIGN_KEY"

        # DATATYPE_ID für BIGINT
        try:
            cursor.execute(
                f"SELECT DATATYPE_ID FROM {META_SCHEMA}.META_DATATYPE WHERE TERADATA_TYPE = 'BIGINT' SAMPLE 1"
            )
            r = cursor.fetchone()
            bigint_id = int(r[0]) if r else 1
        except Exception:
            bigint_id = 1

        for raw_id in master_table_ids:
            try:
                master_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if master_id == target_table_id:
                continue

            # 1. SK/PK-Spalte der Master-Tabelle ermitteln
            cursor.execute(f"""
                SELECT COLUMN_ID, COLUMN_NAME FROM {col_tbl}
                WHERE TABLE_ID = ? AND TRIM(IS_PK) = 'Y'
                ORDER BY COLUMN_POSITION SAMPLE 1
            """, [master_id])
            row = cursor.fetchone()
            if not row:
                cursor.execute(f"""
                    SELECT COLUMN_ID, COLUMN_NAME FROM {col_tbl}
                    WHERE TABLE_ID = ? AND TRIM(IS_TECHNICAL_KEY) = 'Y'
                    ORDER BY COLUMN_POSITION SAMPLE 1
                """, [master_id])
                row = cursor.fetchone()
            if not row:
                logger.warning(f"F6: Keine SK/PK-Spalte in Master-Tabelle {master_id} gefunden, FK übersprungen")
                continue

            master_sk_col_id   = int(row[0])
            master_sk_col_name = (row[1] or '').strip()
            fk_col_name        = f"{master_sk_col_name.upper()}_FK"

            # 2. FK-Spalte in Zieltabelle anlegen (falls nicht vorhanden)
            cursor.execute(f"""
                SELECT COLUMN_ID FROM {col_tbl}
                WHERE TABLE_ID = ? AND UPPER(COLUMN_NAME) = ? SAMPLE 1
            """, [target_table_id, fk_col_name])
            existing = cursor.fetchone()
            if existing:
                fk_col_id = int(existing[0])
            else:
                cursor.execute(f"SELECT COALESCE(MAX(COLUMN_ID), 0) + 1 FROM {col_tbl}")
                fk_col_id = int(cursor.fetchone()[0])
                cursor.execute(
                    f"SELECT COALESCE(MAX(COLUMN_POSITION), 0) + 1 FROM {col_tbl} WHERE TABLE_ID = ?",
                    [target_table_id]
                )
                fk_col_pos = int(cursor.fetchone()[0])
                cursor.execute(f"""
                    INSERT INTO {col_tbl}
                        (COLUMN_ID, TABLE_ID, COLUMN_NAME, COLUMN_POSITION,
                         DATATYPE_ID, COLUMN_TYPE, NULLABLE, IS_FK,
                         ERSTERFASSUNGSDATUM, AENDERUNGSDATUM)
                    VALUES (?, ?, ?, ?, ?, 'BIGINT', 'Y', 'Y',
                            CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
                """, [fk_col_id, target_table_id, fk_col_name, fk_col_pos, bigint_id])
                conn.commit()
                logger.info(
                    f"F6-B: FK-Spalte {fk_col_name} (col_id={fk_col_id}) in Zieltabelle {target_table_id} angelegt"
                )

            # 3. META_FOREIGN_KEY-Beziehung (falls nicht vorhanden)
            cursor.execute(f"""
                SELECT FK_ID FROM {fk_tbl}
                WHERE CHILD_TABLE_ID = ? AND CHILD_COLUMN_ID = ? AND PARENT_TABLE_ID = ? SAMPLE 1
            """, [target_table_id, fk_col_id, master_id])
            if cursor.fetchone():
                logger.debug(f"F6-C: FK-Beziehung {target_table_id}->{master_id} existiert bereits, übersprungen")
                continue

            cursor.execute(f"SELECT COALESCE(MAX(FK_ID), 0) + 1 FROM {fk_tbl}")
            new_fk_id = int(cursor.fetchone()[0])
            fk_name   = f"FK_{fk_col_name}"
            cursor.execute(f"""
                INSERT INTO {fk_tbl}
                    (FK_ID, FK_NAME, CHILD_TABLE_ID, CHILD_COLUMN_ID,
                     PARENT_TABLE_ID, PARENT_COLUMN_ID,
                     ERSTERFASSUNGSDATUM, AENDERUNGSDATUM)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
            """, [new_fk_id, fk_name, target_table_id, fk_col_id, master_id, master_sk_col_id])
            conn.commit()
            logger.info(
                f"F6-C: FK-Beziehung {fk_name} (fk_id={new_fk_id}) "
                f"{target_table_id}.{fk_col_name} -> {master_id}.{master_sk_col_name} angelegt"
            )

        # meta_service-Cache invalidieren, damit Modeler die neuen Spalten/FKs sieht
        try:
            from app.services import meta_service
            for k in list(meta_service._CACHE.keys()):
                if k.startswith("fk|") or k.startswith("columns_full|"):
                    meta_service._CACHE.pop(k, None)
        except Exception:
            pass

    def _populate_target_columns_in_meta(
        self,
        cursor,
        conn,
        target_table_id: int,
        source_table_id: int,
        select_columns: List[str],
        core_name: str = '',
        pk_columns: List[str] = None,
        hash_columns: List[str] = None,
        sk_is_pi: str = 'Y',
        fk_columns: List[str] = None,
    ) -> int:
        """
        B2: Erstellt META_COLUMN-Einträge für eine neu angelegte Zieltabelle.

        Reihenfolge:
          1. SCD2-Technische-Spalten (SK, VALID_FROM, VALID_TO, IS_CURRENT, RECORD_HASH, Audit)
          2. Source-Spalten (aus select_columns, Typ/Länge aus META_COLUMN der Source)

        Überspringt falls für diese table_id bereits Einträge vorhanden.
        """
        col_tbl = f"{META_SCHEMA}.META_COLUMN"

        # Prüfen ob bereits Spalten vorhanden
        cursor.execute(f"SELECT COUNT(*) FROM {col_tbl} WHERE TABLE_ID = ?", [target_table_id])
        existing_count = cursor.fetchone()[0]
        if existing_count > 0:
            logger.debug(f"META_COLUMN für table_id={target_table_id} bereits vorhanden ({existing_count}), übersprungen")
            return existing_count

        # Nächste freie COLUMN_ID
        cursor.execute(f"SELECT COALESCE(MAX(COLUMN_ID), 0) + 1 FROM {col_tbl}")
        next_col_id = int(cursor.fetchone()[0])

        def _get_datatype_id(col_type_str: str) -> int:
            """Lookup DATATYPE_ID aus META_DATATYPE; Fallback 1 (unbekannt)."""
            try:
                base_type = col_type_str.split('(')[0].strip().upper()
                cursor.execute(
                    f"SELECT DATATYPE_ID FROM {META_SCHEMA}.META_DATATYPE WHERE TERADATA_TYPE = ? SAMPLE 1",
                    [base_type]
                )
                row = cursor.fetchone()
                return int(row[0]) if row else 1
            except Exception:
                return 1

        scd2_config = self.param_rules.get('scd2_technical_columns', {})
        col_position = 1
        inserted = 0
        pk_set   = {c.upper() for c in (pk_columns or [])}
        hash_set = {c.upper() for c in (hash_columns or [])}
        # Dedup: Spaltennamen die bereits ausgegeben wurden (verhindert Doppel-Spalte,
        # z.B. wenn die DISC→REUS-Quell-View die SK-Spalte bereits enthält → Error 2803)
        seen_cols = set()

        # Reihenfolge (User-Wunsch): 1. SK  2. Source-Spalten (ID/BK …)  3. FK-Spalten  4. Technische ans Ende
        # --- 1. SK (Surrogate Key) ---
        sk_cfg = scd2_config.get('surrogate_key')
        if sk_cfg:
            pattern  = sk_cfg.get('pattern', '{core_name}_SK')
            fallback = sk_cfg.get('fallback', 'SURROGATE_KEY')
            sk_name  = pattern.replace('{core_name}', core_name.upper()) if core_name else fallback
            sk_type  = sk_cfg.get('type', 'BIGINT')
            sk_null  = 'N' if not sk_cfg.get('nullable', True) else 'Y'
            cursor.execute(f"""
                INSERT INTO {col_tbl}
                    (COLUMN_ID, TABLE_ID, COLUMN_NAME, COLUMN_POSITION,
                     DATATYPE_ID, COLUMN_TYPE, NULLABLE,
                     IS_TECHNICAL_KEY, IS_PK, IS_PI, IS_SCD_COLUMN, IS_AUDIT_COLUMN,
                     ERSTERFASSUNGSDATUM, AENDERUNGSDATUM)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Y', 'Y', ?, 'N', 'N',
                        CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
            """, [next_col_id, target_table_id, sk_name, col_position,
                  _get_datatype_id(sk_type), sk_type, sk_null, sk_is_pi])
            seen_cols.add(sk_name.upper())
            next_col_id  += 1
            col_position += 1
            inserted     += 1

        # --- 2. Source-Spalten (Typ/Länge aus META_COLUMN der Source) ---
        cursor.execute(f"""
            SELECT COLUMN_NAME, DATATYPE_ID, COLUMN_TYPE, COLUMN_LENGTH,
                   DECIMAL_TOTAL_DIGITS, DECIMAL_FRACTIONAL_DIGITS,
                   NULLABLE, IS_BUSINESS_KEY, CHARSET
            FROM {META_SCHEMA}.META_COLUMN
            WHERE TABLE_ID = ?
            ORDER BY COLUMN_POSITION
        """, [source_table_id])
        source_col_map = {r[0].upper(): r for r in cursor.fetchall()}

        for col_name in select_columns:
            col_upper = col_name.upper()
            # Dedup: Quellspalte überspringen, wenn Name bereits vergeben (z.B. SK aus der View)
            if col_upper in seen_cols:
                logger.debug(f"META_COLUMN: Quellspalte {col_upper} übersprungen (bereits vorhanden)")
                continue
            src = source_col_map.get(col_upper)
            if src:
                _, src_dt_id, col_type, col_length, dec_total, dec_frac, nullable, is_bk, charset = src
                datatype_id = int(src_dt_id) if src_dt_id else _get_datatype_id(col_type or 'VARCHAR')
            else:
                col_type, col_length, dec_total, dec_frac, nullable, is_bk, charset = \
                    'VARCHAR(255)', None, None, None, 'Y', 'N', None
                datatype_id = 1

            # BK: aus pk_columns (überschreibt Source-Flag) oder Source-Flag als Fallback
            final_bk   = 'Y' if col_upper in pk_set else (is_bk or 'N')
            # Hash: aus hash_columns
            final_hash = 'Y' if col_upper in hash_set else 'N'

            cursor.execute(f"""
                INSERT INTO {col_tbl}
                    (COLUMN_ID, TABLE_ID, COLUMN_NAME, COLUMN_POSITION,
                     DATATYPE_ID, COLUMN_TYPE, COLUMN_LENGTH,
                     DECIMAL_TOTAL_DIGITS, DECIMAL_FRACTIONAL_DIGITS,
                     NULLABLE, IS_BUSINESS_KEY, IS_HASH,
                     IS_TECHNICAL_KEY, IS_PI, IS_SCD_COLUMN, IS_AUDIT_COLUMN,
                     CHARSET,
                     ERSTERFASSUNGSDATUM, AENDERUNGSDATUM)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'N', 'N', 'N', 'N', ?,
                        CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
            """, [next_col_id, target_table_id, col_upper, col_position,
                  datatype_id, col_type, col_length, dec_total, dec_frac,
                  nullable or 'Y', final_bk, final_hash, charset])
            seen_cols.add(col_upper)
            next_col_id  += 1
            col_position += 1
            inserted     += 1

        # --- 3. FK-Spalten ({MASTER_SK}_FK, BIGINT) – F6-Beladung, vor den technischen Spalten ---
        bigint_dt_id = _get_datatype_id('BIGINT')
        for fk_col in (fk_columns or []):
            fk_name = (fk_col or '').strip().upper()
            if not fk_name or fk_name in seen_cols:
                continue
            cursor.execute(f"""
                INSERT INTO {col_tbl}
                    (COLUMN_ID, TABLE_ID, COLUMN_NAME, COLUMN_POSITION,
                     DATATYPE_ID, COLUMN_TYPE, NULLABLE, IS_FK,
                     IS_TECHNICAL_KEY, IS_PK, IS_PI, IS_SCD_COLUMN, IS_AUDIT_COLUMN,
                     ERSTERFASSUNGSDATUM, AENDERUNGSDATUM)
                VALUES (?, ?, ?, ?, ?, 'BIGINT', 'Y', 'Y', 'N', 'N', 'N', 'N', 'N',
                        CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
            """, [next_col_id, target_table_id, fk_name, col_position, bigint_dt_id])
            seen_cols.add(fk_name)
            next_col_id  += 1
            col_position += 1
            inserted     += 1

        # --- 4. Technische SCD2-Spalten ans Ende ---
        scd2_order = [
            'valid_from', 'valid_to', 'is_current',
            'record_hash', 'created_timestamp', 'last_updated_timestamp',
            'created_by', 'last_updated_by',
        ]
        for key in scd2_order:
            cfg = scd2_config.get(key)
            if not cfg:
                continue

            col_name    = cfg.get('name', key.upper())
            if col_name.upper() in seen_cols:
                continue
            col_type    = cfg.get('type', 'VARCHAR(255)')
            nullable    = 'N' if not cfg.get('nullable', True) else 'Y'
            is_audit    = 'Y' if key in ('created_timestamp', 'last_updated_timestamp', 'created_by', 'last_updated_by') else 'N'
            datatype_id = _get_datatype_id(col_type)

            cursor.execute(f"""
                INSERT INTO {col_tbl}
                    (COLUMN_ID, TABLE_ID, COLUMN_NAME, COLUMN_POSITION,
                     DATATYPE_ID, COLUMN_TYPE, NULLABLE,
                     IS_TECHNICAL_KEY, IS_PK, IS_PI, IS_SCD_COLUMN, IS_AUDIT_COLUMN,
                     ERSTERFASSUNGSDATUM, AENDERUNGSDATUM)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'N', 'N', 'N', 'Y', ?,
                        CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
            """, [next_col_id, target_table_id, col_name, col_position,
                  datatype_id, col_type, nullable, is_audit])
            next_col_id  += 1
            col_position += 1
            inserted     += 1

        conn.commit()
        logger.info(f"META_COLUMN für neue Zieltabelle table_id={target_table_id}: {inserted} Spalten angelegt")
        return inserted

    def _ensure_target_table_exists(
        self, 
        cursor, 
        conn, 
        target_database: str, 
        target_table: str,
        source_table_id: int,
        pk_columns: List[str],
        core_name: str = '',
        fk_columns: List[str] = None,
        extra_columns: List[tuple] = None,
    ):
        """
        Prüft ob Ziel-Tabelle existiert, erstellt sie wenn nicht.

        Ziel-Tabelle = Source-Spalten + SCD2-Spalten (aus Config: cfg/parameter_rules.yml)
        DDL-Optionen (SET/MULTISET, PRIMARY INDEX) ebenfalls aus Config.

        Args:
            core_name: Kern-Name der Tabelle (z.B. 'aufenthalt') für SK-Spaltenname
            fk_columns: Optionale FK-Spalten ({MASTER_SK}_FK, BIGINT) – F6-Beladung
            extra_columns: Optionale Zusatzspalten [(name, definition)], z.B. für das
                Delta-Set; bei bestehender Tabelle per ALTER TABLE ergänzt
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
                self._add_missing_columns(cursor, conn, target_database, target_table, extra_columns)
                return
        except Exception as e:
            logger.warning(f"Fehler beim Prüfen der Ziel-Tabelle: {e}")
        
        # Source-Spalten aus META_COLUMN laden
        cursor.execute(f"""
            SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_LENGTH,
                   DECIMAL_TOTAL_DIGITS, DECIMAL_FRACTIONAL_DIGITS
            FROM {META_SCHEMA}.META_COLUMN
            WHERE TABLE_ID = ?
            ORDER BY COLUMN_POSITION
        """, [source_table_id])
        source_columns = cursor.fetchall()

        if not source_columns:
            # Fallback: Direkt aus dbc.ColumnsV laden
            cursor.execute(f"""
                SELECT t.TABLE_NAME, d.DATABASE_NAME
                FROM {META_SCHEMA}.META_TABLE t
                JOIN {META_SCHEMA}.META_DATABASE d ON t.DATABASE_ID = d.DATABASE_ID
                WHERE t.TABLE_ID = ?
            """, [source_table_id])
            src_info = cursor.fetchone()
            if src_info:
                cursor.execute(f"""
                    SELECT ColumnName, ColumnType, ColumnLength,
                           DecimalTotalDigits, DecimalFractionalDigits
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
        # Dedup: bereits ausgegebene Spaltennamen (verhindert Doppel-Spalte in der DDL,
        # z.B. wenn die DISC→REUS-Quell-View die SK-Spalte bereits enthält → CREATE TABLE schlägt fehl)
        seen_ddl_cols = set()

        # SK-Spalte (erste Spalte)
        sk_config = scd2_config.get('surrogate_key', {})
        sk_name, sk_def = build_column_def('surrogate_key', sk_config)
        columns_ddl.append(sk_def)
        seen_ddl_cols.add(sk_name.upper())
        
        # Source-Spalten
        for row in source_columns:
            col_name = row[0].strip().upper()
            # Dedup: Quellspalte überspringen, wenn Name bereits vergeben (z.B. SK aus der View)
            if col_name in seen_ddl_cols:
                continue
            col_type = row[1] if row[1] else None
            col_length = row[2] if len(row) > 2 else None
            dec_total = row[3] if len(row) > 3 else None
            dec_frac = row[4] if len(row) > 4 else None

            td_type = td_typecode_to_ddl(col_type, col_length, dec_total, dec_frac)
            columns_ddl.append(f"{col_name} {td_type}")
            seen_ddl_cols.add(col_name)
        
        # F6-Beladung: FK-Spalten ({MASTER_SK}_FK, BIGINT) nach den Source-Spalten
        for fk_col in (fk_columns or []):
            fk_name = (fk_col or '').strip().upper()
            if fk_name and fk_name not in seen_ddl_cols:
                columns_ddl.append(f"{fk_name} BIGINT")
                seen_ddl_cols.add(fk_name)
        
        # SCD2-Spalten am Ende (aus Config)
        scd2_order = ['record_hash', 'valid_from', 'valid_to', 'is_current', 
                      'created_timestamp', 'last_updated_timestamp', 
                      'created_by', 'last_updated_by']
        
        scd2_names = {}  # Speichern für PRIMARY INDEX
        for col_key in scd2_order:
            col_config = scd2_config.get(col_key, {})
            col_name, col_def = build_column_def(col_key, col_config)
            scd2_names[col_key] = col_name
            if col_name.upper() in seen_ddl_cols:
                continue
            columns_ddl.append(col_def)
            seen_ddl_cols.add(col_name.upper())

        # Zusatzspalten (z.B. Delta-Set: Ladelauf, Lösch-Kennzeichen)
        for col_name, col_def in (extra_columns or []):
            if col_name.upper() not in seen_ddl_cols:
                columns_ddl.append(col_def)
                seen_ddl_cols.add(col_name.upper())

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

        # Fix D: generierte DDL zurückgeben, damit der Create-Target-Step auch dann
        # angelegt werden kann, wenn die physische Tabelle (noch) nicht existiert.
        return ddl.strip()
    
    @staticmethod
    def _current_table_ddl(cursor, database: str, table: str):
        """Aktuelle CREATE-DDL einer Tabelle als (ddl,) oder None.

        SHOW TABLE statt dbc.TablesV.RequestText: RequestText ist die letzte
        DDL-Anweisung auf der Tabelle (nach ALTER TABLE also das ALTER).
        """
        try:
            cursor.execute(f"SHOW TABLE {database}.{table}")
            rows = cursor.fetchall()
        except Exception:
            return None
        ddl = "".join(r[0] for r in rows).replace("\r", "\n").strip().rstrip(";")
        return (ddl,) if ddl else None

    def _write_job_folder_artifacts(
        self,
        job_id: int,
        target_database: str,
        target_table: str,
        key_database: str,
        key_table_name: str,
        core_name: str,
        source_table_id: int,
        cursor,
    ):
        """
        F5-A: Schreibt DDL- und Cleanup-Dateien in etl/jobs/{job_id}/.

        Struktur:
            etl/jobs/{job_id}/
            ├── create_target_table.ddl
            ├── create_sk_table.ddl        (falls SK-Tabelle vorhanden)
            └── cleanup/
                ├── drop_target_table.sql
                └── drop_sk_table.sql
        """
        try:
            job_dir = Path(get_etl_jobs_path()) / str(job_id)
            cleanup_dir = job_dir / "cleanup"
            job_dir.mkdir(parents=True, exist_ok=True)
            cleanup_dir.mkdir(parents=True, exist_ok=True)

            # --- Zieltabelle CREATE DDL ---
            if target_table and target_database:
                fqn = f"{target_database}.{target_table}"
                try:
                    row = self._current_table_ddl(cursor, target_database, target_table)
                    if row and row[0]:
                        ddl_text = row[0].strip()
                    else:
                        ddl_text = f"-- DDL nicht verfügbar (Tabelle existierte bereits)\n-- CREATE TABLE {fqn} (...)"
                except Exception:
                    ddl_text = f"-- DDL nicht verfügbar\n-- CREATE TABLE {fqn} (...)"

                (job_dir / "create_target_table.ddl").write_text(
                    f"-- Zieltabelle: {fqn}\n-- Generiert beim Job-Erstellen (Job ID: {job_id})\n\n{ddl_text};\n",
                    encoding="utf-8"
                )
                (cleanup_dir / "drop_target_table.sql").write_text(
                    f"-- ACHTUNG: Löscht Zieltabelle inkl. aller Daten!\n-- Job ID: {job_id}\n\nDROP TABLE {fqn};\n",
                    encoding="utf-8"
                )

            # --- SK-Tabelle CREATE DDL ---
            if key_table_name and key_database:
                sk_fqn = f"{key_database}.{key_table_name}"
                try:
                    row = self._current_table_ddl(cursor, key_database, key_table_name)
                    if row and row[0]:
                        sk_ddl = row[0].strip()
                    else:
                        sk_ddl = f"-- DDL nicht verfügbar\n-- CREATE TABLE {sk_fqn} (...)"
                except Exception:
                    sk_ddl = f"-- DDL nicht verfügbar\n-- CREATE TABLE {sk_fqn} (...)"

                (job_dir / "create_sk_table.ddl").write_text(
                    f"-- SK-Tabelle: {sk_fqn}\n-- Generiert beim Job-Erstellen (Job ID: {job_id})\n\n{sk_ddl};\n",
                    encoding="utf-8"
                )
                (cleanup_dir / "drop_sk_table.sql").write_text(
                    f"-- ACHTUNG: Löscht SK-Tabelle inkl. aller Surrogate Keys!\n-- Job ID: {job_id}\n\nDROP TABLE {sk_fqn};\n",
                    encoding="utf-8"
                )

            logger.info(f"Job-Folder Artefakte geschrieben: {job_dir}")

        except Exception as e:
            logger.warning(f"Fehler beim Schreiben der Job-Folder Artefakte (nicht kritisch): {e}")

    def _insert_ddl_steps(
        self,
        cursor,
        conn,
        job_id: int,
        target_database: str,
        target_table: str,
        key_database: str,
        key_table_name: str,
        target_ddl: Optional[str] = None,
    ):
        """
        F5-B: Fügt zwei DDL_CREATE-Steps am Anfang des Jobs ein.

        - order -2: Create Target Table
        - order -1: Create SK Table

        Fix D: Für die Ziel-Tabelle wird bevorzugt die beim Job-Erstellen generierte DDL
        (target_ddl) verwendet, damit der Step auch dann existiert, wenn die physische
        Tabelle (noch) nicht angelegt wurde. Fallback: DDL aus dbc.TablesV.
        Orchestrator ignoriert Error 3803 (Tabelle bereits vorhanden) für DDL_CREATE-Steps.
        """
        try:
            # ETL_JOB_STEP_ID vergibt die Identity-Spalte. Kein eigener MAX+1-Wert:
            # bei GENERATED BY DEFAULT würde er übernommen und mit späteren
            # Identity-Werten kollidieren.
            steps_inserted = 0

            # --- Zieltabelle ---
            if target_database and target_table:
                fqn = f"{target_database}.{target_table}"
                # Fix D: generierte DDL bevorzugen
                if target_ddl:
                    ddl = target_ddl.strip()
                else:
                    try:
                        row = self._current_table_ddl(cursor, target_database, target_table)
                        ddl = row[0].strip() if row else None
                    except Exception:
                        ddl = None

                if ddl:
                    # Doppelte Semikolons vermeiden
                    ddl_sql = ddl if ddl.rstrip().endswith(';') else ddl + ';'
                    cursor.execute(f"""
                        INSERT INTO {META_SCHEMA}.META_ETL_JOB_STEP (
                            ETL_JOB_ID, STEP_NAME, STEP_ORDER,
                            STEP_CATEGORY, SQL_TEMPLATE_PATH, SQL_INLINE,
                            IS_CRITICAL, ROLLBACK_ON_ERROR, IS_ACTIVE,
                            RETRY_COUNT, TIMEOUT_SECONDS
                        ) VALUES (?, 'Create Target Table (DDL)', -2,
                                  'DDL_CREATE', NULL, ?, 'Y', 'N', 'Y', 1, 120)
                    """, [job_id, ddl_sql])
                    steps_inserted += 1
                    logger.info(f"DDL-Step 'Create Target Table' für Job {job_id} eingefügt ({fqn})")

            # --- SK-Tabelle ---
            if key_database and key_table_name:
                sk_fqn = f"{key_database}.{key_table_name}"
                try:
                    row = self._current_table_ddl(cursor, key_database, key_table_name)
                    sk_ddl = row[0].strip() if row else None
                except Exception:
                    sk_ddl = None

                if sk_ddl:
                    cursor.execute(f"""
                        INSERT INTO {META_SCHEMA}.META_ETL_JOB_STEP (
                            ETL_JOB_ID, STEP_NAME, STEP_ORDER,
                            STEP_CATEGORY, SQL_TEMPLATE_PATH, SQL_INLINE,
                            IS_CRITICAL, ROLLBACK_ON_ERROR, IS_ACTIVE,
                            RETRY_COUNT, TIMEOUT_SECONDS
                        ) VALUES (?, 'Create SK Table (DDL)', -1,
                                  'DDL_CREATE', NULL, ?, 'Y', 'N', 'Y', 1, 120)
                    """, [job_id, sk_ddl + ';'])
                    steps_inserted += 1
                    logger.info(f"DDL-Step 'Create SK Table' für Job {job_id} eingefügt ({sk_fqn})")

            if steps_inserted:
                conn.commit()

        except Exception as e:
            logger.warning(f"Fehler beim Einfügen der DDL-Steps für Job {job_id} (nicht kritisch): {e}")

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
            cursor.execute(f"""
                SELECT 
                    STEP_NAME, STEP_ORDER, STEP_CATEGORY,
                    SQL_TEMPLATE_PATH, SQL_INLINE,
                    DEFAULT_PARAMETERS
                FROM {META_SCHEMA}.META_ETL_JOB_STEP_TEMPLATE
                WHERE STEP_TEMPLATE_ID = ?
            """, [step_template_id])
            
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Step-Template {step_template_id} nicht gefunden")
            
            # Step-Order bestimmen
            if step_order is None:
                cursor.execute(f"""
                    SELECT COALESCE(MAX(STEP_ORDER), 0) + 10
                    FROM {META_SCHEMA}.META_ETL_JOB_STEP
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
            cursor.execute(f"""
                INSERT INTO {META_SCHEMA}.META_ETL_JOB_STEP (
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
            cursor.execute(f"""
                SELECT MAX(ETL_JOB_STEP_ID)
                FROM {META_SCHEMA}.META_ETL_JOB_STEP
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
            cursor.execute(f"""
                SELECT TEMPLATE_ID 
                FROM {META_SCHEMA}.META_ETL_JOB_TEMPLATE
                WHERE TEMPLATE_NAME = ?
            """, [template_name])
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            cursor.close()
            conn.close()
    
    def update_job_template(self, template_id: int, data: dict) -> bool:
        """
        Aktualisiert ein Job-Template (Name, Beschreibung, Kategorie, Tags).

        Returns: True wenn erfolgreich
        """
        allowed = {
            'template_name': 'TEMPLATE_NAME',
            'beschreibung': 'BESCHREIBUNG',
            'category': 'CATEGORY',
            'tags': 'TAGS',
        }
        set_parts = []
        values = []
        for key, col in allowed.items():
            if key in data:
                set_parts.append(f"{col} = ?")
                values.append(data[key])

        if not set_parts:
            return True  # Nichts zu tun

        values.append(template_id)
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"UPDATE {META_SCHEMA}.META_ETL_JOB_TEMPLATE SET {', '.join(set_parts)} WHERE TEMPLATE_ID = ?",
                values
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"update_job_template {template_id}: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def update_step_template(self, step_template_id: int, data: dict) -> bool:
        """
        Aktualisiert ein Step-Template (Name, Reihenfolge, Kategorie, SQL-Pfad,
        Parameter, is_active, is_critical, skip_on_empty, rollback_on_error, Beschreibung).

        Returns: True wenn erfolgreich
        """
        allowed = {
            'step_name': 'STEP_NAME',
            'step_order': 'STEP_ORDER',
            'step_category': 'STEP_CATEGORY',
            'sql_template_path': 'SQL_TEMPLATE_PATH',
            'sql_inline': 'SQL_INLINE',
            'beschreibung': 'BESCHREIBUNG',
            'is_active': 'IS_ACTIVE',
        }
        set_parts = []
        values = []
        for key, col in allowed.items():
            if key in data:
                val = data[key]
                if key == 'is_active':
                    val = 'Y' if val in (True, 'Y', 'true', 1) else 'N'
                set_parts.append(f"{col} = ?")
                values.append(val)

        # default_parameters separat behandeln (JSON-Serialisierung)
        if 'default_parameters' in data:
            dp = data['default_parameters']
            set_parts.append("DEFAULT_PARAMETERS = ?")
            values.append(json.dumps(dp) if dp is not None else None)

        if not set_parts:
            return True

        values.append(step_template_id)
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"UPDATE {META_SCHEMA}.META_ETL_JOB_STEP_TEMPLATE SET {', '.join(set_parts)} WHERE STEP_TEMPLATE_ID = ?",
                values
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"update_step_template {step_template_id}: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def _step_params_file(self, step_template_id: int) -> Optional[Path]:
        """Gibt den Pfad zur .params.json-Datei eines Step-Templates zurück (oder None)."""
        from app.config import PATHS
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
                SELECT s.SQL_TEMPLATE_PATH, t.TEMPLATE_CODE
                FROM {META_SCHEMA}.META_ETL_JOB_STEP_TEMPLATE s
                LEFT JOIN {META_SCHEMA}.META_ETL_JOB_TEMPLATE t ON t.TEMPLATE_ID = s.TEMPLATE_ID
                WHERE s.STEP_TEMPLATE_ID = ?
            """, [step_template_id])
            row = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
        if not row or not row[0]:
            return None
        sql_path = str(row[0])           # z.B. "delete/delete_target_table.sql"
        template_code = str(row[1]) if row[1] else ''
        # Wenn sql_path bereits template_code als Prefix enthält, nicht doppeln
        if template_code and not sql_path.startswith(template_code + '/'):
            full_path = f"{template_code}/{sql_path}"
        else:
            full_path = sql_path
        # .sql → .params.json
        params_path = Path(full_path).with_suffix('.params.json')
        return Path(PATHS['sql_templates']) / params_path

    def get_step_template_params(self, step_template_id: int) -> dict:
        """
        Lädt default_parameters eines Step-Templates.
        File-first: .params.json neben der .sql-Datei, Fallback DB.
        """
        params_file = self._step_params_file(step_template_id)
        if params_file and params_file.exists():
            try:
                return json.loads(params_file.read_text(encoding='utf-8'))
            except Exception:
                pass
        # DB-Fallback
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"SELECT DEFAULT_PARAMETERS FROM {META_SCHEMA}.META_ETL_JOB_STEP_TEMPLATE WHERE STEP_TEMPLATE_ID = ?",
                [step_template_id]
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except Exception:
                pass
        return {}

    def save_step_template_params(self, step_template_id: int, params: dict) -> bool:
        """
        Speichert default_parameters file-first (.params.json) + dual-write in DB.
        """
        params_file = self._step_params_file(step_template_id)
        # Datei schreiben
        if params_file:
            params_file.parent.mkdir(parents=True, exist_ok=True)
            params_file.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding='utf-8')
        # DB dual-write
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"UPDATE {META_SCHEMA}.META_ETL_JOB_STEP_TEMPLATE SET DEFAULT_PARAMETERS = ? WHERE STEP_TEMPLATE_ID = ?",
                [json.dumps(params, ensure_ascii=False), step_template_id]
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"save_step_template_params {step_template_id}: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    def delete_step_template(self, step_template_id: int) -> bool:
        """Löscht ein einzelnes Step-Template. Returns: True wenn erfolgreich."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
                DELETE FROM {META_SCHEMA}.META_ETL_JOB_STEP_TEMPLATE
                WHERE STEP_TEMPLATE_ID = ?
            """, [step_template_id])
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"delete_step_template {step_template_id}: {e}")
            conn.rollback()
            return False
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
            cursor.execute(f"""
                DELETE FROM {META_SCHEMA}.META_ETL_JOB_STEP_TEMPLATE
                WHERE TEMPLATE_ID = ?
            """, [template_id])
            
            # Dann Job-Template löschen
            cursor.execute(f"""
                DELETE FROM {META_SCHEMA}.META_ETL_JOB_TEMPLATE
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
            cursor.execute(f"""
                SELECT 
                    JOB_NAME, JOB_TYPE, SOURCE_LAYER_ID, TARGET_LAYER_ID,
                    PRIMARY_KEY_COLUMNS, HASH_COLUMNS,
                    VALID_FROM_COLUMN, VALID_TO_COLUMN, IS_CURRENT_COLUMN,
                    BESCHREIBUNG
                FROM {META_SCHEMA}.META_ETL_JOB
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
            cursor.execute(f"""
                SELECT TEMPLATE_ID, TEMPLATE_CODE
                FROM {META_SCHEMA}.META_ETL_JOB_TEMPLATE
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
            cursor.execute(f"""
                INSERT INTO {META_SCHEMA}.META_ETL_JOB_TEMPLATE (
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
            cursor.execute(f"""
                SELECT TEMPLATE_ID 
                FROM {META_SCHEMA}.META_ETL_JOB_TEMPLATE
                WHERE TEMPLATE_CODE = ?
            """, [final_template_code])
            tpl_row = cursor.fetchone()
            template_id = tpl_row[0] if tpl_row else 0
            
            if not template_id:
                raise ValueError("Template konnte nicht erstellt werden")
            
            # 5. Steps kopieren
            cursor.execute(f"""
                SELECT 
                    STEP_NAME, STEP_ORDER, STEP_CATEGORY,
                    SQL_TEMPLATE_PATH, SQL_INLINE, PARAMETERS,
                    IS_CRITICAL, ROLLBACK_ON_ERROR, BESCHREIBUNG
                FROM {META_SCHEMA}.META_ETL_JOB_STEP
                WHERE ETL_JOB_ID = ?
                ORDER BY STEP_ORDER
            """, [job_id])
            
            steps = cursor.fetchall()
            
            for step in steps:
                cursor.execute(f"""
                    INSERT INTO {META_SCHEMA}.META_ETL_JOB_STEP_TEMPLATE (
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

    # =========================================================================
    # Export / Import als ZIP
    # =========================================================================

    def export_template(self, template_id: int) -> bytes:
        """
        Exportiert Job-Template + Step-Templates + SQL-Dateien als ZIP.

        ZIP-Struktur:
            manifest.json          ← Metadaten (name, version, exported_at, ...)
            job_template.json      ← Row aus META_ETL_JOB_TEMPLATE
            step_templates.json    ← Rows aus META_ETL_JOB_STEP_TEMPLATE
            sql/
                scd_type2/close_old_versions.sql
                ...

        Namespace-Stripping: Falls sql_template_path mit template_code/ beginnt
        (importiertes Template), wird der Namespace-Prefix für den ZIP-Pfad entfernt,
        damit das ZIP portabel bleibt.

        Returns: ZIP-Inhalt als bytes
        """
        import io
        import zipfile
        from datetime import datetime
        from ..config import PATHS

        template = self.get_job_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} nicht gefunden")

        step_templates = self.get_step_templates(template_id=template_id)
        sql_base = PATHS["sql_templates"]
        namespace_prefix = template.template_code + "/"

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            # manifest.json
            manifest = {
                "name": template.template_name,
                "template_code": template.template_code,
                "version": "1.0",
                "exported_at": datetime.utcnow().isoformat(),
                "template_id": template_id,
                "step_count": len(step_templates)
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

            # job_template.json
            zf.writestr("job_template.json", json.dumps(template.dict(), indent=2, ensure_ascii=False))

            # step_templates.json
            zf.writestr("step_templates.json", json.dumps(
                [s.dict() for s in step_templates], indent=2, ensure_ascii=False
            ))

            # SQL-Dateien
            seen_zip_paths: set = set()
            for step in step_templates:
                if not step.sql_template_path:
                    continue
                # Namespace-Prefix für ZIP-Pfad entfernen (portables ZIP)
                rel_path = step.sql_template_path
                if rel_path.startswith(namespace_prefix):
                    rel_path = rel_path[len(namespace_prefix):]

                zip_entry = f"sql/{rel_path}"
                if zip_entry in seen_zip_paths:
                    continue
                seen_zip_paths.add(zip_entry)

                sql_file = sql_base / step.sql_template_path
                if sql_file.exists():
                    zf.writestr(zip_entry, sql_file.read_text(encoding='utf-8'))
                else:
                    logger.warning(f"SQL-Template nicht gefunden beim Export: {sql_file}")

        return buf.getvalue()

    def import_template(self, zip_bytes: bytes, overwrite: bool = False, template_code_override: str = None) -> dict:
        """
        Importiert Job-Template aus ZIP.

        Ablauf:
        1. ZIP lesen (manifest, job_template, step_templates, sql/)
        2. Namespace = template_code aus manifest (z.B. MASTER_DATA_SCD2)
        3. SQL-Dateien nach ddl/sql_templates/{NAMESPACE}/... schreiben
        4. DB: prüfen ob Template-Code bereits existiert
        5. Wenn existiert und overwrite=False → exists=True zurückgeben
        6. Wenn existiert und overwrite=True → altes Template löschen
        7. Neues Job-Template + Step-Templates in DB einfügen
           sql_template_path = {NAMESPACE}/{original_zip_rel_path}

        Returns: dict mit template_id, namespace, step_count, message
        """
        import io
        import zipfile
        from ..config import PATHS

        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, 'r') as zf:
            zip_names = set(zf.namelist())

            # Pflichtdateien prüfen
            for required in ("manifest.json", "job_template.json", "step_templates.json"):
                if required not in zip_names:
                    raise ValueError(f"Ungültiges Template-ZIP: '{required}' fehlt")

            manifest = json.loads(zf.read("manifest.json").decode('utf-8'))
            job_tpl_data = json.loads(zf.read("job_template.json").decode('utf-8'))
            step_tpls_data = json.loads(zf.read("step_templates.json").decode('utf-8'))

        # Namespace aus template_code (Großbuchstaben, nur A-Z0-9_)
        # Priorität: 1. Override vom User, 2. manifest.template_code, 3. manifest.name
        import re as _re
        raw_ns = template_code_override or manifest.get("template_code", manifest.get("name", "IMPORTED"))
        namespace = str(raw_ns).upper().replace(' ', '_')
        # Nur erlaubte Zeichen
        namespace = _re.sub(r'[^A-Z0-9_]', '_', namespace)

        sql_base = PATHS["sql_templates"]
        ns_dir = sql_base / namespace

        # SQL-Dateien schreiben
        with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
            for zip_entry in zf.namelist():
                if not zip_entry.startswith("sql/"):
                    continue
                # Relativer Pfad innerhalb sql/ (ohne führenden Slash)
                rel_path = zip_entry[4:]
                if not rel_path or rel_path.endswith('/'):
                    continue
                target_file = ns_dir / rel_path
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_bytes(zf.read(zip_entry))
                logger.info(f"Template-Import: SQL-Datei geschrieben → {target_file}")

        # DB: existierendes Template prüfen
        template_name = job_tpl_data.get("template_name", namespace)
        template_code = namespace

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
                SELECT TEMPLATE_ID
                FROM {META_SCHEMA}.META_ETL_JOB_TEMPLATE
                WHERE TEMPLATE_CODE = ?
            """, [template_code])
            existing_row = cursor.fetchone()

            if existing_row and not overwrite:
                return {
                    "template_id": existing_row[0],
                    "namespace": namespace,
                    "created": False,
                    "exists": True,
                    "message": f"Template '{template_code}' existiert bereits (ID: {existing_row[0]}). Mit overwrite=true überschreiben."
                }

            if existing_row and overwrite:
                cursor.close()
                conn.close()
                self.delete_template(existing_row[0])
                conn = self._get_connection()
                cursor = conn.cursor()

            # TEMPLATE_ID vergibt die Identity-Spalte (kein eigener MAX+1-Wert, siehe _insert_ddl_steps)
            cursor.execute(f"""
                INSERT INTO {META_SCHEMA}.META_ETL_JOB_TEMPLATE (
                    TEMPLATE_NAME, TEMPLATE_CODE, JOB_TYPE,
                    SOURCE_LAYER_ID, TARGET_LAYER_ID,
                    DEFAULT_PRIMARY_KEY_COLUMNS, DEFAULT_HASH_COLUMNS,
                    DEFAULT_VALID_FROM_COLUMN, DEFAULT_VALID_TO_COLUMN,
                    DEFAULT_IS_CURRENT_COLUMN, CATEGORY, BESCHREIBUNG
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                template_name,
                template_code,
                job_tpl_data.get("job_type", "CUSTOM"),
                job_tpl_data.get("source_layer_id"),
                job_tpl_data.get("target_layer_id"),
                job_tpl_data.get("default_primary_key_columns"),
                job_tpl_data.get("default_hash_columns"),
                job_tpl_data.get("default_valid_from_column"),
                job_tpl_data.get("default_valid_to_column"),
                job_tpl_data.get("default_is_current_column"),
                job_tpl_data.get("category"),
                job_tpl_data.get("beschreibung")
            ])
            cursor.execute(
                f"SELECT TEMPLATE_ID FROM {META_SCHEMA}.META_ETL_JOB_TEMPLATE WHERE TEMPLATE_CODE = ?",
                [template_code],
            )
            new_template_id = cursor.fetchone()[0]
            conn.commit()

            # Step-Templates einfügen
            orig_namespace_prefix = manifest.get("template_code", "") + "/"
            step_count = 0
            for step_data in step_tpls_data:
                orig_path = step_data.get("sql_template_path") or ""
                if orig_path:
                    # Ursprünglichen Namespace-Prefix entfernen, neuen Namespace setzen
                    if orig_path.startswith(orig_namespace_prefix):
                        orig_path = orig_path[len(orig_namespace_prefix):]
                    new_sql_path = f"{namespace}/{orig_path}"
                else:
                    new_sql_path = orig_path or None

                default_params = step_data.get("default_parameters")
                params_json = json.dumps(default_params, ensure_ascii=False) if default_params else None

                cursor.execute(f"""
                    INSERT INTO {META_SCHEMA}.META_ETL_JOB_STEP_TEMPLATE (
                        TEMPLATE_ID, STEP_NAME, STEP_CODE, STEP_ORDER,
                        STEP_CATEGORY, SQL_TEMPLATE_PATH, SQL_INLINE,
                        DEFAULT_PARAMETERS, REQUIRED_PARAMETERS, BESCHREIBUNG
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    new_template_id,
                    step_data.get("step_name", ""),
                    step_data.get("step_code"),
                    step_data.get("step_order", 10),
                    step_data.get("step_category", "SQL"),
                    new_sql_path,
                    step_data.get("sql_inline"),
                    params_json,
                    step_data.get("required_parameters"),
                    step_data.get("beschreibung")
                ])
                step_count += 1

            conn.commit()
            logger.info(f"Template '{template_code}' importiert: ID={new_template_id}, {step_count} Steps, Namespace={namespace}")

            return {
                "template_id": new_template_id,
                "namespace": namespace,
                "step_count": step_count,
                "created": True,
                "exists": False,
                "message": f"Template '{template_code}' erfolgreich importiert (ID={new_template_id}, {step_count} Steps)."
            }

        finally:
            cursor.close()
            conn.close()
