"""
Welche META-Tabellen ein Paket transportiert und wie sie zugeordnet werden.

Konzept: daita-studio/docs/PAKET_DEPLOYMENT_KONZEPT.md, Abschnitte 5 und 6.
IDs werden 1:1 übernommen; der fachliche Schlüssel dient als Kontrolle
(gleiche ID mit anderem Schlüssel oder gleicher Schlüssel mit anderer ID
= Konflikt).
"""

# (Tabelle, ID-Spalten, fachlicher Schlüssel oder None) - Eltern vor Kindern
INHALT = [
    ("META_LAYER", ["layer_id"], ["layer_code"]),
    ("META_AREA_CATEGORY", ["area_category_id"], ["area_category_code"]),
    ("META_AREA", ["area_id"], ["area_code"]),
    ("META_BUSINESS_OBJECT", ["business_object_id"], ["business_object_code"]),
    ("META_DATABASE", ["database_id"], ["database_name"]),
    ("META_DATATYPE", ["datatype_id"], ["datatype_name"]),
    ("META_DATATYPE_MAPPING", ["mapping_id"], ["source_system", "source_datatype"]),
    ("META_SOURCE_SYSTEM", ["SOURCE_SYSTEM_ID"], None),
    ("META_TABLE", ["table_id"], ["database_id", "table_name"]),
    ("META_COLUMN", ["column_id"], ["table_id", "column_name"]),
    ("META_INDEX", ["index_id"], None),
    ("META_INDEX_COLUMN", ["index_column_id"], ["index_id", "column_position"]),
    ("META_FOREIGN_KEY", ["fk_id"], None),
    ("META_ETL_JOB", ["etl_job_id"], ["job_name"]),
    ("META_ETL_JOB_STEP", ["etl_job_step_id"], ["etl_job_id", "step_order", "step_name"]),
    ("META_ETL_JOB_PARAMETER", ["parameter_id"], ["etl_job_id", "parameter_name"]),
    ("META_ETL_DEPENDENCY", ["dependency_id"], ["parent_job_id", "child_job_id"]),
    ("META_ETL_COLUMN_MAPPING", ["mapping_id"], None),
    ("META_ETL_TEST", ["test_id"], ["test_name"]),
    ("META_DATA_QUALITY_RULE", ["rule_id"], ["rule_name"]),
    ("META_LINEAGE", ["lineage_id"], None),
    ("META_ETL_PARSED_COLUMN_LINEAGE", ["parsed_lineage_id"], None),
]

VORLAGEN = [
    ("META_ETL_JOB_TEMPLATE", ["TEMPLATE_ID"], ["TEMPLATE_CODE"]),
    ("META_ETL_JOB_STEP_TEMPLATE", ["STEP_TEMPLATE_ID"], ["TEMPLATE_ID", "STEP_CODE"]),
]

# Zielbetrieb: nie im Paket, nie angefasst
BETRIEB = [
    "META_ETL_JOB_RUN", "META_ETL_JOB_STEP_RUN", "META_ETL_RUN", "META_ETL_TEST_RESULT",
    "META_ETL_NOTIFICATION", "META_USER", "META_ETL_LOAD_STATE", "META_ETL_SCHEDULE",
    "META_DEPLOY",
    "META_VIEW_LINEAGE",  # Cache, schreibt daita-studio selbst (lineage_flow_service)
]

# Spalten, die auf dem Ziel zur Laufzeit gepflegt werden: nicht exportiert, nie überschrieben
LAUFZEIT_SPALTEN = {
    "META_TABLE": ["row_count", "permanent_space", "temp_space"],
    "META_DATABASE": ["permanent_space", "spool_space", "temp_space"],
}

# Spalte mit der Job-ID je Tabelle: Filter für Teilpakete nach Jobs
JOB_SPALTE = {
    "META_ETL_JOB": "etl_job_id",
    "META_ETL_JOB_STEP": "etl_job_id",
    "META_ETL_JOB_PARAMETER": "etl_job_id",
    "META_ETL_DEPENDENCY": "child_job_id",
    "META_ETL_COLUMN_MAPPING": "etl_job_id",
    "META_ETL_TEST": "etl_job_id",
    "META_ETL_PARSED_COLUMN_LINEAGE": "etl_job_id",
}

# Spalte mit der Template-ID je Tabelle: Filter für Teilpakete nach Vorlagen
TEMPLATE_SPALTE = {
    "META_ETL_JOB_TEMPLATE": "TEMPLATE_ID",
    "META_ETL_JOB_STEP_TEMPLATE": "TEMPLATE_ID",
}

# Protokoll der Einspiel-Läufe (Konzept Abschnitt 5); legt der Einspieler an, wenn sie fehlt
META_DEPLOY_DDL = """CREATE MULTISET TABLE {schema}.META_DEPLOY (
    LAUF_ID VARCHAR(40) CHARACTER SET UNICODE NOT NULL,
    TEIL VARCHAR(30) CHARACTER SET UNICODE NOT NULL,
    PAKET VARCHAR(255) CHARACTER SET UNICODE,
    KUNDE VARCHAR(60) CHARACTER SET UNICODE,
    VERSION VARCHAR(255) CHARACTER SET UNICODE,
    INHALT_HASH VARCHAR(64) CHARACTER SET UNICODE,
    UMFANG VARCHAR(4000) CHARACTER SET UNICODE,
    ERGEBNIS VARCHAR(20) CHARACTER SET UNICODE,
    ZUSAMMENFASSUNG VARCHAR(4000) CHARACTER SET UNICODE,
    PROTOKOLL VARCHAR(500) CHARACTER SET UNICODE,
    BENUTZER VARCHAR(128) CHARACTER SET UNICODE,
    ZEITPUNKT TIMESTAMP(0) NOT NULL)
PRIMARY INDEX (LAUF_ID)"""


def tabellen(teil):
    return {"jobs": INHALT, "vorlagen": VORLAGEN}[teil]
