#!/usr/bin/env python3
"""
Abnahmeprüfung eines eingespielten Pakets auf dem Ziel (nur lesend).

Läuft am Ende von einspielen.py --ausfuehren und lässt sich einzeln aufrufen:
    python abnahme.py <paket.zip>

Prüft (Konzept daita-studio/docs/PAKET_DEPLOYMENT_KONZEPT.md, Abschnitt 10):
  - Objekte der Strukturen vorhanden, Struktur wie im Paket
  - Views abfragbar (EXPLAIN: Gültigkeit und Leserecht, ohne die View zu rechnen)
  - Voraussetzungen (z. B. RAW-Tabellen) vorhanden
  - Rollen und Lese-User vorhanden
  - Jobs vollständig: Steps, Step-Dateien, SQL-Templates, Quell-/Zieltabellen
  - Tagessimulation: Layer je aktivem Job auflösbar, Abhängigkeiten ohne Zyklus
  - Dashboards: alle Platzhalter für die Zielumgebung auflösbar
Der Bericht (Text, keine Fachdaten) geht als Rückmeldung an die Entwicklung.
"""
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export import abfrage, objekte, show  # noqa: E402
from paket_format import Paket, norm, sha256_datei, tabelle_zerlegen, view_signatur  # noqa: E402
from studio_umgebung import Studio  # noqa: E402

PLATZHALTER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([A-Za-z0-9_-]+))?\}")


class Bericht:
    def __init__(self, log):
        self.log = log
        self.fehler = 0
        self.zeilen = []

    def ok(self, text):
        self._z("OK      " + text)

    def fehl(self, text):
        self.fehler += 1
        self._z("FEHLER  " + text)

    def hinweis(self, text):
        self._z("HINWEIS " + text)

    def _z(self, text):
        self.zeilen.append(text)
        self.log("  " + text)


def _view_lesen(cur, db, name):
    """None = abfragbar, sonst Fehlertext; 'RECHT' = dem User fehlt das Leserecht (Error 3523).
    EXPLAIN statt SELECT … SAMPLE 0: SAMPLE wirkt erst auf das fertige Ergebnis, die View
    würde vollständig gerechnet (auf INT mit echten Daten Minuten je View)."""
    try:
        cur.execute('EXPLAIN SELECT * FROM {}."{}"'.format(db, name))
        cur.fetchall()
        return None
    except Exception as e:  # noqa: BLE001
        text = str(e)
        return "RECHT" if "[Error 3523]" in text else text.splitlines()[0][text.find("[Error"):][:150]


def _strukturen(b, paket, cur, teil, lese_cur=None, lese_user=None):
    inhalt = paket.manifest["inhalt"][teil]
    ist = {db: objekte(cur, db) for db in inhalt["datenbanken"]}
    fehlt, anders, views_ok, ohne_recht = [], [], 0, {}
    for o in inhalt["objekte"]:
        db, name = o["db"], o["name"]
        if ist[db].get(name) is None:
            fehlt.append("{}.{}".format(db, name))
            continue
        ddl = paket.text("{}/{}/{}.sql".format(teil, db, name))
        if o["art"] == "V":
            if view_signatur(show(cur, db, name, "VIEW")) != view_signatur(ddl):
                anders.append("{}.{}".format(db, name))
            f = _view_lesen(cur, db, name)
            if f == "RECHT" and lese_cur is not None and db.upper().endswith("_ACCESS"):
                f = _view_lesen(lese_cur, db, name)
                f = "{} (mit Lese-User {})".format(f, lese_user) if f else None
            if f is None:
                views_ok += 1
            elif f == "RECHT":
                ohne_recht[db] = ohne_recht.get(db, 0) + 1
            else:
                b.fehl("View {}.{} nicht abfragbar: {}".format(db, name, f))
        else:
            soll, i = tabelle_zerlegen(ddl), tabelle_zerlegen(show(cur, db, name, "TABLE"))
            sd = {n: norm(d) for n, d in soll["spalten"]}
            idd = {n: norm(d) for n, d in i["spalten"]}
            if any(idd.get(n) != d for n, d in sd.items()) or soll["index"] != i["index"] or soll["art"] != i["art"]:
                anders.append("{}.{}".format(db, name))
    n = len(inhalt["objekte"])
    (b.fehl if fehlt else b.ok)("{}: {} von {} Objekten vorhanden{}".format(
        teil, n - len(fehlt), n, " - fehlt: " + ", ".join(fehlt[:10]) if fehlt else ""))
    (b.fehl if anders else b.ok)("{}: Struktur wie im Paket{}".format(
        teil, " - abweichend: " + ", ".join(anders[:10]) if anders else ""))
    nv = sum(1 for o in inhalt["objekte"] if o["art"] == "V")
    if nv:
        b.ok("{}: {} von {} Views abfragbar{}".format(teil, views_ok, nv, " (mit Lese-User {} für *_ACCESS)".format(
            lese_user) if lese_cur is not None else ""))
    for db, n in ohne_recht.items():
        b.hinweis("{}: {} Views in {} nicht prüfbar - dem Einspiel-User fehlt dort das Leserecht (Rollenkonzept)".format(
            teil, n, db))
    for v in inhalt.get("voraussetzungen", []):
        if not abfrage(cur, "SELECT 1 FROM dbc.TablesV WHERE DatabaseName = ? AND TableName = ?", (v["db"], v["name"])):
            b.fehl("Voraussetzung {}.{} fehlt".format(v["db"], v["name"]))
    if inhalt.get("voraussetzungen"):
        b.ok("{}: {} Voraussetzungen geprüft".format(teil, len(inhalt["voraussetzungen"])))


def _rechte(b, paket, cur):
    r = paket.manifest["inhalt"]["rechte"]
    rollen = {x[0].upper() for x in abfrage(cur, "SELECT TRIM(RoleName) FROM dbc.RoleInfoV")}
    fehlt = [x for x in r["rollen"] if x.upper() not in rollen]
    (b.fehl if fehlt else b.ok)("rechte: {} von {} Rollen vorhanden{}".format(
        len(r["rollen"]) - len(fehlt), len(r["rollen"]), " - fehlt: " + ", ".join(fehlt) if fehlt else ""))
    for lu in r.get("lese_user", []):
        if abfrage(cur, "SELECT 1 FROM dbc.RoleMembersV WHERE RoleName = ? AND Grantee = ?", (lu["rolle"], lu["user"])):
            b.ok("rechte: Lese-User {} mit Rolle {}".format(lu["user"], lu["rolle"]))
        else:
            b.fehl("rechte: Lese-User {} fehlt oder hat Rolle {} nicht".format(lu["user"], lu["rolle"]))


def _jobs(b, paket, studio, env_id, cur, schema):
    inhalt = paket.manifest["inhalt"]["jobs"]
    tab = {e["tabelle"]: e for e in inhalt.get("meta", {}).get("tabellen", [])}
    if "META_ETL_JOB" not in tab:
        return
    jobs = paket.zeilen(tab["META_ETL_JOB"]["datei"])
    jc = tab["META_ETL_JOB"]["spalten"]
    jid = jc.index(tab["META_ETL_JOB"]["id"][0])
    ids = [z[jid] for z in jobs]
    steps = paket.zeilen(tab["META_ETL_JOB_STEP"]["datei"]) if "META_ETL_JOB_STEP" in tab else []
    soll_steps = {}
    sc = tab["META_ETL_JOB_STEP"]["spalten"] if steps else []
    for z in steps:
        soll_steps[z[sc.index("etl_job_id")]] = soll_steps.get(z[sc.index("etl_job_id")], 0) + 1
    ist_steps = dict(abfrage(cur, "SELECT etl_job_id, COUNT(*) FROM {}.META_ETL_JOB_STEP GROUP BY 1".format(schema)))
    ist_jobs = {r[0] for r in abfrage(cur, "SELECT etl_job_id FROM {}.META_ETL_JOB".format(schema))}
    fehlt = [i for i in ids if i not in ist_jobs]
    falsch = [i for i in ids if ist_steps.get(i, 0) != soll_steps.get(i, 0)]
    (b.fehl if fehlt else b.ok)("jobs: {} von {} Jobs in META".format(len(ids) - len(fehlt), len(ids)))
    (b.fehl if falsch else b.ok)("jobs: Steps je Job wie im Paket{}".format(
        " - abweichend bei Job " + ", ".join(map(str, falsch[:10])) if falsch else ""))

    # SQL-Templates der Steps
    basis = studio.sql_templates()
    pfade = {r[0].strip() for r in abfrage(
        cur, "SELECT DISTINCT sql_template_path FROM {}.META_ETL_JOB_STEP WHERE sql_template_path IS NOT NULL "
             "AND is_active = 'Y'".format(schema)) if r[0] and r[0].strip()}
    ohne = sorted(p for p in pfade if not (basis / p).exists())
    (b.fehl if ohne else b.ok)("jobs: {} SQL-Templates der aktiven Steps vorhanden in {}{}".format(
        len(pfade) - len(ohne), basis, " - fehlt: " + ", ".join(ohne[:10]) if ohne else ""))

    # Step-Dateien
    for e in inhalt.get("dateien", []):
        if e["bereich"] != "etl_jobs":
            continue
        ziel = studio.etl_jobs(env_id)
        schlecht = [rel for rel in e["dateien"] if not (ziel / rel).exists() or
                    sha256_datei(ziel / rel) != paket.summen["dateien/jobs/etl_jobs/" + rel]]
        (b.fehl if schlecht else b.ok)("jobs: {} Step-Dateien in {} wie im Paket{}".format(
            len(e["dateien"]) - len(schlecht), ziel, " - abweichend: " + ", ".join(schlecht[:5]) if schlecht else ""))

    # Quell- und Zieltabellen physisch vorhanden
    rows = abfrage(cur, "SELECT j.etl_job_id, TRIM(d.database_name), TRIM(t.table_name) FROM {0}.META_ETL_JOB j "
                        "JOIN {0}.META_TABLE t ON t.table_id IN (j.source_table_id, j.target_table_id) "
                        "JOIN {0}.META_DATABASE d ON d.database_id = t.database_id "
                        "WHERE j.is_active = 'Y'".format(schema))
    phys = {}
    for _, db, name in rows:
        if db not in phys:
            phys[db] = {k.upper() for k in objekte(cur, db)}
    fehlend = sorted({"{}.{}".format(db, n) for _, db, n in rows if n.upper() not in phys[db]})
    (b.fehl if fehlend else b.ok)("jobs: Quell- und Zieltabellen der aktiven Jobs vorhanden{}".format(
        " - fehlt: " + ", ".join(fehlend[:10]) if fehlend else ""))

    # Tagessimulation: Layer je Job, Abhängigkeiten ohne Zyklus
    ohne_layer = [r[0] for r in abfrage(
        cur, "SELECT j.etl_job_id FROM {0}.META_ETL_JOB j LEFT JOIN {0}.META_TABLE t ON t.table_id = j.target_table_id "
             "LEFT JOIN {0}.META_DATABASE d ON d.database_id = t.database_id "
             "LEFT JOIN {0}.META_LAYER l ON l.layer_id = d.layer_id "
             "WHERE j.is_active = 'Y' AND l.layer_id IS NULL".format(schema))]
    (b.fehl if ohne_layer else b.ok)("Tagessimulation: Layer für alle aktiven Jobs auflösbar{}".format(
        " - nicht bei Job " + ", ".join(map(str, ohne_layer[:10])) if ohne_layer else ""))
    kanten = abfrage(cur, "SELECT parent_job_id, child_job_id FROM {}.META_ETL_DEPENDENCY".format(schema))
    nach = {}
    for p, c in kanten:
        nach.setdefault(p, []).append(c)
    farbe, zyklus = {}, []

    def besuch(k):
        farbe[k] = 1
        for c in nach.get(k, []):
            if farbe.get(c) == 1:
                zyklus.append((k, c))
            elif not farbe.get(c):
                besuch(c)
        farbe[k] = 2
    for k in list(nach):
        if not farbe.get(k):
            besuch(k)
    (b.fehl if zyklus else b.ok)("Tagessimulation: Abhängigkeiten ohne Zyklus ({} Kanten)".format(len(kanten)))


def _dashboards(b, paket, studio, env_id, cur, schema):
    ordner = studio.dashboards(env_id)
    werte = {"META_SCHEMA"}
    for code, db in abfrage(cur, "SELECT l.layer_code, d.database_name FROM {0}.META_LAYER l "
                                 "JOIN {0}.META_DATABASE d ON d.layer_id = l.layer_id".format(schema)):
        if code and db:
            werte.add("DB_" + str(code).strip().upper())
    u = ordner / "umgebungen.yml"
    if u.exists():
        v = (yaml.safe_load(u.read_text(encoding="utf-8")) or {}).get("variablen") or {}
        if env_id not in v:
            b.fehl("dashboards: {} hat keinen Abschnitt für die Umgebung {}".format(u, env_id))
        werte |= set((v.get("default") or {}).keys()) | set((v.get(env_id) or {}).keys())
    offen = {}
    for p in sorted(ordner.rglob("*")):
        if p.suffix not in (".sql", ".yml") or p.name == "umgebungen.yml" or not p.is_file():
            continue
        for m in PLATZHALTER.finditer(p.read_text(encoding="utf-8")):
            if m.group(2) is None and m.group(1) not in werte:
                offen.setdefault(m.group(1), set()).add(p.relative_to(ordner).as_posix())
    (b.fehl if offen else b.ok)("dashboards: alle Platzhalter in {} für {} auflösbar{}".format(
        ordner, env_id, " - offen: " + "; ".join("{} ({})".format(k, ", ".join(sorted(v)[:3])) for k, v in offen.items())
        if offen else ""))


def pruefen(paket, studio, env_id, cur, log, ordner=None):
    """Führt alle Prüfungen der Teile im Paket aus; gibt die Anzahl Fehler zurück."""
    b = Bericht(log)
    schema = studio.umgebung(env_id)["schema"]
    teile = paket.teile()
    lese_conn = lese_cur = lese_user = None
    dash = studio.umgebung(env_id).get("dashboards_db")
    if dash and dash.get("user") and dash.get("password"):
        import teradatasql
        try:
            lese_conn = teradatasql.connect(host=dash.get("host") or studio.umgebung(env_id)["host"],
                                            user=dash["user"], password=dash["password"])
            lese_cur, lese_user = lese_conn.cursor(), dash["user"]
        except Exception as e:  # noqa: BLE001
            b.fehl("Anmeldung des Lese-Users {} (dashboards_db) fehlgeschlagen: {}".format(dash["user"], str(e).splitlines()[0][:150]))
    for teil in ("metaschema", "strukturen"):
        if teil in teile:
            _strukturen(b, paket, cur, teil, lese_cur, lese_user)
    if lese_conn is not None:
        lese_conn.close()
    if "rechte" in teile:
        _rechte(b, paket, cur)
    if "jobs" in teile:
        _jobs(b, paket, studio, env_id, cur, schema)
    if "vorlagen" in teile:
        for e in paket.manifest["inhalt"]["vorlagen"].get("dateien", []):
            basis = studio.sql_templates()
            schlecht = [r for r in e["dateien"] if not (basis / r).exists() or
                        sha256_datei(basis / r) != paket.summen["dateien/vorlagen/sql_templates/" + r]]
            (b.fehl if schlecht else b.ok)("vorlagen: {} SQL-Template-Dateien wie im Paket{}".format(
                len(e["dateien"]) - len(schlecht), " - abweichend: " + ", ".join(schlecht[:5]) if schlecht else ""))
    if "dashboards" in teile:
        _dashboards(b, paket, studio, env_id, cur, schema)
    log("  Abnahme: {}".format("OK" if b.fehler == 0 else "{} Fehler".format(b.fehler)))
    if ordner:
        m = paket.manifest
        kopf = ["Abnahmebericht {}".format(datetime.now().strftime("%Y-%m-%d %H:%M")),
                "Paket {}  Inhalt {}  Version {}".format(paket.pfad.name, m["inhalt_hash"], m["version"].get("bezeichnung")),
                "Ziel {}  Umgebung {}  Meta-Schema {}".format(m["ziel"]["umgebung"], env_id, schema),
                "Ergebnis: {}".format("OK" if b.fehler == 0 else "{} Fehler".format(b.fehler)), ""]
        (Path(ordner) / "abnahmebericht.txt").write_text("\n".join(kopf + b.zeilen) + "\n", encoding="utf-8")
        log("  Bericht: {}".format(Path(ordner) / "abnahmebericht.txt"))
    return b.fehler


def main():
    import argparse
    from einspielen import PROTOKOLL, ziel_bestimmen
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paket")
    args = ap.parse_args()
    paket = Paket(args.paket)
    studio = Studio()
    env_id, _ = ziel_bestimmen(studio, paket.manifest)
    ordner = studio.root / PROTOKOLL / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_abnahme")
    ordner.mkdir(parents=True, exist_ok=True)
    conn = studio.verbinden(env_id)
    fehler = pruefen(paket, studio, env_id, conn.cursor(), print, ordner)
    conn.close()
    sys.exit(1 if fehler else 0)


if __name__ == "__main__":
    main()
