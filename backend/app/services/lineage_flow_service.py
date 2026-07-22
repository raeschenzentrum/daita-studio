"""
LineageFlowService – ermittelt den Herkunftsgraphen (Upstream / Dataflow) eines
Objekts.

Herkunft entsteht aus zwei Quellen:
1. **ETL-Kanten** – materialisierte Strecken über ``META_ETL_JOB``
   (source_table_id -> target_table_id).
2. **View-Kanten** – Abhängigkeiten aus der View-Definition (``dbc.TablesV``
   RequestText), per sqlglot geparst und gegen ``META_TABLE`` aufgelöst.

Read-only – es werden ausschließlich SELECTs ausgeführt, keine Schreibzugriffe.
View-DDLs werden live geparst (noch keine Persistenz).
Spaltennamen/Aliase sind an meta_service.py angelehnt.
"""

import re
import hashlib
import threading
from typing import Optional

import sqlglot
import teradatasql

from app.config import DB_CONFIG, META_SCHEMA


# Pro Request (Thread) genutzte Verbindung – wird von build_dataflow gesetzt,
# damit nicht jede einzelne Query eine neue Teradata-Verbindung aufbaut.
_local = threading.local()


# ---------------------------------------------------------------------------
# Verbindungshelfer (analog meta_service, bewusst eigenständig / read-only)
# ---------------------------------------------------------------------------

def _connect():
    return teradatasql.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["username"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
    )


def _query(sql: str, params: tuple = ()) -> list[dict]:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0].lower() for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    with _connect() as c:
        with c.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0].lower() for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def _execute(sql: str, params: tuple = ()) -> None:
    """Schreibender Aufruf (DML) mit commit. Nur für Persistenz-Cache."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
        return
    with _connect() as c:
        with c.cursor() as cur:
            cur.execute(sql, params)
        c.commit()


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------

def _fetch_node(table_id: int) -> Optional[dict]:
    """Metadaten eines Objekts (Tabelle/View) inkl. Layer für die Knoten-Box."""
    rows = _query(
        f"""
        SELECT
            t.table_id,
            t.table_name,
            t.comment_string  AS table_desc,
            d.database_name    AS db_name,
            t.layer_id,
            l.layer_code,
            l.layer_name,
            l.layer_sequence,
            t.table_kind       AS object_type
        FROM {META_SCHEMA}.META_TABLE t
        JOIN {META_SCHEMA}.META_DATABASE d ON t.database_id = d.database_id
        LEFT JOIN {META_SCHEMA}.META_LAYER l ON t.layer_id = l.layer_id
        WHERE t.table_id = ?
        """,
        (table_id,),
    )
    return rows[0] if rows else None


def _upstream_etl_edges(table_id: int) -> list[dict]:
    """Alle ETL-Jobs, die ``table_id`` als Ziel befüllen (Upstream-Quellen)."""
    return _query(
        f"""
        SELECT
            j.etl_job_id,
            j.job_name,
            j.source_table_id
        FROM {META_SCHEMA}.META_ETL_JOB j
        WHERE j.target_table_id = ?
          AND j.source_table_id IS NOT NULL
        """,
        (table_id,),
    )


# ---------------------------------------------------------------------------
# View-Abhängigkeiten (live aus dbc.TablesV, per sqlglot)
# ---------------------------------------------------------------------------

def _fetch_view_ddl(db_name: str, view_name: str) -> Optional[str]:
    """RequestText (CREATE/REPLACE VIEW …) einer View aus dbc.TablesV."""
    if not db_name or not view_name:
        return None
    rows = _query(
        "SELECT RequestText FROM dbc.TablesV "
        "WHERE DatabaseName = ? AND TableName = ? AND TableKind = 'V'",
        (db_name, view_name),
    )
    if not rows:
        return None
    # Spaltenname kommt kleingeschrieben aus _query
    val = rows[0].get("requesttext")
    return str(val) if val is not None else None


def _parse_view_ddl(ddl: str):
    """
    View-DDL robust zu einem sqlglot-Ausdruck parsen.

    Behandelt ``REPLACE VIEW`` (→ CREATE VIEW) und fällt bei Parser-Fehlern auf
    das Parsen ab dem ersten ``SELECT`` zurück. Gibt None zurück, wenn nichts
    parsebar ist.
    """
    if not ddl:
        return None
    ddl2 = re.sub(r"^\s*REPLACE\s+VIEW", "CREATE VIEW", ddl, flags=re.IGNORECASE)
    for candidate in (ddl2, None):
        text = candidate
        if text is None:
            m = re.search(r"\bSELECT\b", ddl2, flags=re.IGNORECASE)
            if not m:
                return None
            text = ddl2[m.start():]
        try:
            parsed = sqlglot.parse_one(text, read="teradata")
            if parsed is not None:
                return parsed
        except Exception:
            continue
    return None


def _extract_view_sources(ddl: str, self_db: str, self_name: str) -> list[tuple]:
    """
    Quell-Objekte (db, name) aus einer View-DDL extrahieren.

    Robust gegen ``REPLACE VIEW`` (→ CREATE VIEW) und Parser-Fehler
    (Fallback: ab erstem SELECT parsen). Die View selbst wird ausgeschlossen.
    Rückgabe: Liste von (db_or_None, name) in Großschreibung, dedupliziert.
    """
    parsed = _parse_view_ddl(ddl)
    if parsed is None:
        return []

    self_db_u = (self_db or "").upper()
    self_name_u = (self_name or "").upper()

    # CTE-Namen (WITH-Blöcke) sind keine echten Quellobjekte
    cte_names = set()
    for cte in parsed.find_all(sqlglot.exp.CTE):
        cname = (cte.alias_or_name or "").upper()
        if cname:
            cte_names.add(cname)

    seen = set()
    result: list[tuple] = []
    for t in parsed.find_all(sqlglot.exp.Table):
        name = (t.name or "").upper()
        if not name:
            continue
        db = (t.db or "").upper() or None
        # die View selbst nicht als Quelle zählen
        if name == self_name_u and (db == self_db_u or db is None):
            continue
        # CTE-Referenz (ohne DB-Qualifizierung) überspringen
        if db is None and name in cte_names:
            continue
        key = (db, name)
        if key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _extract_view_columns(ddl: str) -> list[dict]:
    """
    Spalten-Mapping einer View extrahieren (ein Hop).

    Je Zielspalte: welche Quell-Spalten (mit aufgelöstem Tabellen-Alias) fließen
    ein und welcher Transformationstyp liegt vor.

    Rückgabe je Spalte:
      { target_column, transform_type, expression, sources: [{table, column}] }
    transform_type ∈ {DIRECT, CAST, CASE, COMPUTED, ALL_COLUMNS}
    """
    parsed = _parse_view_ddl(ddl)
    if parsed is None:
        return []

    select = parsed if isinstance(parsed, sqlglot.exp.Select) else parsed.find(sqlglot.exp.Select)
    if select is None:
        return []

    # Alias/Name → volle Objektbezeichnung (DB.NAME)
    alias_map: dict[str, str] = {}
    for t in select.find_all(sqlglot.exp.Table):
        full = f"{t.db}.{t.name}" if t.db else (t.name or "")
        if not full:
            continue
        if t.alias:
            alias_map[str(t.alias).upper()] = full
        if t.name:
            alias_map[str(t.name).upper()] = full
    distinct_tables = set(alias_map.values())
    sole_table = next(iter(distinct_tables)) if len(distinct_tables) == 1 else None

    cols: list[dict] = []
    for proj in select.expressions:
        if isinstance(proj, sqlglot.exp.Star):
            cols.append({
                "target_column": "*",
                "transform_type": "ALL_COLUMNS",
                "expression": "*",
                "sources": [],
            })
            continue

        inner = proj.this if isinstance(proj, sqlglot.exp.Alias) else proj
        target = proj.alias_or_name or (inner.sql(dialect="teradata") if inner is not None else "")

        try:
            expr_str = inner.sql(dialect="teradata")
        except Exception:
            expr_str = str(inner)

        up = expr_str.upper()
        if isinstance(inner, sqlglot.exp.Column):
            tt = "DIRECT"
        elif "CASE" in up and "WHEN" in up:
            tt = "CASE"
        elif "CAST" in up or "CONVERT" in up:
            tt = "CAST"
        else:
            tt = "COMPUTED"

        sources = []
        seen = set()
        for c in inner.find_all(sqlglot.exp.Column):
            tab = str(c.table).upper() if c.table else None
            resolved = alias_map.get(tab) if tab else sole_table
            colname = c.name
            key = (resolved, colname)
            if key not in seen:
                seen.add(key)
                sources.append({"table": resolved, "column": colname})

        cols.append({
            "target_column": target,
            "transform_type": tt,
            "expression": expr_str,
            "sources": sources,
        })
    return cols


def _resolve_object(db_name: Optional[str], table_name: str) -> Optional[int]:
    """(db, name) → table_id aus META_TABLE. db optional (dann nur über Name)."""
    if db_name:
        rows = _query(
            f"""
            SELECT t.table_id
            FROM {META_SCHEMA}.META_TABLE t
            JOIN {META_SCHEMA}.META_DATABASE d ON t.database_id = d.database_id
            WHERE UPPER(t.table_name) = ? AND UPPER(d.database_name) = ?
            """,
            (table_name.upper(), db_name.upper()),
        )
    else:
        rows = _query(
            f"""
            SELECT t.table_id
            FROM {META_SCHEMA}.META_TABLE t
            WHERE UPPER(t.table_name) = ?
            """,
            (table_name.upper(),),
        )
    return rows[0]["table_id"] if rows else None


# ---------------------------------------------------------------------------
# Persistenz-Cache (META_VIEW_LINEAGE) – fehlertolerant
# ---------------------------------------------------------------------------
# Speichert das geparste Ergebnis je View, invalidiert über den Hash der DDL.
# Ein Marker-Eintrag (alle Quell-Spalten NULL) kennzeichnet "geparst, 0 Quellen".

def _ddl_hash(ddl: str) -> str:
    return hashlib.sha256(ddl.encode("utf-8", "ignore")).hexdigest()


def _load_cached_view_edges(view_table_id: int, request_hash: str) -> Optional[list[dict]]:
    """
    Liefert gecachte View-Quellen, wenn ein Eintrag mit passendem Hash existiert,
    sonst None (→ neu parsen). Fehler (z. B. Tabelle fehlt) → None.
    """
    try:
        rows = _query(
            f"""
            SELECT source_table_id, source_db, source_name, request_text_hash
            FROM {META_SCHEMA}.META_VIEW_LINEAGE
            WHERE view_table_id = ?
            """,
            (view_table_id,),
        )
    except Exception:
        return None
    if not rows:
        return None
    if (rows[0].get("request_text_hash") or "") != request_hash:
        return None
    edges = []
    for r in rows:
        stid = r.get("source_table_id")
        sdb = r.get("source_db")
        sname = r.get("source_name")
        if stid is None and sdb is None and sname is None:
            continue  # Marker "0 Quellen"
        edges.append({"source_table_id": stid, "source_db": sdb, "source_name": sname})
    return edges


def _store_cached_view_edges(view_table_id: int, request_hash: str, edges: list[dict]) -> None:
    """Cache aktualisieren (alte Einträge ersetzen). Fehler werden geschluckt."""
    try:
        _execute(
            f"DELETE FROM {META_SCHEMA}.META_VIEW_LINEAGE WHERE view_table_id = ?",
            (view_table_id,),
        )
        ins = (
            f"INSERT INTO {META_SCHEMA}.META_VIEW_LINEAGE "
            f"(view_table_id, source_table_id, source_db, source_name, request_text_hash, parsed_at) "
            f"VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP(0))"
        )
        if not edges:
            _execute(ins, (view_table_id, None, None, None, request_hash))
        else:
            for e in edges:
                _execute(ins, (
                    view_table_id,
                    e.get("source_table_id"),
                    e.get("source_db"),
                    e.get("source_name"),
                    request_hash,
                ))
    except Exception:
        pass  # Persistenz darf die Anzeige nie brechen


def _upstream_view_edges(node: dict) -> list[dict]:
    """
    View-Quellen eines Objekts ableiten.

    Ob ein Objekt eine View ist, wird an der **Quelle der Wahrheit** ``dbc.TablesV``
    (TableKind='V') festgemacht – NICHT an ``META_TABLE.table_kind`` (dort teils leer).
    Liefert ``_fetch_view_ddl`` eine DDL, gilt der Knoten als View; sein
    ``object_type`` wird auf ``'V'`` korrigiert.

    Das Parse-Ergebnis wird in ``META_VIEW_LINEAGE`` (Hash der DDL) gecacht.

    Rückgabe je Quelle:
      { source_table_id | None, source_db, source_name }
    ``source_table_id`` ist None, wenn die Quelle nicht in META_TABLE auflösbar ist
    (externer Knoten).
    """
    if not node or node.get("is_external"):
        return []

    ddl = None
    try:
        ddl = _fetch_view_ddl(node.get("db_name"), node.get("table_name"))
    except Exception:
        ddl = None
    if not ddl:
        return []

    # dbc bestätigt: es ist eine View → object_type korrigieren (Badge/Anzeige)
    node["object_type"] = "V"

    view_table_id = node.get("table_id")
    request_hash = _ddl_hash(ddl)

    # 1) Cache
    if isinstance(view_table_id, int):
        cached = _load_cached_view_edges(view_table_id, request_hash)
        if cached is not None:
            return cached

    # 2) Live parsen + auflösen
    edges = []
    for db, name in _extract_view_sources(ddl, node.get("db_name"), node.get("table_name")):
        edges.append({
            "source_table_id": _resolve_object(db, name),
            "source_db": db,
            "source_name": name,
        })

    # 3) Cache schreiben
    if isinstance(view_table_id, int):
        _store_cached_view_edges(view_table_id, request_hash, edges)

    return edges


# ---------------------------------------------------------------------------
# Downstream (vorwärts): wer nutzt dieses Objekt?
# ---------------------------------------------------------------------------

def _downstream_etl_edges(table_id: int) -> list[dict]:
    """ETL-Jobs, die ``table_id`` als Quelle nutzen (befüllte Ziele)."""
    return _query(
        f"""
        SELECT j.etl_job_id, j.job_name, j.target_table_id
        FROM {META_SCHEMA}.META_ETL_JOB j
        WHERE j.source_table_id = ?
          AND j.target_table_id IS NOT NULL
        """,
        (table_id,),
    )


def _downstream_view_edges(node: dict) -> list[dict]:
    """
    Views, die ``node`` als Quelle referenzieren.

    Vorfilter über ``dbc.TablesV.RequestText LIKE '%NAME%'`` (billig), danach
    parse-bestätigt über ``_upstream_view_edges`` (nutzt den Cache). Nur Views,
    deren aufgelöste Quellen die ``table_id`` enthalten, zählen.
    Rückgabe je Konsument: ``{ view_table_id }``.
    """
    if not node or node.get("is_external"):
        return []
    name = (node.get("table_name") or "")
    if not name:
        return []
    target_id = node.get("table_id")

    try:
        cands = _query(
            "SELECT TRIM(DatabaseName) AS db, TRIM(TableName) AS nm "
            "FROM dbc.TablesV WHERE TableKind = 'V' AND UPPER(RequestText) LIKE ?",
            ("%" + name.upper() + "%",),
        )
    except Exception:
        return []

    result = []
    seen = set()
    for c in cands:
        cdb, cnm = c.get("db"), c.get("nm")
        if not cnm:
            continue
        vid = _resolve_object(cdb, cnm)
        if vid is None or vid == target_id or vid in seen:
            continue
        vnode = {"db_name": cdb, "table_name": cnm, "table_id": vid, "is_external": False}
        srcs = _upstream_view_edges(vnode)
        if any(s.get("source_table_id") == target_id for s in srcs):
            seen.add(vid)
            result.append({"view_table_id": vid})
    return result


# ---------------------------------------------------------------------------
# Graph-Aufbau (Traversierung, Upstream/Downstream)
# ---------------------------------------------------------------------------

def build_dataflow(root_table_id: int, depth: int = 12, direction: str = "upstream") -> dict:
    """
    Öffentliche Einstiegsfunktion. Öffnet **eine** Verbindung für den gesamten
    Traversierungslauf (spart pro Query einen Verbindungsaufbau) und delegiert an
    die eigentliche Logik.

    direction: ``upstream`` (Herkunft, Standard), ``downstream`` (Verwendung)
    oder ``both``.
    """
    conn = _connect()
    _local.conn = conn
    try:
        return _build_dataflow_impl(root_table_id, depth, direction)
    finally:
        _local.conn = None
        try:
            conn.close()
        except Exception:
            pass


def get_view_ddl(table_id: int) -> dict:
    """
    View-DDL (RequestText aus dbc.TablesV) eines Objekts.

    Rückgabe: ``{table_id, db_name, table_name, ddl}`` – ``ddl`` ist None, wenn
    das Objekt keine View ist oder keine DDL gefunden wurde.
    Zeilenenden werden auf ``\\n`` normalisiert (View-DDLs nutzen teils nur ``\\r``).
    """
    conn = _connect()
    _local.conn = conn
    try:
        node = _fetch_node(table_id)
        if node is None:
            return {"table_id": table_id, "db_name": None, "table_name": None, "ddl": None}
        ddl = None
        try:
            ddl = _fetch_view_ddl(node.get("db_name"), node.get("table_name"))
        except Exception:
            ddl = None
        columns = []
        if ddl:
            try:
                columns = _extract_view_columns(ddl)
            except Exception:
                columns = []
            ddl = ddl.replace("\r\n", "\n").replace("\r", "\n")
        return {
            "table_id": table_id,
            "db_name": node.get("db_name"),
            "table_name": node.get("table_name"),
            "ddl": ddl,
            "columns": columns,
        }
    finally:
        _local.conn = None
        try:
            conn.close()
        except Exception:
            pass


def _build_dataflow_impl(root_table_id: int, depth: int = 12, direction: str = "upstream") -> dict:
    """
    Baut den Datenfluss-Graphen eines Objekts als {nodes, edges}.

    Folgt sowohl materialisierten ETL-Strecken (``META_ETL_JOB``) als auch
    View-Abhängigkeiten (View-DDL via sqlglot).

    Args:
        root_table_id: Startobjekt.
        depth:         maximale Traversierungstiefe (Schutz vor Riesen-Graphen).
        direction:     ``upstream`` (Herkunft), ``downstream`` (Verwendung) oder ``both``.

    Returns:
        dict mit ``root_table_id``, ``direction``, ``nodes`` (Liste), ``edges`` (Liste).
    """
    want_up = direction in ("upstream", "both")
    want_down = direction in ("downstream", "both")

    root = _fetch_node(root_table_id)
    if root is None:
        return {
            "root_table_id": root_table_id,
            "direction": direction,
            "nodes": [],
            "edges": [],
            "error": f"Objekt {root_table_id} nicht in META_TABLE gefunden",
        }

    nodes: dict = {}
    edges: list[dict] = []
    seen_edges: set = set()
    visited: set = set()

    queue: list[tuple] = [(root_table_id, 0)]

    def _ensure_node(tid):
        """Knoten (int table_id) einmalig laden und ablegen."""
        if tid in nodes:
            return nodes[tid]
        node = _fetch_node(tid)
        if node is None:
            nodes[tid] = {
                "table_id": tid, "table_name": f"#{tid}", "table_desc": None,
                "db_name": None, "layer_id": None, "layer_code": None,
                "layer_name": None, "layer_sequence": None, "object_type": None,
                "is_external": True,
            }
        else:
            node["is_external"] = False
            node["is_root"] = (tid == root_table_id)
            nodes[tid] = node
        return nodes[tid]

    def _ensure_external(ext_id, db, name):
        if ext_id in nodes:
            return nodes[ext_id]
        nodes[ext_id] = {
            "table_id": ext_id,
            "table_name": (f"{db}.{name}" if db else name),
            "table_desc": None, "db_name": db, "layer_id": None,
            "layer_code": None, "layer_name": None, "layer_sequence": None,
            "object_type": None, "is_external": True,
        }
        return nodes[ext_id]

    def _add_edge(src, tid, edge_type, etl_job_id=None, job_name=None):
        key = (src, tid, edge_type, etl_job_id)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({
            "from_table_id": src,
            "to_table_id": tid,
            "edge_type": edge_type,
            "etl_job_id": etl_job_id,
            "job_name": job_name,
        })

    while queue:
        tid, d = queue.pop(0)
        node = _ensure_node(tid)

        if tid in visited:
            continue
        visited.add(tid)

        if d >= depth:
            continue

        # ── Upstream (Herkunft) ──────────────────────────────────────────
        if want_up:
            # 1) ETL-Kanten
            for e in _upstream_etl_edges(tid):
                src = e["source_table_id"]
                _ensure_node(src)
                _add_edge(src, tid, "ETL", e["etl_job_id"], e["job_name"])
                if src not in visited:
                    queue.append((src, d + 1))

            # 2) View-Kanten (nur wenn der Knoten selbst eine View ist)
            for v in _upstream_view_edges(node):
                src_id = v["source_table_id"]
                if src_id is not None:
                    if src_id == tid:
                        continue
                    _ensure_node(src_id)
                    _add_edge(src_id, tid, "VIEW")
                    if src_id not in visited:
                        queue.append((src_id, d + 1))
                else:
                    ext_id = f"EXT::{v['source_db'] or ''}.{v['source_name']}"
                    _ensure_external(ext_id, v["source_db"], v["source_name"])
                    _add_edge(ext_id, tid, "VIEW")

        # ── Downstream (Verwendung) ──────────────────────────────────────
        if want_down:
            # 3) ETL-Kanten: Jobs, die tid als Quelle nutzen
            for e in _downstream_etl_edges(tid):
                tgt = e["target_table_id"]
                _ensure_node(tgt)
                _add_edge(tid, tgt, "ETL", e["etl_job_id"], e["job_name"])
                if tgt not in visited:
                    queue.append((tgt, d + 1))

            # 4) View-Kanten: Views, die tid referenzieren
            for v in _downstream_view_edges(node):
                vid = v["view_table_id"]
                if vid == tid:
                    continue
                _ensure_node(vid)
                _add_edge(tid, vid, "VIEW")
                if vid not in visited:
                    queue.append((vid, d + 1))

    return {
        "root_table_id": root_table_id,
        "direction": direction,
        "nodes": list(nodes.values()),
        "edges": edges,
    }

