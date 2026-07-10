"""
LayerExportService (F10)
========================

Bulk-SQL-Export pro Layer-Transition (RAW->DISC, DISC->REUS) -- die
wiederverwendbare Service-Variante des Einmal-Skripts
``sql/export_layers/generate_export.py``.

Pro ETL-Job wird EIN SQL-Script erzeugt (analog "SQL Export"-Button im
Job-Detail), zusaetzlich optional die Tabellen-DDLs (DISC/REUS) und die
REUS-Quell-View-DDLs. Alles wird in ein ZIP gepackt.

Regeln (wie im Skript):
  * Reihenfolge / Nummerierung nach Foreign-Key-Topologie (Parent vor Child).
  * DDL_CREATE-Steps sind INAKTIV (auskommentiert).
  * DELETE_TARGET (Initial Load) ist AKTIV -- ausser im Delta-Modus.

Datenquelle: live aus MDP01_META ueber die bestehende ETLService-Connection
(keine statischen _meta/*.json mehr).

Pfade ausschliesslich aus ``config.PATHS`` -- keine hartkodierten Pfade.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from typing import Optional

from ..config import META_SCHEMA, PATHS
from .etl_service import ETLService
from .template_engine import SQLTemplateEngine

# Layer-IDs (bestaetigt gegen META_LAYER): RAW=1, DISC=2, REUS=3, CONS=4
LAYER = {"RAW": 1, "DISC": 2, "REUS": 3, "CONS": 4}

TRANSITIONS = {
    "raw_to_disc": {
        "label": "RAW -> DISC",
        "source_layer": LAYER["RAW"],
        "target_layer": LAYER["DISC"],
        "ddl_dir": "ddl/disc",
    },
    "disc_to_reus": {
        "label": "DISC -> REUS",
        "source_layer": LAYER["DISC"],
        "target_layer": LAYER["REUS"],
        "ddl_dir": "ddl/reus",
    },
}

RULE = "-- " + "=" * 76


# ---------------------------------------------------------------------------
# Text-Helfer (identisch zum bewaehrten generate_export.py)
# ---------------------------------------------------------------------------
def _norm(text: str) -> str:
    """Zeilenumbrueche normalisieren, trailing-spaces weg, Block-Einrueckung loesen."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    indents = [len(ln) - len(ln.lstrip()) for ln in lines if ln.strip()]
    if indents:
        cut = min(indents)
        lines = [ln[cut:] if ln.strip() else ln for ln in lines]
    return "\n".join(lines).strip("\n")


def _comment_block(text: str) -> str:
    return "\n".join(("-- " + ln) if ln else "--" for ln in _norm(text).split("\n"))


def _parse_table_name(ddl: str) -> str:
    m = re.search(r"CREATE\s+(?:SET|MULTISET)?\s*TABLE\s+([A-Za-z0-9_\.]+)", ddl or "", re.IGNORECASE)
    if not m:
        return "UNKNOWN_TABLE"
    return m.group(1).split(".")[-1]


class LayerExportService:
    """Erzeugt den Layer-Bulk-Export als In-Memory-Artefakte (+ ZIP)."""

    def __init__(self, etl_service: Optional[ETLService] = None):
        from .etl_service import get_etl_service
        self.etl = etl_service or get_etl_service()
        self.engine = SQLTemplateEngine(str(PATHS["sql_templates"]))
        self.gen_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # -- Live-Metadaten ----------------------------------------------------
    def _fetch_jobs(self, source_layer: int, target_layer: int) -> list[dict]:
        """Jobs einer Transition inkl. Source/Target-DB, Tabellen, View-Flag.

        Der View-Status wird aus ``dbc.TablesV`` bestimmt (Quelle der Wahrheit),
        nicht aus ``META_TABLE.table_kind`` -- letzteres kann veraltet sein
        (z.B. V_PART_PERSON ist real eine View, in META aber nicht als 'V' markiert).
        """
        conn = self.etl._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT j.etl_job_id, j.job_name,
                       sd.database_name AS source_db, st.table_name AS source_table,
                       td.database_name AS target_db, tt.table_name AS target_table,
                       tt.table_id      AS target_table_id
                FROM {META_SCHEMA}.META_ETL_JOB j
                JOIN {META_SCHEMA}.META_TABLE    st ON j.source_table_id = st.table_id
                JOIN {META_SCHEMA}.META_DATABASE sd ON st.database_id   = sd.database_id
                JOIN {META_SCHEMA}.META_TABLE    tt ON j.target_table_id = tt.table_id
                JOIN {META_SCHEMA}.META_DATABASE td ON tt.database_id   = td.database_id
                WHERE COALESCE(sd.layer_id, j.source_layer_id) = ?
                  AND COALESCE(td.layer_id, j.target_layer_id) = ?
                  AND j.is_active = 'Y'
                ORDER BY j.etl_job_id
                """,
                (source_layer, target_layer),
            )
            rows = cur.fetchall()
            jobs = [{
                "job_id": int(r[0]),
                "job_name": r[1],
                "source_db": r[2],
                "source_table": r[3],
                "target_db": r[4],
                "target_table": r[5],
                "target_table_id": int(r[6]),
            } for r in rows]

            # View-Status real aus dbc bestimmen
            view_set = self._fetch_view_names({j["source_db"] for j in jobs})
            for j in jobs:
                j["source_is_view"] = (j["source_db"], j["source_table"]) in view_set
            return jobs
        finally:
            conn.close()

    def _fetch_view_names(self, databases: set[str]) -> set[tuple[str, str]]:
        """Menge der (DB, View-Name) fuer die angegebenen Datenbanken (dbc.TablesV)."""
        databases = {d for d in databases if d}
        if not databases:
            return set()
        conn = self.etl._get_connection()
        try:
            cur = conn.cursor()
            placeholders = ", ".join("?" for _ in databases)
            cur.execute(
                f"SELECT TRIM(DatabaseName), TRIM(TableName) FROM dbc.TablesV "
                f"WHERE DatabaseName IN ({placeholders}) AND TableKind = 'V'",
                tuple(databases),
            )
            return {(db, name) for db, name in cur.fetchall()}
        finally:
            conn.close()


    def _fetch_fk_edges(self) -> list[tuple[int, int]]:
        """Alle FK-Kanten als (parent_table_id, child_table_id)."""
        conn = self.etl._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f"SELECT parent_table_id, child_table_id "
                f"FROM {META_SCHEMA}.META_FOREIGN_KEY"
            )
            return [(int(p), int(c)) for p, c in cur.fetchall() if p is not None and c is not None]
        finally:
            conn.close()

    def _fetch_view_ddl(self, db: str, view: str) -> Optional[str]:
        """RequestText einer View aus dbc.TablesV."""
        conn = self.etl._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT RequestText FROM dbc.TablesV "
                "WHERE DatabaseName = ? AND TableName = ? AND TableKind = 'V'",
                (db, view),
            )
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    # -- FK-Topologie ------------------------------------------------------
    def _order_jobs(self, jobs: list[dict]) -> list[dict]:
        """Parent-vor-Child Topologie ueber target_table_id (Kahn);
        stabiler Fallback auf job_id-Reihenfolge, wenn keine FK vorhanden."""
        ids = {j["target_table_id"] for j in jobs}
        edges = [(p, c) for p, c in self._fetch_fk_edges() if p in ids and c in ids and p != c]

        indeg = {i: 0 for i in ids}
        children: dict[int, list[int]] = {i: [] for i in ids}
        for parent, child in edges:
            children[parent].append(child)
            indeg[child] += 1

        # stabile Ausgangsreihenfolge = job_id
        order_by_id = [j["target_table_id"] for j in sorted(jobs, key=lambda x: x["job_id"])]
        ready = [i for i in order_by_id if indeg[i] == 0]
        result: list[int] = []
        while ready:
            node = ready.pop(0)
            result.append(node)
            for ch in children[node]:
                indeg[ch] -= 1
                if indeg[ch] == 0:
                    # an stabiler Position einfuegen
                    ready.append(ch)
                    ready.sort(key=lambda i: order_by_id.index(i))
        # Zyklen / Reste anhaengen
        for i in order_by_id:
            if i not in result:
                result.append(i)

        by_target = {j["target_table_id"]: j for j in jobs}
        ordered = [by_target[i] for i in result]
        for seq, j in enumerate(ordered, start=1):
            j["seq"] = seq * 10
        return ordered

    # -- Rendering ---------------------------------------------------------
    def _render_step(self, step) -> str:
        try:
            if step.sql_template_path:
                params = step.parameters if isinstance(step.parameters, dict) else {}
                return self.engine.render(step.sql_template_path, params).strip()
            if step.sql_inline:
                return _norm(step.sql_inline).strip()
            return "-- (kein SQL)"
        except Exception as e:  # noqa: BLE001 -- defensiv wie im Original
            return f"-- RENDER ERROR: {e}"

    def _step_header(self, step, inactive: bool = False) -> str:
        tag = "  [INAKTIV]" if inactive else ""
        h = [
            RULE,
            f"-- Step {step.step_order}: {step.step_name}{tag}",
            f"-- Category: {step.step_category}",
        ]
        if step.sql_template_path:
            h.append(f"-- Template: {step.sql_template_path}")
        h.append(RULE)
        return "\n".join(h)

    def _build_job_script(self, job: dict, label: str, mode: str) -> tuple[str, list[tuple[str, str]]]:
        """Liefert (script_text, [(ddl_table_name, ddl_text), ...])."""
        steps = self.etl.get_job_steps(job["job_id"])
        steps.sort(key=lambda s: s.step_order)

        parts = [
            RULE,
            f"-- Job {job['seq']:03d}: {job['job_name']}",
            f"-- Transition: {label}",
            f"-- Source: {job['source_db']}.{job['source_table']}"
            + ("  (VIEW)" if job["source_is_view"] else ""),
            f"-- Target: {job['target_db']}.{job['target_table']}",
            f"-- Generiert: {self.gen_ts}",
            "--",
            "-- Hinweis: CREATE-TABLE-Steps (DDL_CREATE) sind auskommentiert (inaktiv).",
            "--          DELETE-Step (Initial Load) ist "
            + ("AKTIV." if mode == "initial_load" else "im Delta-Modus uebersprungen."),
            RULE,
            "",
        ]

        ddl_create = [s for s in steps if s.step_category == "DDL_CREATE"]
        active = []
        for s in steps:
            if s.step_category == "DDL_CREATE":
                continue
            if s.is_active.strip() != "Y":
                continue
            if mode == "delta" and s.step_category == "DELETE_TARGET":
                continue
            active.append(s)

        if ddl_create:
            parts.append("-- ####################################################################")
            parts.append("-- ## INAKTIVE CREATE-TABLE-STEPS (Tabellen werden NICHT neu erstellt) ##")
            parts.append("-- ####################################################################")
            parts.append("")
            for s in ddl_create:
                parts.append(self._step_header(s, inactive=True))
                parts.append(_comment_block(s.sql_inline or "-- (kein SQL)"))
                parts.append("")

        for s in active:
            parts.append(self._step_header(s))
            parts.append(self._render_step(s))
            parts.append("")

        content = "\n".join(parts).rstrip() + "\n"

        ddls: list[tuple[str, str]] = []
        for s in ddl_create:
            ddl = _norm(s.sql_inline or "")
            tname = _parse_table_name(ddl)
            head = (
                f"-- DDL: {tname}\n"
                f"-- Quelle: META_ETL_JOB_STEP (Job {job['job_id']}, '{s.step_name}')\n"
                f"-- Generiert: {self.gen_ts}\n"
            )
            ddls.append((tname, head + "\n" + ddl + "\n"))
        return content, ddls

    # -- Public ------------------------------------------------------------
    def generate(
        self,
        transitions: Optional[list[str]] = None,
        include_ddl: bool = True,
        include_views: bool = True,
        mode: str = "initial_load",
    ) -> dict[str, str]:
        """Erzeugt alle Artefakte als {relativer_pfad: inhalt}."""
        if not transitions:
            transitions = ["raw_to_disc", "disc_to_reus"]
        if mode not in ("initial_load", "delta"):
            mode = "initial_load"

        artifacts: dict[str, str] = {}
        for transition in transitions:
            cfg = TRANSITIONS.get(transition)
            if not cfg:
                continue
            jobs = self._fetch_jobs(cfg["source_layer"], cfg["target_layer"])
            jobs = self._order_jobs(jobs)

            for job in jobs:
                script, ddls = self._build_job_script(job, cfg["label"], mode)
                fname = f"{job['seq']:03d}_{job['job_name']}.sql"
                artifacts[f"{transition}/{fname}"] = script

                if include_ddl:
                    for tname, ddl_text in ddls:
                        artifacts[f"{cfg['ddl_dir']}/{tname}.sql"] = ddl_text

                if include_views and job["source_is_view"]:
                    rtext = self._fetch_view_ddl(job["source_db"], job["source_table"])
                    if rtext:
                        head = (
                            f"-- View-DDL: {job['source_table']}\n"
                            f"-- Database: {job['source_db']}\n"
                            f"-- Quelle: dbc.TablesV.RequestText\n"
                            f"-- Generiert: {self.gen_ts}\n"
                        )
                        artifacts[f"views/{job['source_table']}.sql"] = head + "\n" + _norm(rtext) + "\n"

        return artifacts

    def generate_zip(
        self,
        transitions: Optional[list[str]] = None,
        include_ddl: bool = True,
        include_views: bool = True,
        mode: str = "initial_load",
    ) -> tuple[bytes, dict]:
        """Wie generate(), packt aber in ein ZIP. Liefert (zip_bytes, manifest)."""
        artifacts = self.generate(transitions, include_ddl, include_views, mode)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for path, content in sorted(artifacts.items()):
                zf.writestr(path, content)
        buf.seek(0)

        manifest = {
            "generated": self.gen_ts,
            "mode": mode,
            "transitions": transitions or ["raw_to_disc", "disc_to_reus"],
            "include_ddl": include_ddl,
            "include_views": include_views,
            "file_count": len(artifacts),
            "files": sorted(artifacts.keys()),
        }
        return buf.getvalue(), manifest


def get_layer_export_service() -> LayerExportService:
    return LayerExportService()
