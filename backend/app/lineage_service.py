"""
Column Lineage Service - Core Business Logic
"""
import sqlglot
import requests
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path
from .models import LLMConnection, ColumnMapping
from .config import OUTPUT_DIR


class LineageService:
    """Service für Column Lineage Analyse"""
    
    def __init__(self):
        pass
    
    def parse_sql(self, sql: str, dialect: str = 'tsql') -> Dict[str, Any]:
        """Parsed SQL und extrahiert Column Lineage"""
        
        # Clean SQL: Remove GO statements (T-SQL batch separator)
        sql_clean = sql.replace('GO', '').replace('go', '').strip()
        
        try:
            parsed = sqlglot.parse_one(sql_clean, read=dialect)
        except Exception as e:
            raise ValueError(f"SQL Parse Error: {str(e)}")
        
        # Handle UNION statements - recursively get first SELECT
        original_type = type(parsed).__name__
        if isinstance(parsed, sqlglot.exp.Union):
            print(f"ℹ️  UNION Statement erkannt - extrahiere ersten SELECT-Teil")
            # Recursively go left until we find a Select
            while isinstance(parsed, sqlglot.exp.Union):
                parsed = parsed.left
        
        if not isinstance(parsed, sqlglot.exp.Select):
            raise ValueError(f"Nur SELECT Statements werden unterstützt (Statement-Typ: {original_type}, nach UNION-Auflösung: {type(parsed).__name__})")
        
        expressions = list(parsed.expressions)
        
        # Extrahiere Source Tables
        tables = []
        for table in parsed.find_all(sqlglot.exp.Table):
            tables.append({
                'path': f"{table.db}.{table.catalog}.{table.name}" if table.db else table.name,
                'alias': table.alias if hasattr(table, 'alias') and table.alias else None
            })
        
        # Sammle Column Mappings
        column_data = []
        for expr in expressions:
            target_col = expr.alias if expr.alias else str(expr)[:30]
            source_expr_str = str(expr.this) if hasattr(expr, 'this') else str(expr)
            
            # Transformation Type
            sql_upper = source_expr_str.upper()
            if 'CASE' in sql_upper and 'WHEN' in sql_upper:
                transform_type = 'CONDITIONAL_LOGIC'
                transform_icon = '🔀 CASE WHEN'
            elif 'CAST' in sql_upper or 'CONVERT' in sql_upper:
                transform_type = 'TYPE_CONVERSION'
                transform_icon = '🔄 Type Conversion'
            else:
                transform_type = 'DIRECT_MAPPING'
                transform_icon = '➡️ Direct Mapping'
            
            # Source Columns
            source_cols_d = []
            source_cols_const = []
            for col in expr.find_all(sqlglot.exp.Column):
                col_name = col.name
                table_alias = col.table if hasattr(col, 'table') and col.table else None
                if table_alias and 'constant' not in table_alias.lower():
                    source_cols_d.append(col_name)
                elif table_alias:
                    source_cols_const.append(col_name)
            
            column_data.append({
                'target_column': target_col,
                'source_expression': source_expr_str,
                'transform_type': transform_type,
                'transform_icon': transform_icon,
                'source_columns_d': list(set(source_cols_d)),
                'source_columns_const': list(set(source_cols_const)),
                'llm_description': None
            })
        
        return {
            'columns': column_data,
            'tables': tables,
            'column_count': len(expressions)
        }
    
    def enrich_with_llm(self, columns: List[Dict], connection: Dict[str, Any]) -> List[ColumnMapping]:
        """Reichert Columns mit LLM-Beschreibungen an"""
        
        enriched = []
        for col_data in columns:
            description = self._generate_llm_description(
                col_data['source_expression'],
                col_data['target_column'],
                col_data['source_columns_d'],
                col_data['source_columns_const'],
                connection
            )
            col_data['llm_description'] = description
            enriched.append(ColumnMapping(**col_data))
        
        return enriched
    
    def _generate_llm_description(self, sql_expr: str, target_col: str, 
                                   source_cols: List[str], constants: List[str],
                                   connection: Dict[str, Any]) -> Optional[str]:
        """Generiert LLM-Beschreibung für eine Spalte"""
        
        prompt = f"""Du bist ein Data Warehouse Analyst. Erkläre diese SQL-Transformation in 1-2 kurzen Sätzen auf Deutsch, fachlich für Business-User.

SQL-Ausdruck:
{sql_expr}

Ziel-Spalte: {target_col}
Quell-Spalten: {', '.join(source_cols) if source_cols else 'keine'}
Verwendete Konstanten: {', '.join(constants) if constants else 'keine'}

Fokussiere auf:
- Was wird geprüft oder transformiert?
- Welche Business-Regel wird angewendet?
- Warum ist das wichtig für die Datenqualität?

Antworte nur mit der Beschreibung, keine Überschriften oder Zusatztexte."""
        
        try:
            if connection.get('backend_type') == "ollama":
                response = requests.post(
                    f"{connection['url']}/api/generate",
                    json={
                        "model": connection['model'],
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "top_p": 0.9,
                            "num_predict": 150
                        }
                    },
                    timeout=connection.get('timeout', 300)
                )
                
                if response.status_code == 200:
                    result = response.json()
                    description = result.get('response', '').strip()
                    if 20 < len(description) < 500:
                        return description
            
            elif connection.get('backend_type') in ["llm-farm", "openai"]:
                headers = {}
                if connection.get('api_key'):
                    headers["Authorization"] = f"Bearer {connection['api_key']}"
                
                response = requests.post(
                    f"{connection['url']}/v1/chat/completions",
                    json={
                        "model": connection['model'],
                        "messages": [
                            {"role": "system", "content": "Du bist ein Data Warehouse Analyst."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 800
                    },
                    headers=headers,
                    timeout=connection.get('timeout', 300)
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result['choices'][0]['message']['content'].strip()
                    
                    # DeepSeek R1: Filtere <think> Tags
                    if '<think>' in content:
                        parts = content.split('</think>')
                        if len(parts) > 1:
                            description = parts[-1].strip()
                        else:
                            description = content
                    else:
                        description = content
                    
                    if 20 < len(description) < 1000:
                        return description
            
            return None
            
        except Exception as e:
            print(f"LLM Error: {e}")
            return None
    
    def generate_mermaid(self, columns: List[ColumnMapping]) -> str:
        """Generiert Mermaid Diagramm Code"""
        
        # Sammle alle Source Columns und Constants
        source_cols_full = set()
        const_cols_full = set()
        transform_mappings = {}
        
        for col in columns[:20]:  # Limit 20 für Übersichtlichkeit
            for src in col.source_columns_d:
                source_cols_full.add(src)
            for const in col.source_columns_const:
                const_cols_full.add(const)
            
            transform_mappings[col.target_column] = (
                [(('d', c)) for c in col.source_columns_d] + 
                [(('const', c)) for c in col.source_columns_const],
                col.transform_type.replace('_', ' '),
                col.source_expression[:100]
            )
        
        # Build Mermaid
        mermaid = "graph LR\n"
        mermaid += '    subgraph SOURCE["Source Tables"]\n'
        for col in sorted(source_cols_full):
            col_id = col.replace('_', '').replace('[', '').replace(']', '')
            mermaid += f"        src_{col_id}[{col}]\n"
        mermaid += "    end\n\n"
        
        if const_cols_full:
            mermaid += '    subgraph CONST["Constants"]\n'
            for col in sorted(const_cols_full):
                col_id = col.replace('_', '').replace('[', '').replace(']', '')
                mermaid += f"        const_{col_id}[{col}]\n"
            mermaid += "    end\n\n"
        
        mermaid += "    %% Transformation Nodes\n"
        for target_col, (sources, transform_type, _) in transform_mappings.items():
            tgt_id = target_col.replace('_', '').replace('[', '').replace(']', '')
            label = {
                'CONDITIONAL LOGIC': 'CASE WHEN',
                'TYPE CONVERSION': 'CAST',
                'DIRECT MAPPING': 'DIRECT'
            }.get(transform_type, 'TRANSFORM')
            mermaid += f'    xform_{tgt_id}[["{label}"]]\n'
        
        mermaid += '\n    subgraph TARGET["Target Columns"]\n'
        for col in columns[:20]:
            tgt_id = col.target_column.replace('_', '').replace('[', '').replace(']', '')
            mermaid += f"        tgt_{tgt_id}[{col.target_column}]\n"
        mermaid += "    end\n\n"
        
        # Connections
        for target_col, (sources, _, _) in transform_mappings.items():
            tgt_id = target_col.replace('_', '').replace('[', '').replace(']', '')
            for src_type, src_col in set(sources):
                src_id = src_col.replace('_', '').replace('[', '').replace(']', '')
                if src_type == 'd':
                    mermaid += f"    src_{src_id} --> xform_{tgt_id}\n"
                else:
                    mermaid += f"    const_{src_id} --> xform_{tgt_id}\n"
            mermaid += f"    xform_{tgt_id} --> tgt_{tgt_id}\n"
        
        # Click Events
        mermaid += "\n    %% Click Events\n"
        for i, col in enumerate(columns[:20], 1):
            tgt_id = col.target_column.replace('_', '').replace('[', '').replace(']', '')
            anchor = col.target_column.lower().replace('_', '-').replace('[', '').replace(']', '')
            mermaid += f'    click xform_{tgt_id} "#{i}-{anchor}"\n'
        
        # Styling
        mermaid += """
    %% Styling
    classDef sourceClass fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef targetClass fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef transformClass fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    classDef constClass fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
"""
        
        return mermaid
    
    def generate_html(self, columns: List[ColumnMapping], mermaid_code: str, 
                     connection_name: str = "N/A", sql: str = "") -> str:
        """Generiert HTML Report"""
        
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        html_file = OUTPUT_DIR / f"lineage_report_{timestamp}.html"
        
        html_content = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Column Lineage Report</title>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ startOnLoad: true, securityLevel: 'loose', theme: 'default' }});
    </script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{ background: white; border-radius: 8px; padding: 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #1976d2; border-bottom: 3px solid #1976d2; padding-bottom: 10px; }}
        h2 {{ color: #f57c00; margin-top: 30px; }}
        h3 {{ color: #7b1fa2; border-left: 4px solid #7b1fa2; padding-left: 10px; }}
        .info-box {{ background: #e3f2fd; border-left: 4px solid #1976d2; padding: 15px; margin: 20px 0; border-radius: 4px; }}
        .llm-badge {{ background: #4caf50; color: white; padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: bold; }}
        .mermaid-container {{ background: white; padding: 20px; border-radius: 8px; border: 1px solid #ddd; margin: 20px 0; overflow-x: auto; }}
        pre {{ background: #f5f5f5; padding: 15px; border-radius: 4px; overflow-x: auto; font-size: 12px; }}
        .detail-section {{ background: #fafafa; padding: 20px; margin: 15px 0; border-radius: 8px; border: 1px solid #e0e0e0; }}
        .transform-type {{ display: inline-block; padding: 5px 15px; background: #fff9c4; border-radius: 20px; font-weight: bold; color: #f57f17; }}
        .description-box {{ background: #e8f5e9; border-left: 4px solid #4caf50; padding: 12px; margin: 15px 0; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Column-Level Lineage Report <span class="llm-badge">🤖 AI-Enhanced</span></h1>
        
        <div class="info-box">
            <p><strong>💡 Automatisch generierter Lineage Report mit AI-Beschreibungen</strong></p>
            <p>Erstellt mit metadaita - Powered by FastAPI & sqlglot</p>
        </div>
        
        <h2>Übersicht</h2>
        <ul>
            <li><strong>Anzahl Spalten:</strong> {len(columns)}</li>
            <li><strong>LLM Backend:</strong> {connection_name}</li>
            <li><strong>Parser:</strong> sqlglot v{sqlglot.__version__}</li>
            <li><strong>Generiert:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
        </ul>
        
        <h2>Source SQL</h2>
        <pre><code>{sql[:1000]}{'...' if len(sql) > 1000 else ''}</code></pre>
        
        <h2>Column Lineage Diagramm</h2>
        <div class="mermaid-container">
            <div class="mermaid">
{mermaid_code}
            </div>
        </div>
        
        <h2>Transformation Details</h2>
"""
        
        for i, col in enumerate(columns[:20], 1):
            anchor = col.target_column.lower().replace('_', '-').replace('[', '').replace(']', '')
            html_content += f"""
        <div class="detail-section" id="{i}-{anchor}">
            <h3>{i}. {col.target_column}</h3>
            <p><span class="transform-type">{col.transform_icon}</span></p>
"""
            if col.llm_description:
                html_content += f"""
            <div class="description-box">
                <p style="margin:0;"><strong>📋 Fachliche Beschreibung (AI):</strong> {col.llm_description}</p>
            </div>
"""
            html_content += f"""
            <p><strong>Source Expression:</strong></p>
            <pre><code>{col.source_expression[:500].replace('<', '&lt;').replace('>', '&gt;')}</code></pre>
"""
            if col.source_columns_d:
                html_content += f"""            <p><strong>Source Columns:</strong> {', '.join(col.source_columns_d)}</p>\n"""
            if col.source_columns_const:
                html_content += f"""            <p><strong>Constants:</strong> {', '.join(col.source_columns_const)}</p>\n"""
            
            html_content += "        </div>\n"
        
        html_content += """    </div>
</body>
</html>
"""
        
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return str(html_file)
