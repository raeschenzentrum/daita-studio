# SQL Templates für Metadata-Driven ETL

## Übersicht

Dieses Verzeichnis enthält wiederverwendbare SQL-Templates für das Metadata-Driven ETL Framework. Templates verwenden **Parameter-Substitution** mit `${PARAMETER_NAME}` Syntax.

## Verzeichnisstruktur

```
sql_templates/
├── staging/          # Staging-Tabellen und Type Conversion
├── scd_type2/        # SCD Type 2 Historisierung
├── append_only/      # Transaktionsdaten (Append-Only)
└── common/           # Gemeinsame Templates (Statistics, Cleanup)
```

## Parameter-Substitution

Templates verwenden folgendes Format für Parameter:

```sql
SELECT * 
FROM ${SOURCE_DATABASE}.${SOURCE_TABLE}
WHERE ${BUSINESS_KEY} IS NOT NULL;
```

Parameter werden aus der `META_ETL_JOB_STEP.parameters` Spalte (JSON Format) geladen:

```json
{
  "SOURCE_DATABASE": "MDP01_RAW_LAYER",
  "SOURCE_TABLE": "TAAA_PERSON",
  "BUSINESS_KEY": "PERSON_ID"
}
```

## Template-Kategorien

### 1. STAGING Templates
- **create_staging_table.sql**: Erstellt VOLATILE Staging-Tabelle mit Type Conversion
- **load_staging_with_hash.sql**: Lädt Daten mit HASHROW-Berechnung

### 2. SCD TYPE 2 Templates
- **identify_new_records.sql**: Identifiziert neue Records (LEFT JOIN)
- **identify_changed_records.sql**: Identifiziert geänderte Records (HASH-Vergleich)
- **close_old_versions.sql**: Schließt alte Versionen (UPDATE IS_CURRENT='N')
- **insert_new_versions.sql**: Fügt neue Versionen ein (INSERT)

### 3. APPEND ONLY Templates
- **insert_new_transactions.sql**: Fügt neue Transaktionsdaten ein (kein SCD)

### 4. COMMON Templates
- **calculate_statistics.sql**: Sammelt Execution-Metriken
- **cleanup_temp_tables.sql**: Löscht VOLATILE Tables

## Verwendung im Orchestrator

```python
# Template laden und Parameter ersetzen
template_engine = SQLTemplateEngine(base_dir='/path/to/sql_templates')
rendered_sql = template_engine.render(
    template_path='scd_type2/identify_new_records.sql',
    parameters={
        'STAGING_TABLE': 'temp_taaa_person_staging',
        'TARGET_DATABASE': 'MDP01_DISCOVERABLE_LAYER',
        'TARGET_TABLE': 'TAAA_PERSON_HISTORY',
        'BUSINESS_KEY': 'PERSON_ID'
    }
)
```

## Best Practices

1. **Eindeutige Parameter**: Verwende UPPER_CASE für Parameter-Namen
2. **Validierung**: Prüfe auf ungesetzte Parameter (${...})
3. **Kommentare**: Dokumentiere erwartete Parameter im Template-Header
4. **Fehlerbehandlung**: Templates sollen idempotent sein (wiederholbar)

## Siehe auch

- Konzept: `/dwh/docs/METADATA_DRIVEN_ETL_CONCEPT.md`
- DDL: `/dwh/database/ddl/MDP01_META/META_ETL_JOB_STEP.ddl`
- Orchestrator: `/dwh/tools/etl/orchestrator.py`
