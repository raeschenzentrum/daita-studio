"""
Keyed History Service
=====================

Erzeugt Jobs für Template-Sets mit eigener Historie in der Zielschicht
(z.B. DISC_TO_REUS_KEYED_HISTORY):

- Quelle ist eine View: Sie kapselt die Business-Logik und liefert je Zeile
  eine Version mit Versionsspalten (cfg/parameter_rules.yml → keyed_history).
- Ein Job kann mehrere Rollen haben (z.B. MAIN und TEXT), jede mit eigener
  Quell-View und Zieltabelle; alle Rollen teilen sich eine KEY-Tabelle.
- KEY-Tabelle, SK-Spalte und Natural-Key-Spalte sind frei wählbar.
- Verweise (FK) im KEY-Modus mit frei wählbarem Namen der Zielspalte; fehlende
  Keys legt der Step "Late Arriving Keys" an.
- Feste Zeilen mit SK -1 aus Parametern.

Step-Templates des Sets tragen in DEFAULT_PARAMETERS den Key "ROLE" (MAIN,
TEXT, … oder ALL für Job-weite Steps); die übrigen Keys legen fest, welche
Parameter der Step bekommt.

Kundenneutral: Tabellen-, Spalten- und Datenbanknamen kommen aus der
Job-Spezifikation bzw. aus META, nie aus dem Code.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .template_service import TemplateService
from .template_engine import write_step_parameters
from ..config import META_SCHEMA, get_etl_jobs_path, PATHS

logger = logging.getLogger(__name__)

LAYER_NAMES = {1: 'raw', 2: 'discoverable', 3: 'reusable', 4: 'consumable'}
TEXT_TYPES = ('CHAR', 'VARCHAR', 'CLOB')


def _q(value) -> str:
    """SQL-Literal."""
    if value is None:
        return 'NULL'
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


class KeyedHistoryService(TemplateService):
    """Job-Erzeugung für Template-Sets mit eigener Historie und Rollen."""

    def __init__(self):
        super().__init__()
        self.cfg = self.param_rules.get('keyed_history', {}) or {}
        self.src = self.cfg.get('source_columns', {})
        self.tgt = {k: v['name'] for k, v in (self.cfg.get('target_columns', {}) or {}).items()}
        self.tgt_types = {k: v['type'] for k, v in (self.cfg.get('target_columns', {}) or {}).items()}
        self.vals = self.cfg.get('values', {})

    # ------------------------------------------------------------------ META

    def _source_info(self, cursor, table_id: int) -> dict:
        cursor.execute(f"""
            SELECT TRIM(t.TABLE_NAME), TRIM(d.DATABASE_NAME), t.LAYER_ID
            FROM {META_SCHEMA}.META_TABLE t
            JOIN {META_SCHEMA}.META_DATABASE d ON t.DATABASE_ID = d.DATABASE_ID
            WHERE t.TABLE_ID = ?""", [table_id])
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Quelle TABLE_ID {table_id} nicht in META_TABLE")
        cursor.execute(f"""
            SELECT TRIM(COLUMN_NAME), TRIM(COLUMN_TYPE), TRIM(CHARSET)
            FROM {META_SCHEMA}.META_COLUMN WHERE TABLE_ID = ? ORDER BY COLUMN_POSITION""", [table_id])
        cols = [(r[0].upper(), r[1], r[2]) for r in cursor.fetchall()]
        if not cols:
            raise ValueError(f"Quelle {row[1]}.{row[0]} hat keine Spalten in META_COLUMN")
        return {'table': row[0], 'database': row[1], 'layer_id': row[2], 'columns': cols}

    def _column_ddl_type(self, col_type: str, charset: Optional[str]) -> str:
        t = (col_type or '').strip()
        if t.upper().startswith(TEXT_TYPES) and 'CHARACTER SET' not in t.upper():
            t += f" CHARACTER SET {(charset or 'UNICODE').upper()}"
        return t

    # ------------------------------------------------------------- DDL

    def _key_table_ddl(self, db: str, table: str) -> str:
        return (f"CREATE SET TABLE {db}.{table}\n(\n"
                "    SURROGATE_KEY      BIGINT NOT NULL,\n"
                "    NATURAL_KEY_VALUE  VARCHAR(255) CHARACTER SET UNICODE NOT NULL,\n"
                "    NATURAL_KEY_DOMAIN VARCHAR(50) CHARACTER SET UNICODE NOT NULL,\n"
                "    NATURAL_KEY_HASH   BYTE(20),\n"
                "    IS_MASKED          CHAR(1) CHARACTER SET UNICODE DEFAULT 'N',\n"
                "    MASKED_VALUE       VARCHAR(255) CHARACTER SET UNICODE,\n"
                "    CREATED_TIMESTAMP  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),\n"
                "    CREATED_BY         VARCHAR(100) CHARACTER SET UNICODE DEFAULT 'ETL_KEY_GEN',\n"
                "    PRIMARY KEY (SURROGATE_KEY)\n)\n"
                f"UNIQUE INDEX (NATURAL_KEY_DOMAIN, NATURAL_KEY_VALUE)")

    def _target_ddl(self, db: str, table: str, sk: str, r: dict) -> str:
        lines = [f"    {sk} BIGINT NOT NULL"]
        for name, typ in r['target_columns']:
            lines.append(f"    {name} {typ}")
        for key in ('valid_from', 'valid_to', 'is_current', 'deleted_in_source', 'load_id',
                    'update_load_id', 'record_hash', 'created_ts', 'updated_ts'):
            lines.append(f"    {self.tgt[key]} {self.tgt_types[key]}")
        return (f"CREATE MULTISET TABLE {db}.{table}, FALLBACK\n(\n" + ",\n".join(lines) +
                f"\n)\nPRIMARY INDEX ({sk})")

    @staticmethod
    def _table_exists(cursor, db: str, table: str) -> bool:
        cursor.execute("SELECT 1 FROM dbc.TablesV WHERE DatabaseName = ? AND TableName = ?", [db, table])
        return cursor.fetchone() is not None

    # ------------------------------------------------------------- Rollen

    def _role(self, cursor, spec: dict, name: str, rs: dict, key_db: str, domain: str) -> dict:
        """Rolle aus Spezifikation + META: Spalten, Typen, Ziel-DDL-Spalten, FKs."""
        src = self._source_info(cursor, rs['source_table_id'])
        tech = {c.upper() for c in self.src.values()}
        types = {c: (t, cs) for c, t, cs in src['columns']}
        business = [c for c, _, _ in src['columns'] if c not in tech]
        nk = spec['natural_key_column'].upper()
        bk = [c.upper() for c in rs['business_key']]
        if not bk or bk[0] != nk:
            raise ValueError(f"Rolle {name}: Business Key muss mit {nk} beginnen")
        missing = [c for c in bk if c not in business]
        if missing:
            raise ValueError(f"Rolle {name}: Business-Key-Spalten fehlen in der Quelle: {missing}")
        fks = []
        for f in rs.get('fk', []) or []:
            sc = f['source_column'].upper()
            if sc not in business:
                raise ValueError(f"Rolle {name}: FK-Spalte {sc} fehlt in der Quelle")
            fks.append({'source_column': sc, 'target_column': f['target_column'].upper(),
                        'key_table': f['key_table'], 'key_database': f.get('key_database') or key_db,
                        'domain': f.get('domain') or domain})
        fk_src = {f['source_column']: f for f in fks}
        insert_cols = [c.upper() for c in (rs.get('insert_columns') or [c for c in business if c not in fk_src])]
        hash_cols = [c.upper() for c in (rs.get('hash_columns') or [c for c in business if c not in bk])]
        target_cols = []
        for c in business:
            if c in fk_src:
                target_cols.append((fk_src[c]['target_column'], 'BIGINT'))
            elif c in insert_cols:
                target_cols.append((c, self._column_ddl_type(*types[c])))
        return {'name': name, 'source': src, 'business': business, 'bk': bk, 'rest': bk[1:],
                'fks': fks, 'insert_columns': insert_cols, 'hash_columns': hash_cols,
                'target': rs['target_table'], 'target_columns': target_cols,
                'types': {n: t for n, t in target_cols}, 'unknown_rows': rs.get('unknown_rows', [{}])}

    def _role_params(self, spec: dict, r: dict, job_id: int, tgt_db: str, key_db: str, domain: str,
                     watermark: str, cap: str) -> Dict[str, object]:
        sk = spec['sk_column'].upper()
        nk = spec['natural_key_column'].upper()
        rest = r['rest']
        pre = self.cfg.get('staging_prefix', 'temp_')
        base = f"{pre}{r['target'].lower()}"
        stg, keyed, versions = f"{base}_stg", f"{base}_keyed", f"{base}_versions"
        s = self.src
        hl = int(self.cfg.get('hash_cast_length', 1000))
        hash_parts = [f"CAST(src.{c} AS VARCHAR({hl}))" for c in r['hash_columns']] or ["CAST(NULL AS VARCHAR(1))"]

        def keys(alias, sk_expr=None):
            return ", ".join([sk_expr or f"{alias}.{sk}"] + [f"{alias}.{c}" for c in rest])

        def join(a, b):
            return " AND ".join([f"{a}.{sk} = {b}.{sk}"] + [f"{a}.{c} = {b}.{c}" for c in rest])

        # Late Arriving Keys: je KEY-Tabelle ein INSERT
        late = ''
        if r['fks']:
            part = (Path(PATHS['sql_templates']) / spec['_template_code'] / 'keys' / 'late_arriving_key.part'
                    if 'sql_templates' in PATHS else None)
            part_sql = part.read_text(encoding='utf-8') if part and part.exists() else None
            if part_sql is None:
                raise ValueError("keys/late_arriving_key.part im Template-Set nicht gefunden")
            groups: Dict[tuple, List[str]] = {}
            for f in r['fks']:
                groups.setdefault((f['key_database'], f['key_table'], f['domain']), []).append(f['source_column'])
            stmts = []
            for (kdb, ktab, kdom), cols in groups.items():
                nks = "\n        UNION ALL\n        ".join(
                    f"SELECT CAST(stg.{c} AS VARCHAR(255)) AS natural_key FROM {stg} stg WHERE stg.{c} IS NOT NULL"
                    for c in cols)
                sql = part_sql
                for k, v in {'FK_KEY_DATABASE': kdb, 'FK_KEY_TABLE': ktab, 'FK_DOMAIN': kdom,
                             'FK_NATURAL_KEYS': nks, 'ETL_JOB_ID': str(job_id)}.items():
                    sql = sql.replace('${' + k + '}', v)
                stmts.append(sql.strip())
            late = ";\n\n".join(stmts) + ";"

        # Zeilen -1
        rows = r['unknown_rows'] or [{}]
        extra = []
        for row in rows:
            for c in row:
                if c.upper() not in extra:
                    extra.append(c.upper())
        ucols = [sk] + extra + [self.tgt[k] for k in ('valid_from', 'valid_to', 'is_current',
                                                      'deleted_in_source', 'created_ts')]
        selects = []
        for row in rows:
            rowu = {k.upper(): v for k, v in row.items()}
            vals = [f"CAST(-1 AS BIGINT) AS {sk}"]
            for c in extra:
                typ = r['types'].get(c, 'VARCHAR(255) CHARACTER SET UNICODE')
                vals.append(f"CAST({_q(rowu.get(c))} AS {typ}) AS {c}")
            vals += [f"TIMESTAMP '{self.cfg.get('initial_valid_from', '1000-01-01 00:00:00')}' AS {self.tgt['valid_from']}",
                     f"TIMESTAMP '{self.cfg.get('open_valid_to', '9999-12-31 23:59:59.999999')}' AS {self.tgt['valid_to']}",
                     f"'{self.vals.get('is_current', 'Y')}' AS {self.tgt['is_current']}",
                     f"'{self.vals.get('not_deleted', 'N')}' AS {self.tgt['deleted_in_source']}",
                     f"CURRENT_TIMESTAMP(6) AS {self.tgt['created_ts']}"]
            # Teradata verlangt in UNION-Zweigen eine Tabellenreferenz
            selects.append("SELECT " + ", ".join(vals) + " FROM (SELECT 1 AS D) one_row")
        umatch = " AND ".join([f"t.{sk} = u.{sk}"] + [f"t.{c} = u.{c}" for c in extra if c in rest])

        fk_defs = [{'sk_column': f['target_column'], 'key_table': f['key_table'],
                    'key_database': f['key_database'], 'domain': f['domain'],
                    'natural_key_expr': f"CAST(st.{f['source_column']} AS VARCHAR(255))"} for f in r['fks']]

        return {
            'ROLE': r['name'],
            'SOURCE_DATABASE': r['source']['database'], 'SOURCE_TABLE': r['source']['table'],
            'TARGET_DATABASE': tgt_db, 'TARGET_TABLE': r['target'],
            'KEY_DATABASE': key_db, 'KEY_TABLE': spec['key_table'], 'DOMAIN': domain,
            'SK_COLUMN': sk, 'NATURAL_KEY_COL': nk,
            'NATURAL_KEY_EXPRESSION_STG': f"CAST(stg.{nk} AS VARCHAR(255))",
            'BUSINESS_KEY': ", ".join(r['bk']),
            'STAGING_TABLE': stg, 'KEYED_TABLE': keyed, 'VERSIONS_TABLE': versions,
            'STG_SELECT': ", ".join(f"src.{c}" for c in r['business']),
            'HASH_EXPRESSION': "HASHROW(" + ", ".join(hash_parts) + ")",
            'STG_HASH': 'STG_RECORD_HASH',
            'SRC_VALID_FROM': s['valid_from'], 'SRC_VALID_TO': s['valid_to'],
            'SRC_IS_CURRENT': s['is_current'], 'SRC_DELETED': s['deleted_in_source'],
            'SRC_LOAD_ID': s['load_id'], 'SRC_UPDATE_LOAD_ID': s['update_load_id'],
            'TGT_VALID_FROM_COL': self.tgt['valid_from'], 'TGT_VALID_TO_COL': self.tgt['valid_to'],
            'TGT_IS_CURRENT_COL': self.tgt['is_current'], 'TGT_DELETED_COL': self.tgt['deleted_in_source'],
            'TGT_LOAD_ID_COL': self.tgt['load_id'], 'TGT_UPDATE_LOAD_ID_COL': self.tgt['update_load_id'],
            'TGT_HASH_COL': self.tgt['record_hash'], 'TGT_CREATED_TS_COL': self.tgt['created_ts'],
            'TGT_UPDATED_TS_COL': self.tgt['updated_ts'],
            'DELETED_VAL': self.vals.get('deleted', 'Y'), 'IS_CURRENT_OPEN': self.vals.get('is_current', 'Y'),
            'IS_CURRENT_CLOSED': self.vals.get('is_closed', 'N'),
            'LOAD_WATERMARK': watermark, 'LOAD_CAP': cap,
            'PART_KEY_STG': keys('stg', 'k.SURROGATE_KEY'),
            'PART_KEY_R': keys('r'), 'JOIN_KEY_S_P': join('p', 's'), 'JOIN_KEY_S_L': join('l', 's'),
            'TGT_KEY_COLS_T': keys('t'), 'PART_KEY_T': keys('t'),
            'KEY_COLS_V': keys('v'), 'PART_KEY_V': keys('v'),
            'JOIN_KEY_T_E': join('t', 'e'), 'JOIN_KEY_ST_EN': join('en', 'st'),
            'INSERT_COLUMNS': ", ".join(r['insert_columns']),
            'INSERT_SELECT': ", ".join(f"st.{c}" for c in r['insert_columns']),
            'fk_definitions': fk_defs,
            'LATE_ARRIVING_INSERTS': late,
            'UNKNOWN_COLUMNS': ", ".join(ucols),
            'UNKNOWN_COLUMNS_U': ", ".join(f"u.{c}" for c in ucols),
            'UNKNOWN_ROWS': "\n    UNION ALL\n    ".join(selects),
            'UNKNOWN_MATCH': umatch,
        }

    # ------------------------------------------------------------- Job

    def create_keyed_history_job(self, spec: dict) -> dict:
        """
        Legt einen Job an. spec:
          template_id, job_name, key_table, sk_column, natural_key_column,
          [domain], [upstream_job_ids], roles: {ROLLE: {source_table_id,
          target_table, business_key, [insert_columns], [hash_columns],
          [fk: [{source_column, target_column, key_table, [key_database]}]],
          [unknown_rows: [{spalte: wert}]]}}
        Rückgabe: {job_id, targets: {ROLLE: table}, steps}
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            template = self.get_job_template(spec['template_id'])
            if not template:
                raise ValueError(f"Template {spec['template_id']} nicht gefunden")
            spec = dict(spec, _template_code=template.template_code)
            steps = self.get_step_templates(template_id=spec['template_id'])
            if not spec.get('roles') or 'MAIN' not in spec['roles']:
                raise ValueError("Rolle MAIN fehlt")
            cursor.execute(f"SELECT ETL_JOB_ID FROM {META_SCHEMA}.META_ETL_JOB WHERE JOB_NAME = ?", [spec['job_name']])
            if cursor.fetchone():
                raise ValueError(f"Job {spec['job_name']} existiert bereits")
            domain = spec.get('domain') or next((st.default_parameters.get('DOMAIN') for st in steps
                                                if st.default_parameters and st.default_parameters.get('DOMAIN')), '')
            main_src = self._source_info(cursor, spec['roles']['MAIN']['source_table_id'])
            tgt_layer = (main_src['layer_id'] or template.source_layer_id) + 1
            layers = self._layers_config(cursor, LAYER_NAMES)
            tgt_db = layers.get(LAYER_NAMES.get(tgt_layer, ''), {}).get('database')
            if not tgt_db:
                raise ValueError(f"Keine Datenbank für Layer {tgt_layer}")
            key_db = spec.get('key_database') or tgt_db
            roles = {n: self._role(cursor, spec, n, rs, key_db, domain) for n, rs in spec['roles'].items()}

            # Job-ID und Parameter zuerst; geschrieben wird erst, wenn alle Steps vollständig sind
            cursor.execute(f"SELECT COALESCE(MAX(ETL_JOB_ID), 0) + 1 FROM {META_SCHEMA}.META_ETL_JOB")
            job_id = cursor.fetchone()[0]
            main = roles['MAIN']
            ls = (self.param_rules.get('raw_delta', {}) or {}).get('load_state_table', 'META_ETL_LOAD_STATE')
            watermark = (f"(SELECT COALESCE(MAX(LAST_LOAD_ID), 0) FROM {META_SCHEMA}.{ls} "
                         f"WHERE ETL_JOB_ID = {job_id})")
            up = [int(j) for j in spec.get('upstream_job_ids') or []]
            cap = (f"(SELECT CASE WHEN COUNT(*) = {len(up)} THEN MIN(LAST_LOAD_ID) ELSE 0 END "
                   f"FROM {META_SCHEMA}.{ls} WHERE ETL_JOB_ID IN ({', '.join(map(str, up))}))"
                   if up else '9223372036854775807')
            params = {n: self._role_params(spec, r, job_id, tgt_db, key_db, domain, watermark, cap)
                      for n, r in roles.items()}
            src_s = self.src
            events = "\n    UNION ALL\n    ".join(
                f"SELECT CASE WHEN s.{src_s['update_load_id']} IS NOT NULL "
                f"AND s.{src_s['update_load_id']} > s.{src_s['load_id']} "
                f"AND s.{src_s['update_load_id']} <= {cap} THEN s.{src_s['update_load_id']} "
                f"ELSE s.{src_s['load_id']} END AS EVT FROM {p['STAGING_TABLE']} s"
                for p in params.values())
            job_params = {'ROLE': 'ALL', 'META_DATABASE': str(META_SCHEMA), 'LOAD_STATE_TABLE': ls,
                          'ETL_JOB_ID': str(job_id), 'SOURCE_TABLE_ID': str(spec['roles']['MAIN']['source_table_id']),
                          'DELTA_EVENTS': events}

            step_rows = []
            for st in steps:
                dp = st.default_parameters or {}
                role = dp.get('ROLE', 'ALL')
                if role == 'ALL':
                    src_params = job_params
                elif role in params:
                    src_params = params[role]
                else:
                    continue
                if 'LATE_ARRIVING_INSERTS' in dp and not src_params.get('LATE_ARRIVING_INSERTS'):
                    continue
                fehlend = [k for k in dp if k not in src_params and k not in ('ROLE', 'DOMAIN', 'fk_definitions')]
                if fehlend:
                    raise ValueError(f"Step '{st.step_name}': Parameter ohne Wert: {fehlend}")
                step_params = {k: src_params[k] for k in dp if k in src_params}
                if 'fk_definitions' in dp:
                    step_params['fk_definitions'] = src_params.get('fk_definitions', [])
                for k, v in dp.items():
                    step_params.setdefault(k, v)
                step_rows.append((st, step_params))

            ddls = [('Create Key Table (DDL)', key_db, spec['key_table'], self._key_table_ddl(key_db, spec['key_table']))]
            # KEY-Tabellen der Verweisziele: late arriving keys brauchen sie, auch wenn
            # der Job der Zieldomäne noch nicht angelegt oder gelaufen ist
            fk_keys = []
            for r in roles.values():
                for f in r['fks']:
                    k = (f['key_database'], f['key_table'])
                    if k != (key_db, spec['key_table']) and k not in fk_keys:
                        fk_keys.append(k)
            for kdb, ktab in fk_keys:
                ddls.append((f"Create Key Table {ktab} (DDL)", kdb, ktab, self._key_table_ddl(kdb, ktab)))
            for n, r in roles.items():
                ddls.append((f"Create Target Table {n} (DDL)", tgt_db, r['target'],
                             self._target_ddl(tgt_db, r['target'], spec['sk_column'].upper(), r)))

            # Tabellen anlegen (KEY ohne Zeile -1; Ziele mit technischen Spalten)
            for _, db, tab, ddl in ddls:
                if not self._table_exists(cursor, db, tab):
                    cursor.execute(ddl)
                    conn.commit()
                    logger.info(f"{db}.{tab} angelegt")

            # Ziele in META registrieren (Layer der Zielschicht)
            from . import import_service
            target_ids = {}
            for n, r in roles.items():
                cursor.execute(f"""SELECT t.TABLE_ID FROM {META_SCHEMA}.META_TABLE t
                    JOIN {META_SCHEMA}.META_DATABASE d ON d.DATABASE_ID = t.DATABASE_ID
                    WHERE d.DATABASE_NAME = ? AND t.TABLE_NAME = ?""", [tgt_db, r['target']])
                row = cursor.fetchone()
                if not row:
                    erg = import_service.import_table(tgt_db, r['target'], tgt_layer)
                    if erg.get('error'):
                        raise ValueError(f"{tgt_db}.{r['target']}: {erg['error']}")
                    row = (erg['table_id'],)
                target_ids[n] = row[0]

            # Job
            cursor.execute(f"""
                INSERT INTO {META_SCHEMA}.META_ETL_JOB (
                    ETL_JOB_ID, JOB_NAME, JOB_TYPE, SOURCE_TABLE_ID, TARGET_TABLE_ID,
                    SOURCE_LAYER_ID, TARGET_LAYER_ID, PRIMARY_KEY_COLUMNS, HASH_COLUMNS,
                    VALID_FROM_COLUMN, VALID_TO_COLUMN, IS_CURRENT_COLUMN,
                    IS_ACTIVE, RETRY_COUNT, TIMEOUT_SECONDS
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Y', 3, 3600)""",
                [job_id, spec['job_name'], template.job_type, spec['roles']['MAIN']['source_table_id'], target_ids['MAIN'],
                 main['source']['layer_id'], tgt_layer, ", ".join(main['bk']), ", ".join(main['hash_columns']),
                 self.tgt['valid_from'], self.tgt['valid_to'], self.tgt['is_current']])
            conn.commit()

            # Steps
            inserted = []
            for st, step_params in step_rows:
                cursor.execute(f"""
                    INSERT INTO {META_SCHEMA}.META_ETL_JOB_STEP (
                        ETL_JOB_ID, STEP_NAME, STEP_ORDER, STEP_CATEGORY, SQL_TEMPLATE_PATH, SQL_INLINE,
                        PARAMETERS, IS_CRITICAL, ROLLBACK_ON_ERROR, IS_ACTIVE, RETRY_COUNT, TIMEOUT_SECONDS
                    ) VALUES (?, ?, ?, ?, ?, NULL, ?, 'Y', 'Y', 'Y', 3, 300)""",
                    [job_id, st.step_name, st.step_order, st.step_category,
                     f"{template.template_code}/{st.sql_template_path}" if st.sql_template_path else None,
                     json.dumps(step_params)])
                inserted.append(st.step_name)
            for i, (name, db, tab, ddl) in enumerate(ddls):
                cursor.execute(f"""
                    INSERT INTO {META_SCHEMA}.META_ETL_JOB_STEP (
                        ETL_JOB_ID, STEP_NAME, STEP_ORDER, STEP_CATEGORY, SQL_TEMPLATE_PATH, SQL_INLINE,
                        IS_CRITICAL, ROLLBACK_ON_ERROR, IS_ACTIVE, RETRY_COUNT, TIMEOUT_SECONDS
                    ) VALUES (?, ?, ?, 'DDL_CREATE', NULL, ?, 'Y', 'N', 'Y', 1, 120)""",
                    [job_id, name, i - len(ddls), ddl + ';'])
            conn.commit()

            # Parameterdateien und DDL-Dateien im Job-Ordner
            cursor.execute(f"SELECT ETL_JOB_STEP_ID, PARAMETERS FROM {META_SCHEMA}.META_ETL_JOB_STEP "
                           f"WHERE ETL_JOB_ID = ? AND PARAMETERS IS NOT NULL", [job_id])
            for sid, p in cursor.fetchall():
                write_step_parameters(job_id, int(sid), json.loads(p), get_etl_jobs_path())
            job_dir = Path(get_etl_jobs_path()) / str(job_id)
            (job_dir / 'cleanup').mkdir(parents=True, exist_ok=True)
            for name, db, tab, ddl in ddls:
                (job_dir / f"create_{tab.lower()}.ddl").write_text(
                    f"-- {name}: {db}.{tab}\n-- Generiert beim Job-Erstellen (Job ID: {job_id})\n\n{ddl};\n",
                    encoding='utf-8')
                (job_dir / 'cleanup' / f"drop_{tab.lower()}.sql").write_text(
                    f"-- ACHTUNG: Löscht {db}.{tab} inkl. aller Daten!\n-- Job ID: {job_id}\n\nDROP TABLE {db}.{tab};\n",
                    encoding='utf-8')
            return {'job_id': job_id, 'target_database': tgt_db, 'key_database': key_db,
                    'targets': {n: r['target'] for n, r in roles.items()}, 'target_table_ids': target_ids,
                    'steps': inserted}
        finally:
            cursor.close()
            conn.close()
