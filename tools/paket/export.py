"""
Export der Paketteile aus der Entwicklungsumgebung (Bibliothek).

Aufgerufen vom Aufrufskript im Kunden-Workspace (z. B.
<kunde>-lakehouse/deploy/paket_<kunde>.py), das Umfang und Ziel festlegt.
Jede Funktion schreibt ihre Dateien in den PaketSchreiber und gibt den
Manifest-Eintrag ihres Teils zurück.

Konzept: daita-studio/docs/PAKET_DEPLOYMENT_KONZEPT.md
"""
import subprocess
from pathlib import Path

from meta_modell import LAUFZEIT_SPALTEN, JOB_SPALTE, TEMPLATE_SPALTE, tabellen
from paket_format import ndjson, sha256_datei, tabelle_signatur, tabelle_zerlegen, view_signatur, wert_aus_db

AUSGESCHLOSSEN = ("__pycache__", ".pyc", ".DS_Store")


# ---------------------------------------------------------------------------
# DB-Helfer
# ---------------------------------------------------------------------------
def abfrage(cur, sql, params=None):
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    return cur.fetchall()


def objekte(cur, db):
    """{Name: Art} mit Art T (Tabelle), V (View) oder anderem TableKind."""
    return {n: k.strip() for n, k in abfrage(
        cur, "SELECT TRIM(TableName), TableKind FROM dbc.TablesV WHERE DatabaseName = ? ORDER BY 1", (db,))}


def show(cur, db, name, art):
    return "".join(r[0] for r in abfrage(cur, 'SHOW {} {}."{}"'.format(art, db, name))).replace("\r", "\n")


def spalten(cur, db, tabelle):
    return [r[0] for r in abfrage(
        cur, "SELECT TRIM(ColumnName) FROM dbc.ColumnsV WHERE DatabaseName = ? AND TableName = ? "
             "ORDER BY ColumnId", (db, tabelle))]


def spalten_signatur(cur, db, tabelle):
    """Spalten mit Typ, Länge, Stellen, NULL - für den Abgleich von Voraussetzungen."""
    return ["{} {} {} {} {} {}".format(n, (t or "").strip(), l, d, f, (nu or "").strip()) for n, t, l, d, f, nu in abfrage(
        cur, "SELECT TRIM(ColumnName), ColumnType, ColumnLength, DecimalTotalDigits, DecimalFractionalDigits, "
             "Nullable FROM dbc.ColumnsV WHERE DatabaseName = ? AND TableName = ? ORDER BY ColumnId", (db, tabelle))]


def git_stand(pfad):
    """{commit, geaendert} des Repos, in dem pfad liegt; None ohne Git."""
    try:
        commit = subprocess.check_output(["git", "-C", str(pfad), "rev-parse", "--short", "HEAD"],
                                         stderr=subprocess.DEVNULL).decode().strip()
        status = subprocess.check_output(["git", "-C", str(pfad), "status", "--porcelain"],
                                         stderr=subprocess.DEVNULL).decode().strip()
        return {"commit": commit, "geaendert": bool(status)}
    except (OSError, subprocess.CalledProcessError):
        return None


# ---------------------------------------------------------------------------
# Strukturen (auch Meta-Schema)
# ---------------------------------------------------------------------------
def export_strukturen(cur, schreiber, teil, datenbanken, auslassen=(), voraussetzungen=None, startdaten=()):
    """SHOW TABLE / SHOW VIEW aller Objekte der Datenbanken.

    voraussetzungen: {"meta_schema": ..., "datenbanken": [...]} - Tabellen, die
        in META registriert sind und in diesen Datenbanken liegen (z. B. RAW),
        werden nur mit ihren Spalten gelistet und auf dem Ziel geprüft.
    startdaten: [{"db", "tabelle", "bedingung", "schluessel": [...]}]
    """
    auslassen = {a.upper() for a in auslassen}
    eintraege, hinweise = [], []
    for db in datenbanken:
        for name, art in objekte(cur, db).items():
            if name.upper() in auslassen or "{}.{}".format(db, name).upper() in auslassen:
                continue
            if art not in ("T", "V", "O"):
                hinweise.append("{}.{}: TableKind {} wird nicht übernommen".format(db, name, art))
                continue
            if art == "V":
                ddl = show(cur, db, name, "VIEW")
                e = {"db": db, "name": name, "art": "V", "signatur": view_signatur(ddl)}
            else:
                ddl = show(cur, db, name, "TABLE")
                t = tabelle_zerlegen(ddl)
                e = {"db": db, "name": name, "art": "T", "signatur": tabelle_signatur(ddl),
                     "spalten": [n for n, _ in t["spalten"]]}
            e["hash"] = schreiber.text("{}/{}/{}.sql".format(teil, db, name), ddl)
            eintraege.append(e)

    vor = []
    if voraussetzungen:
        ms = voraussetzungen["meta_schema"]
        for db in voraussetzungen["datenbanken"]:
            registriert = [r[0] for r in abfrage(
                cur, "SELECT TRIM(t.table_name) FROM {0}.META_TABLE t JOIN {0}.META_DATABASE d "
                     "ON d.database_id = t.database_id WHERE d.database_name = ? ORDER BY 1".format(ms), (db,))]
            vorhanden = objekte(cur, db)
            for name in registriert:
                if name in vorhanden:
                    vor.append({"db": db, "name": name, "spalten": spalten_signatur(cur, db, name)})
                else:
                    hinweise.append("Voraussetzung {}.{} ist in META registriert, fehlt aber in der Quelle".format(db, name))

    start = []
    for s in startdaten:
        cols = spalten(cur, s["db"], s["tabelle"])
        rows = abfrage(cur, 'SELECT {} FROM {}.{} WHERE {}'.format(
            ", ".join('"{}"'.format(c) for c in cols), s["db"], s["tabelle"], s["bedingung"]))
        datei = "{}/startdaten/{}.{}.ndjson".format(teil, s["db"], s["tabelle"])
        h = schreiber.text(datei, ndjson([[wert_aus_db(v) for v in r] for r in rows]))
        start.append({"db": s["db"], "tabelle": s["tabelle"], "schluessel": s["schluessel"],
                      "spalten": cols, "zeilen": len(rows), "datei": datei, "hash": h})

    return {"datenbanken": list(datenbanken), "auslassen": sorted(auslassen), "objekte": eintraege,
            "voraussetzungen": vor, "startdaten": start, "hinweise": hinweise}


# ---------------------------------------------------------------------------
# META-Zeilen (Jobs, Vorlagen)
# ---------------------------------------------------------------------------
def _echter_name(namen, gesucht):
    m = {n.upper(): n for n in namen}
    return m[gesucht.upper()]


def export_meta(cur, schreiber, teil, schema, job_ids=None, template_codes=None):
    """Zeilen der META-Tabellen eines Teils ("jobs" oder "vorlagen").

    job_ids / template_codes: Umfang für Teilpakete (None = alles). Gefiltert
    werden nur Tabellen mit Job- bzw. Template-Spalte; Löschungen auf dem
    Ziel wirken nur innerhalb dieses Umfangs.
    """
    vorhanden = objekte(cur, schema)
    filter_werte, filter_spalten = None, {}
    if teil == "jobs" and job_ids is not None:
        filter_werte, filter_spalten = sorted(int(i) for i in job_ids), JOB_SPALTE
    if teil == "vorlagen" and template_codes is not None:
        codes = [c.upper() for c in template_codes]
        filter_werte = sorted(int(r[0]) for r in abfrage(
            cur, "SELECT TEMPLATE_ID FROM {}.META_ETL_JOB_TEMPLATE WHERE TEMPLATE_CODE IN ({})".format(
                schema, ", ".join("?" * len(codes))), codes)) if codes else []
        filter_spalten = TEMPLATE_SPALTE

    eintraege, hinweise = [], []
    for tabelle, id_spalten, schluessel in tabellen(teil):
        if tabelle not in vorhanden:
            hinweise.append("{}.{} fehlt in der Quelle".format(schema, tabelle))
            continue
        alle = spalten(cur, schema, tabelle)
        weg = {s.upper() for s in LAUFZEIT_SPALTEN.get(tabelle, [])}
        cols = [c for c in alle if c.upper() not in weg]
        ids = [_echter_name(alle, s) for s in id_spalten]
        key = [_echter_name(alle, s) for s in schluessel] if schluessel else None
        where, params, filt = "", [], None
        if filter_werte is not None and tabelle in filter_spalten:
            fs = _echter_name(alle, filter_spalten[tabelle])
            filt = {"spalte": fs, "werte": filter_werte}
            where = " WHERE {} IN ({})".format(fs, ", ".join(str(int(v)) for v in filter_werte) or "NULL")
            if tabelle == "META_ETL_DEPENDENCY":
                where += " AND parent_job_id IN ({})".format(", ".join(str(int(v)) for v in filter_werte) or "NULL")
            if tabelle == "META_ETL_TEST":
                where = " WHERE {0} IS NULL OR {0} IN ({1})".format(fs, ", ".join(str(int(v)) for v in filter_werte) or "NULL")
        rows = abfrage(cur, "SELECT {} FROM {}.{}{} ORDER BY {}".format(
            ", ".join('"{}"'.format(c) for c in cols), schema, tabelle, where,
            ", ".join('"{}"'.format(c) for c in ids)), params)
        daten = [[wert_aus_db(v) for v in r] for r in rows]
        if key:
            pos = [cols.index(k) for k in key]
            gesehen = {}
            for z in daten:
                k = repr([z[p] for p in pos])
                gesehen[k] = gesehen.get(k, 0) + 1
            doppelt = [k for k, n in gesehen.items() if n > 1]
            if doppelt:
                hinweise.append("{}: fachlicher Schlüssel {} nicht eindeutig ({} Werte), Kontrolle nur über die ID".format(
                    tabelle, key, len(doppelt)))
                key = None
        datei = "meta/{}/{}.ndjson".format(teil, tabelle)
        h = schreiber.text(datei, ndjson(daten))
        eintraege.append({"tabelle": tabelle, "spalten": cols, "id": ids, "schluessel": key,
                          "filter": filt, "zeilen": len(daten), "datei": datei, "hash": h})
    return {"schema": schema, "tabellen": eintraege, "hinweise": hinweise}


def job_ids_aus_meta(cur, schema, job_namen=None):
    """IDs der Jobs (alle oder nach job_name-Mustern mit LIKE)."""
    if not job_namen:
        return [int(r[0]) for r in abfrage(cur, "SELECT etl_job_id FROM {}.META_ETL_JOB ORDER BY 1".format(schema))]
    bed = " OR ".join("job_name LIKE ?" for _ in job_namen)
    return [int(r[0]) for r in abfrage(
        cur, "SELECT etl_job_id FROM {}.META_ETL_JOB WHERE {} ORDER BY 1".format(schema, bed), list(job_namen))]


# ---------------------------------------------------------------------------
# Dateien (Step-Parameter, SQL-Templates, Dashboards)
# ---------------------------------------------------------------------------
def export_dateien(schreiber, teil, bereich, quelle, ordner=None):
    """Alle Dateien unter quelle (oder nur in den Unterordnern ordner)."""
    quelle = Path(quelle)
    if not quelle.is_dir():
        raise FileNotFoundError("Ordner fehlt: {}".format(quelle))
    dateien = {}
    for p in sorted(quelle.rglob("*")):
        if not p.is_file() or any(a in p.parts or p.name.endswith(a) for a in AUSGESCHLOSSEN):
            continue
        rel = p.relative_to(quelle).as_posix()
        if ordner is not None and rel.split("/", 1)[0] not in ordner:
            continue
        schreiber.datei("dateien/{}/{}/{}".format(teil, bereich, rel), p)
        dateien[rel] = sha256_datei(p)
    return {"bereich": bereich, "ordner": sorted(ordner) if ordner is not None else None, "dateien": dateien}


# ---------------------------------------------------------------------------
# Rechte
# ---------------------------------------------------------------------------
def export_rechte(schreiber, rollen, grants, user_grants, lese_user=()):
    """rollen: [Name]; grants: [SQL]; user_grants: [(User, SQL)];
    lese_user: [{"user", "eltern", "rolle", "spool", "pruef_db"}] - auf dem Ziel angelegt,
    Passwort entsteht dort."""
    import json
    inhalt = {"rollen": list(rollen), "grants": list(grants),
              "user_grants": [list(x) for x in user_grants], "lese_user": list(lese_user)}
    h = schreiber.text("rechte/rechte.json", json.dumps(inhalt, ensure_ascii=False, indent=2))
    return dict(inhalt, datei="rechte/rechte.json", hash=h)


# ---------------------------------------------------------------------------
# Software (daita-studio selbst)
# ---------------------------------------------------------------------------
# Nicht im Software-Teil: Standort-Konfiguration (legt der Betreiber einmal an)
# und Inhalte, die mit anderen Teilen kommen.
SOFTWARE_AUSSCHLUSS = [
    "cfg/config.yml", "cfg/environments.yml", "cfg/database.yml", "cfg/connections.json",
    "frontend/config.js", "etl/jobs/", "etl/sql_templates/", "tools/meta_transfer/meta_export/",
]
# Zielplattform der Wheels (docs/AIRGAP_DEPLOYMENT_PROMPT.md: SLES 15 SP6, Python 3.11)
WHEEL_PYTHON = "3.11"
WHEEL_PLATTFORMEN = ["manylinux_2_17_x86_64", "manylinux2014_x86_64", "manylinux_2_28_x86_64"]


def export_software(schreiber, studio_root, arbeitsordner, mit_wheels=True, uv="uv", pip=None):
    """Versionierte Dateien von daita-studio (git ls-files) plus gepinnte
    Abhängigkeiten und - mit mit_wheels - die Wheels für die Zielplattform.

    arbeitsordner: leerer Ordner für Zwischenergebnisse (Wheels-Download).
    pip: Python-Interpreter mit pip für den Download (Standard: sys.executable).
    """
    import sys
    studio_root = Path(studio_root)
    arbeitsordner = Path(arbeitsordner)
    arbeitsordner.mkdir(parents=True, exist_ok=True)
    namen = subprocess.check_output(["git", "-C", str(studio_root), "ls-files"]).decode("utf-8").splitlines()
    dateien = {}
    for rel in sorted(namen):
        if any(rel == a or (a.endswith("/") and rel.startswith(a)) for a in SOFTWARE_AUSSCHLUSS):
            continue
        p = studio_root / rel
        if p.is_file():
            schreiber.datei("software/code/" + rel, p)
            dateien[rel] = sha256_datei(p)

    req = arbeitsordner / "requirements.lock.txt"
    subprocess.check_call([uv, "pip", "compile", str(studio_root / "pyproject.toml"), "--quiet",
                           "--python-version", WHEEL_PYTHON, "--python-platform", "x86_64-manylinux_2_17",
                           "--no-header", "--no-annotate", "-o", str(req)])
    req_hash = schreiber.datei("software/requirements.lock.txt", req)
    wheels = []
    if mit_wheels:
        wdir = arbeitsordner / "wheels"
        cmd = [pip or sys.executable, "-m", "pip", "download", "-q", "-r", str(req), "-d", str(wdir),
               "--only-binary=:all:", "--python-version", WHEEL_PYTHON.replace(".", ""), "--implementation", "cp",
               "--abi", "cp" + WHEEL_PYTHON.replace(".", "")]
        for pl in WHEEL_PLATTFORMEN:
            cmd += ["--platform", pl]
        subprocess.check_call(cmd)
        for w in sorted(wdir.glob("*.whl")):
            schreiber.datei("software/wheels/" + w.name, w)
            wheels.append(w.name)
    return {"dateien": dateien, "ausschluss": SOFTWARE_AUSSCHLUSS, "requirements_hash": req_hash,
            "wheels": wheels, "python": WHEEL_PYTHON}
