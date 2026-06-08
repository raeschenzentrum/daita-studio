"""
type_utils.py – Teradata DBC Typcode → DDL Mapping
====================================================

Zentrale Funktion für die Konvertierung von Teradata DBC COLUMN_TYPE Codes
(wie sie in dbc.ColumnsV / META_COLUMN stehen) zu DDL-Typbezeichnungen.

Typecodes: https://docs.teradata.com/r/Teradata-VantageCloud-Lake/Database-Reference/
           Data-Type-Codes-in-DBC-Tables

WICHTIG: Hier ändern, nicht in einzelnen Services!
"""


def td_typecode_to_ddl(
    col_type: str,
    col_length=None,
    decimal_total: int = None,
    decimal_frac: int = None,
) -> str:
    """
    Konvertiert einen Teradata DBC COLUMN_TYPE Code zu einem DDL-Typ-String.

    Args:
        col_type:       Wert aus dbc.ColumnsV.ColumnType / META_COLUMN.COLUMN_TYPE
                        (z.B. 'I8', 'CV', 'DA', 'TS', 'D ', 'I ', ...)
        col_length:     COLUMN_LENGTH aus META_COLUMN (für VARCHAR, CHAR, BYTE, ...)
        decimal_total:  DECIMAL_TOTAL_DIGITS (für DECIMAL/NUMBER)
        decimal_frac:   DECIMAL_FRACTIONAL_DIGITS (für DECIMAL/NUMBER)

    Returns:
        DDL-Typ-String (z.B. 'BIGINT', 'VARCHAR(200)', 'DECIMAL(18,4)')
    """
    if not col_type:
        return 'VARCHAR(255)'

    t = col_type.strip().upper()

    # -------------------------------------------------------------------------
    # Integer-Typen – REIHENFOLGE wichtig: spezifisch vor generisch
    # -------------------------------------------------------------------------
    if t == 'I8':
        return 'BIGINT'
    if t == 'I4':
        return 'INTEGER'
    if t == 'I2':
        return 'SMALLINT'
    if t in ('I1', 'BO'):
        return 'BYTEINT'
    if t in ('I', 'I '):        # generischer 4-Byte Integer
        return 'INTEGER'

    # -------------------------------------------------------------------------
    # Float / Number
    # -------------------------------------------------------------------------
    if t in ('F', 'F '):
        return 'FLOAT'

    # -------------------------------------------------------------------------
    # Decimal / Numeric – mit Präzision aus META_COLUMN wenn vorhanden
    # -------------------------------------------------------------------------
    if t in ('D', 'D ', 'N', 'N '):
        p = int(decimal_total) if decimal_total else 18
        s = int(decimal_frac) if decimal_frac else 2
        return f'DECIMAL({p},{s})'

    # -------------------------------------------------------------------------
    # Datum / Uhrzeit – DA vor D, damit DATE nicht als DECIMAL landet!
    # -------------------------------------------------------------------------
    if t == 'DA':
        return 'DATE'
    if t in ('AT',):
        return 'TIME'
    if t in ('AZ',):
        return 'TIME WITH TIME ZONE'
    if t in ('TS', 'SZ'):
        return 'TIMESTAMP(6)'
    if t == 'TZ':
        return 'TIMESTAMP WITH TIME ZONE'

    # Period Types
    if t == 'PS':
        return 'PERIOD(DATE)'
    if t == 'PT':
        return 'PERIOD(TIME)'
    if t in ('PM', 'PZ'):
        return 'PERIOD(TIMESTAMP)'

    # -------------------------------------------------------------------------
    # Character
    # -------------------------------------------------------------------------
    if t == 'CV':
        length = int(col_length) if col_length else 255
        return f'VARCHAR({length}) CHARACTER SET UNICODE'
    if t == 'CF':
        length = int(col_length) if col_length else 1
        return f'CHAR({length}) CHARACTER SET UNICODE'
    if t == 'CO':
        return 'CLOB'

    # -------------------------------------------------------------------------
    # Binary
    # -------------------------------------------------------------------------
    if t == 'BV':
        length = int(col_length) if col_length else 64000
        return f'VARBYTE({length})'
    if t == 'BF':
        length = int(col_length) if col_length else 64000
        return f'BYTE({length})'

    # -------------------------------------------------------------------------
    # Interval
    # -------------------------------------------------------------------------
    _intervals = {
        'YR': 'INTERVAL YEAR',
        'YM': 'INTERVAL YEAR TO MONTH',
        'MO': 'INTERVAL MONTH',
        'DY': 'INTERVAL DAY',
        'DH': 'INTERVAL DAY TO HOUR',
        'DM': 'INTERVAL DAY TO MINUTE',
        'DS': 'INTERVAL DAY TO SECOND',
        'HR': 'INTERVAL HOUR',
        'HM': 'INTERVAL HOUR TO MINUTE',
        'HS': 'INTERVAL HOUR TO SECOND',
        'MI': 'INTERVAL MINUTE',
        'MS': 'INTERVAL MINUTE TO SECOND',
        'SC': 'INTERVAL SECOND',
    }
    if t in _intervals:
        return _intervals[t]

    # -------------------------------------------------------------------------
    # JSON / XML / UDT
    # -------------------------------------------------------------------------
    if t == 'JN':
        return 'JSON'
    if t == 'XM':
        return 'XML'

    # -------------------------------------------------------------------------
    # DDL-Passthrough: META_COLUMN speichert bereits fertige DDL-Typ-Strings
    # (z.B. "BIGINT", "VARCHAR(200)") statt Teradata-Codes ("I8", "CV").
    # Falls der Typ hier ankommt und kein 2-Zeichen-Code war, direkt verwenden.
    # -------------------------------------------------------------------------
    _ddl_passthrough = {
        'BIGINT', 'INTEGER', 'INT', 'SMALLINT', 'BYTEINT',
        'FLOAT', 'REAL', 'DOUBLE PRECISION', 'DATE', 'CLOB', 'BLOB',
    }
    if t in _ddl_passthrough:
        return t

    _ddl_prefixes = (
        'VARCHAR(', 'CHAR(', 'NVARCHAR(', 'VARBYTE(', 'BYTE(',
        'DECIMAL(', 'NUMERIC(', 'NUMBER(', 'FLOAT(',
        'TIMESTAMP(', 'TIME(', 'PERIOD(', 'INTERVAL ',
    )
    if any(t.startswith(p) for p in _ddl_prefixes):
        return col_type.strip()

    # -------------------------------------------------------------------------
    # Fallback
    # -------------------------------------------------------------------------
    return 'VARCHAR(255)'
