"""
SQL Template Engine für Metadata-Driven ETL Framework
=======================================================

Rendert SQL-Templates mit Parameter-Substitution.
Verwendet einfache String-Substitution mit ${PARAMETER} Syntax.

Autor: DWH MVP Team
Datum: 2026-01-19
Version: 1.0
"""

import re
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class SQLTemplateEngine:
    """
    Template-Engine für SQL-Dateien mit Parameter-Substitution.
    
    Unterstützt:
    - Einfache Parameter: ${SOURCE_TABLE}
    - Spezielle Generierung: ${HASH_EXPRESSION}, ${SELECT_COLUMNS}
    - Validierung: Prüft auf ungesetzte Parameter
    
    Example:
        >>> engine = SQLTemplateEngine(base_dir='/path/to/templates')
        >>> sql = engine.render(
        ...     'scd_type2/identify_new_records.sql',
        ...     {'STAGING_TABLE': 'temp_staging', 'BUSINESS_KEY': 'PERSON_ID'}
        ... )
    """
    
    def __init__(self, base_dir: str):
        """
        Initialisiert die Template-Engine.
        
        Args:
            base_dir: Basis-Verzeichnis für SQL-Templates
        """
        self.base_dir = Path(base_dir)
        if not self.base_dir.exists():
            raise ValueError(f"Template directory does not exist: {base_dir}")
        
        logger.info(f"SQLTemplateEngine initialized with base_dir: {base_dir}")
    
    def render(self, template_path: str, parameters: Dict[str, Any]) -> str:
        """
        Rendert ein SQL-Template mit Parameter-Substitution.
        
        Args:
            template_path: Relativer Pfad zum Template (z.B. 'scd_type2/identify_new_records.sql')
            parameters: Dictionary mit Parametern für Substitution
        
        Returns:
            Gerenderter SQL-String
        
        Raises:
            FileNotFoundError: Template-Datei existiert nicht
            ValueError: Ungesetzte Parameter gefunden
        """
        # Template laden
        full_path = self.base_dir / template_path
        if not full_path.exists():
            raise FileNotFoundError(f"Template not found: {full_path}")
        
        logger.debug(f"Loading template: {template_path}")
        with open(full_path, 'r', encoding='utf-8') as f:
            template = f.read()
        
        # Spezielle Parameter generieren
        params = self._prepare_parameters(parameters)
        
        # Parameter ersetzen
        rendered_sql = self._substitute_parameters(template, params)
        
        # Validierung: Keine unersetzten Platzhalter
        self._validate_rendered_sql(rendered_sql)
        
        logger.debug(f"Template rendered successfully: {template_path}")
        return rendered_sql
    
    def _prepare_parameters(self, parameters: Dict[str, Any]) -> Dict[str, str]:
        """
        Bereitet Parameter vor und generiert spezielle Expressions.
        
        Args:
            parameters: Input-Parameter (können JSON-Objekte enthalten)
        
        Returns:
            Dictionary mit allen String-Parametern
        """
        params = {}
        
        # Normalize keys to lowercase for lookup
        params_lower = {k.lower(): v for k, v in parameters.items()}
        
        # Table alias für Spalten-Referenzen (z.B. "stg" für stg.COLUMN_NAME)
        table_alias = params_lower.get('table_alias', None)
        
        # Einfache Parameter kopieren
        for key, value in parameters.items():
            if isinstance(value, (str, int, float)):
                params[key] = str(value)
            elif isinstance(value, list):
                # Listen speichern für spezielle Verarbeitung
                params[f"_list_{key}"] = value
        
        # Spezielle Expressions generieren (case-insensitive lookup)
        # Nur wenn der Wert eine Liste ist – bei fertigen Strings den Wert direkt übernehmen
        if 'hash_columns' in params_lower:
            hash_cols = params_lower['hash_columns']
            if isinstance(hash_cols, list):
                params['HASH_EXPRESSION'] = self._build_hash_expression(
                    hash_cols,
                    table_alias=table_alias
                )

        if 'select_columns' in params_lower:
            select_cols = params_lower['select_columns']
            if isinstance(select_cols, list):
                params['SELECT_COLUMNS'] = self._build_select_columns(
                    select_cols,
                    table_alias=table_alias
                )
        elif 'insert_columns' in params_lower:
            insert_cols = params_lower['insert_columns']
            if isinstance(insert_cols, list):
                params['SELECT_COLUMNS'] = self._build_select_columns(
                    insert_cols,
                    table_alias=table_alias
                )

        if 'insert_columns' in params_lower:
            insert_cols = params_lower['insert_columns']
            if isinstance(insert_cols, list):
                params['INSERT_COLUMNS'] = self._build_insert_columns(insert_cols)

        # FK_DEFINITIONS → FK_SK_COLUMNS, FK_INSERT_COLUMNS, FK_JOINS
        # Format: [{"sk_column": "GESCHAEFT_SK", "key_table": "KEY_TAAS_GESCHAEFT",
        #           "key_database": "MDP01_DISCOVERABLE_LAYER",
        #           "natural_key_expr": "CAST(src.GESCHAEFT_ID AS VARCHAR(255))",
        #           "domain": "UZMS01"}]
        fk_defs = params_lower.get('fk_definitions')
        if fk_defs and isinstance(fk_defs, list) and len(fk_defs) > 0:
            fk_sk_cols, fk_insert_cols, fk_joins = self._build_fk_expressions(fk_defs)
            params['FK_SK_COLUMNS']     = fk_sk_cols
            params['FK_INSERT_COLUMNS'] = fk_insert_cols
            params['FK_JOINS']          = fk_joins
        else:
            # Kein FK: leere Strings → Template verhält sich wie ohne FK
            params['FK_SK_COLUMNS']     = ''
            params['FK_INSERT_COLUMNS'] = ''
            params['FK_JOINS']          = ''

        return params
    
    def _substitute_parameters(self, template: str, parameters: Dict[str, str]) -> str:
        """
        Ersetzt alle ${PARAMETER} Platzhalter im Template.
        Lässt ${...} in Kommentarzeilen (die mit -- beginnen) unverändert.
        
        Args:
            template: Template-String
            parameters: Parameter-Dictionary
        
        Returns:
            Template mit ersetzten Parametern
        """
        lines = template.split('\n')
        result_lines = []
        
        for line in lines:
            stripped = line.lstrip()
            
            # Kommentarzeilen: Keine Ersetzung (Dokumentation bleibt intakt)
            if stripped.startswith('--'):
                result_lines.append(line)
            else:
                # Normale Zeilen: Parameter ersetzen
                result_line = line
                for key, value in parameters.items():
                    if not key.startswith('_list_'):  # Listen überspringen
                        placeholder = f"${{{key}}}"
                        result_line = result_line.replace(placeholder, value)
                result_lines.append(result_line)
        
        return '\n'.join(result_lines)
    
    def _validate_rendered_sql(self, sql: str) -> None:
        """
        Validiert gerendertes SQL auf ungesetzte Parameter.
        Ignoriert ${...} in Kommentarzeilen (nur Dokumentation).
        
        Args:
            sql: Gerenderter SQL-String
        
        Raises:
            ValueError: Ungesetzte Parameter gefunden
        """
        # Nur nicht-Kommentar Zeilen prüfen
        lines = sql.split('\n')
        non_comment_lines = [line for line in lines if not line.lstrip().startswith('--')]
        non_comment_sql = '\n'.join(non_comment_lines)
        
        # Suche nach ${...} Patterns
        remaining = re.findall(r'\$\{([^}]+)\}', non_comment_sql)
        
        if remaining:
            raise ValueError(
                f"Unresolved template parameters found: {', '.join(set(remaining))}\n"
                f"Please provide values for these parameters in the parameters JSON."
            )
    
    def _build_hash_expression(self, columns: List[str], table_alias: str = None) -> str:
        """
        Baut HASHROW-Expression aus Spalten-Liste.
        
        Args:
            columns: Liste von Spalten-Namen oder Expressions
            table_alias: Optionaler Tabellen-Alias (z.B. "stg")
        
        Returns:
            HASHROW(...) Expression
        
        Example:
            >>> engine._build_hash_expression(['PERSON_ID', 'NAME'], table_alias='stg')
            'HASHROW(\\n        CAST(stg.PERSON_ID AS VARCHAR(100)),\\n        CAST(stg.NAME AS VARCHAR(100))\\n    )'
        """
        prefix = f"{table_alias}." if table_alias else ""
        
        cast_expressions = []
        for col in columns:
            # Prüfen ob bereits CAST oder Expression enthalten ist
            col_upper = col.upper().strip()
            if col_upper.startswith('CAST(') or col_upper.startswith('COALESCE('):
                # Bereits eine Expression - Alias vor Spaltennamen einfügen
                # z.B. "CAST(ZEMIS_NR AS VARCHAR(20))" → "CAST(stg.ZEMIS_NR AS VARCHAR(20))"
                if table_alias:
                    # Füge Alias nach öffnender Klammer ein
                    col = self._add_alias_to_expression(col, table_alias)
                cast_expressions.append(col)
            else:
                # Einfacher Spaltenname - CAST hinzufügen
                cast_expressions.append(f"CAST({prefix}{col} AS VARCHAR(100))")
        
        return "HASHROW(\n        " + ",\n        ".join(cast_expressions) + "\n    )"
    
    def _add_alias_to_expression(self, expression: str, alias: str) -> str:
        """
        Fügt Tabellen-Alias zu Spaltennamen in einer Expression hinzu.
        
        Args:
            expression: SQL Expression wie "CAST(ZEMIS_NR AS VARCHAR(20))"
            alias: Tabellen-Alias wie "stg"
        
        Returns:
            Expression mit Alias: "CAST(stg.ZEMIS_NR AS VARCHAR(20))"
        """
        import re
        
        # Pattern für Spaltennamen nach ( oder , - aber nicht nach .
        # Spaltenname = Großbuchstaben/Unterstriche, kein Punkt davor
        def replace_column(match):
            before = match.group(1)  # ( oder , oder Whitespace
            col_name = match.group(2)  # Spaltenname
            # Prüfen ob es ein SQL-Keyword ist
            keywords = {'AS', 'VARCHAR', 'INTEGER', 'DECIMAL', 'TIMESTAMP', 'DATE', 'CHAR', 'COALESCE', 'CAST', 'NULL'}
            if col_name.upper() in keywords:
                return match.group(0)  # Unverändert lassen
            return f"{before}{alias}.{col_name}"
        
        # Ersetze Spaltennamen nach ( oder , aber nicht nach .
        result = re.sub(r'([\(,]\s*)([A-Z_][A-Z0-9_]*)(?!\.)', replace_column, expression, flags=re.IGNORECASE)
        return result
    
    def _build_select_columns(self, columns: List, table_alias: str = None) -> str:
        """
        Baut SELECT-Liste mit Type Conversions.
        
        Args:
            columns: Liste von Spalten - entweder Strings oder Dicts
                     Strings: ['COL1', 'COL2']
                     Dicts: [{'name': 'COL1', 'expression': 'COALESCE(COL1, 0)'}]
            table_alias: Optionaler Tabellen-Alias (z.B. "stg")
        
        Returns:
            SELECT-Liste als String
        
        Example:
            >>> columns = [
            ...     {'name': 'PERSON_ID'},
            ...     {'name': 'NAME', 'expression': 'COALESCE(NAME, "UNKNOWN")'}
            ... ]
            >>> engine._build_select_columns(columns, table_alias='stg')
            'stg.PERSON_ID,\\n        COALESCE(stg.NAME, "UNKNOWN") AS NAME'
        """
        prefix = f"{table_alias}." if table_alias else ""
        select_items = []
        
        for col in columns:
            if isinstance(col, str):
                # Einfacher String → mit Alias verwenden
                select_items.append(f"{prefix}{col}")
            elif isinstance(col, dict):
                # Dict mit 'name' und optionalem 'expression'
                name = col['name']
                expression = col.get('expression')
                
                if expression:
                    # Alias zu Expression hinzufügen
                    if table_alias:
                        expression = self._add_alias_to_expression(expression, table_alias)
                    select_items.append(f"{expression} AS {name}")
                else:
                    select_items.append(f"{prefix}{name}")
            else:
                raise ValueError(f"Invalid column format: {col}")
        
        return ",\n        ".join(select_items)
    
    def _build_fk_expressions(self, fk_definitions: List[dict]):
        """
        Generiert FK-SK SELECT-Ausdrücke, INSERT-Spalten und LEFT JOINs aus FK_DEFINITIONS.

        Args:
            fk_definitions: Liste von FK-Definitionen:
                [
                  {
                    "sk_column":        "GESCHAEFT_SK",
                    "key_table":        "KEY_TAAS_GESCHAEFT",
                    "key_database":     "MDP01_DISCOVERABLE_LAYER",
                    "natural_key_expr": "CAST(src.GESCHAEFT_ID AS VARCHAR(255))",
                    "domain":           "UZMS01"
                  }
                ]

        Returns:
            Tuple (fk_sk_columns_str, fk_insert_columns_str, fk_joins_str)
        """
        sk_cols    = []
        insert_cols = []
        joins      = []

        for i, fk in enumerate(fk_definitions, start=1):
            alias    = f"fk{i}"
            sk_col   = fk['sk_column']
            key_db   = fk['key_database']
            key_tbl  = fk['key_table']
            nk_expr  = fk['natural_key_expr']

            # F6: Master-Modus – FK referenziert die SK einer Master-/Dimensionstabelle
            #     (Join über deren Business Key). Kein KEY-Tabellen-Schema/Domain nötig.
            if fk.get('master_mode'):
                parent_sk = fk['parent_sk_column']
                parent_bk = fk['parent_bk_column']
                sk_cols.append(f"    COALESCE({alias}.{parent_sk}, -1) AS {sk_col},")
                insert_cols.append(f"    {sk_col},")
                joins.append(
                    f"LEFT JOIN {key_db}.{key_tbl} {alias}\n"
                    f"    ON CAST({alias}.{parent_bk} AS VARCHAR(255)) = {nk_expr}"
                )
            else:
                # KEY-Tabellen-Modus (NATURAL_KEY_VALUE / NATURAL_KEY_DOMAIN / SURROGATE_KEY)
                domain   = fk['domain']
                sk_cols.append(f"    COALESCE({alias}.SURROGATE_KEY, -1) AS {sk_col},")
                insert_cols.append(f"    {sk_col},")
                joins.append(
                    f"LEFT JOIN {key_db}.{key_tbl} {alias}\n"
                    f"    ON {nk_expr} = {alias}.NATURAL_KEY_VALUE\n"
                    f"   AND {alias}.NATURAL_KEY_DOMAIN = '{domain}'"
                )

        fk_sk_str     = ("\n".join(sk_cols) + "\n") if sk_cols else ""
        fk_insert_str = ("\n".join(insert_cols) + "\n") if insert_cols else ""
        fk_joins_str  = "\n".join(joins) if joins else ""

        return fk_sk_str, fk_insert_str, fk_joins_str

    def _build_insert_columns(self, columns: List[str]) -> str:
        """
        Baut Spalten-Liste für INSERT Statement.
        
        Args:
            columns: Liste von Spalten-Namen
        
        Returns:
            Komma-separierte Spalten-Liste
        
        Example:
            >>> engine._build_insert_columns(['PERSON_ID', 'NAME', 'STATUS'])
            'PERSON_ID,\\n    NAME,\\n    STATUS'
        """
        return ",\n    ".join(columns)
    
    def list_templates(self, category: Optional[str] = None) -> List[str]:
        """
        Listet verfügbare Templates auf.
        
        Args:
            category: Optional: Filter nach Kategorie (z.B. 'scd_type2')
        
        Returns:
            Liste von Template-Pfaden (relativ zu base_dir)
        """
        if category:
            search_dir = self.base_dir / category
        else:
            search_dir = self.base_dir
        
        templates = []
        for sql_file in search_dir.rglob('*.sql'):
            rel_path = sql_file.relative_to(self.base_dir)
            templates.append(str(rel_path))
        
        return sorted(templates)


# =============================================================================
# Utility Functions
# =============================================================================

def load_parameters_from_json(json_string: str) -> Dict[str, Any]:
    """
    Lädt Parameter aus JSON-String (aus META_ETL_JOB_STEP.parameters).
    """
    return json.loads(json_string)


def resolve_step_parameters(
    job_id: int,
    step_id: int,
    db_params: Optional[str],
    etl_jobs_path: "Path",
) -> Dict[str, Any]:
    """
    F4-A: Löst Step-Parameter auf.
    Priorität: JSON-Datei (etl/jobs/{job_id}/{step_id}.json) → DB-Fallback.

    Args:
        job_id:        etl_job_id
        step_id:       etl_job_step_id
        db_params:     JSON-String aus META_ETL_JOB_STEP.parameters (Fallback)
        etl_jobs_path: PATHS["etl_jobs"] als Path-Objekt

    Returns:
        Parameter-Dictionary (leer wenn nichts gefunden)
    """
    json_file = Path(etl_jobs_path) / str(job_id) / f"{step_id}.json"
    if json_file.exists():
        try:
            return json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            pass  # Fallback auf DB
    if db_params:
        try:
            return json.loads(db_params)
        except Exception:
            pass
    return {}


def write_step_parameters(
    job_id: int,
    step_id: int,
    parameters: Dict[str, Any],
    etl_jobs_path: "Path",
) -> None:
    """
    F4-B: Schreibt Step-Parameter in JSON-Datei.
    Erstellt den Job-Ordner falls nicht vorhanden.

    Args:
        job_id:        etl_job_id
        step_id:       etl_job_step_id
        parameters:    Parameter-Dictionary
        etl_jobs_path: PATHS["etl_jobs"] als Path-Objekt
    """
    job_dir = Path(etl_jobs_path) / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    json_file = job_dir / f"{step_id}.json"
    json_file.write_text(
        json.dumps(parameters, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def validate_template_parameters(
    template_content: str,
    parameters: Dict[str, Any]
) -> List[str]:
    """
    Validiert ob alle Template-Parameter vorhanden sind.
    
    Args:
        template_content: Template-Inhalt
        parameters: Verfügbare Parameter
    
    Returns:
        Liste von fehlenden Parametern (leer wenn alle vorhanden)
    """
    # Finde alle ${...} Patterns
    required_params = set(re.findall(r'\$\{([^}]+)\}', template_content))
    
    # Prüfe welche fehlen
    missing = []
    for param in required_params:
        if param not in parameters:
            missing.append(param)
    
    return missing


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == '__main__':
    # Logging konfigurieren
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Template-Engine initialisieren
    engine = SQLTemplateEngine(
        base_dir='/mnt/user/devel/daita-lakehouse/dwh/database/sql_templates'
    )
    
    # Verfügbare Templates auflisten
    print("Available SCD Type 2 Templates:")
    for template in engine.list_templates('scd_type2'):
        print(f"  - {template}")
    
    # Beispiel: Template rendern
    parameters = {
        'STAGING_TABLE': 'temp_taaa_person_staging',
        'TARGET_DATABASE': '<aus META_LAYER>',
        'TARGET_TABLE': 'TAAA_PERSON_HISTORY',
        'BUSINESS_KEY': 'PERSON_ID'
    }
    
    sql = engine.render('scd_type2/identify_new_records.sql', parameters)
    print("\nRendered SQL:")
    print(sql)
