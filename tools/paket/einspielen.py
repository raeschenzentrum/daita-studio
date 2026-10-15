#!/usr/bin/env python3
"""
Paket auf dem Zielserver einspielen.

Vergleicht den Soll-Stand im Paket mit dem Ist-Stand des Ziels, zeigt den
Plan und spielt mit --ausfuehren nur die Unterschiede ein. Konzept:
daita-studio/docs/PAKET_DEPLOYMENT_KONZEPT.md

Zielumgebung (env_id, Meta-Schema) und Umfang kommen aus dem Manifest, die
Zugangsdaten aus cfg/environments.yml dieser daita-studio-Installation
(ohne die Datei: Umgebung "default" aus cfg/database.yml). Hat die Umgebung
einen Eintrag einspielen_db (user, password, optional host), spielt der
Einspieler mit diesem User ein - für Rollen, GRANTs und DDL braucht es meist
mehr Rechte als der Betriebs-User von daita-studio hat.

Je Lauf entsteht ein Protokollordner <PROTOKOLL>/<lauf-id>/ mit Log, Plan,
Sicherungen (Vorher-Stand) und ruecknahme.json. Ausgeführte Läufe stehen
zusätzlich in <Meta-Schema>.META_DEPLOY.

Aufruf (im Ordner tools/paket der daita-studio-Installation, mit deren venv):
    python einspielen.py <paket.zip>                    # Plan (Dry-Run)
    python einspielen.py <paket.zip> --ausfuehren       # einspielen + Abnahme
    python einspielen.py <paket.zip> --teil jobs        # nur einen Teil
    python einspielen.py --zuruecknehmen <lauf-id>      # Plan der Rücknahme
    python einspielen.py --zuruecknehmen <lauf-id> --ausfuehren

Optionen mit Wirkung auf Daten:
    --loeschen    Objekte, Zeilen und Dateien im Umfang, die nicht mehr im
                  Paket sind, entfernen (sonst nur Hinweis)
    --leere-neu   geänderte, aber LEERE Tabellen per DROP + CREATE neu anlegen
Befüllte Tabellen werden nie geleert; Änderungen daran brauchen eine Migration.

Python 3.6 kompatibel; braucht teradatasql und PyYAML (venv von daita-studio).
"""
import argparse
import getpass
import json
import os
import secrets
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import abnahme  # noqa: E402
from export import abfrage, objekte, show, spalten, spalten_signatur  # noqa: E402
from meta_modell import META_DEPLOY_DDL  # noqa: E402
from paket_format import (Paket, PaketFehler, norm, sha256_datei, tabelle_zerlegen,  # noqa: E402
                          view_als_replace, view_signatur, wert_aus_db, wert_fuer_db)
from studio_umgebung import Studio  # noqa: E402

# ============================================================================
# DEF-Block: einzige Anpassstelle
# ============================================================================

# Protokollordner, relativ zum daita-studio-Root (in .gitignore)
PROTOKOLL = "log/paket"
# Zeilen je executemany
BATCH = 500
# uv für die Offline-Installation der Wheels (Teil software); auf dem Ziel liegt
# uv z. B. im ~/.local/bin des Betriebs-Users - dann hier den Aufruf anpassen
UV = "uv"
# Ordner der Installation, in denen Dateien "nur im Ziel" gesucht werden (Teil software)
SOFTWARE_PRUEFORDNER = ["backend", "frontend", "bin", "tools/paket"]

# ============================================================================


class Lauf:
    """Zustand eines Einspiel-Laufs: Verbindung, Ziel, Protokoll, Plan."""

    def __init__(self, args, studio, lauf_id):
        self.args = args
        self.studio = studio
        self.lauf_id = lauf_id
        self.ordner = studio.root / PROTOKOLL / lauf_id
        self.ordner.mkdir(parents=True, exist_ok=True)
        self._log = open(str(self.ordner / "einspielen.log"), "a", encoding="utf-8")
        self.konflikte = []
        self.hinweise = []
        self.ruecknahme = []
        self.geplante_spalten = {}  # Tabelle (Meta-Schema) -> Spalten, die metaschema anlegt

    def log(self, text=""):
        print(text)
        self._log.write(text + "\n")
        self._log.flush()

    def konflikt(self, text):
        self.konflikte.append(text)
        self.log("  KONFLIKT " + text)

    def hinweis(self, text):
        self.hinweise.append(text)
        self.log("  HINWEIS  " + text)

    def ruecknahme_merken(self, eintrag):
        self.ruecknahme.append(eintrag)
        (self.ordner / "ruecknahme.json").write_text(
            json.dumps(self.ruecknahme, ensure_ascii=False, indent=2), encoding="utf-8")


def ausfuehren_sql(lauf, sql):
    lauf.log("    SQL " + " ".join(sql.split())[:200])
    lauf.cur.execute(sql)


# ===========================================================================
# Strukturen (Teile "metaschema" und "strukturen")
# ===========================================================================
def _zeilen(cur, db, name):
    return abfrage(cur, 'SELECT COUNT(*) FROM {}."{}"'.format(db, name))[0][0]


def _spalten_vergleich(soll, ist):
    """-> (alter_sql_teile, migration_gruende, nur_ziel_spalten)."""
    s, i = dict(soll["spalten"]), dict(ist["spalten"])
    alter, gruende = [], []
    for name, d in soll["spalten"]:
        if name not in i:
            alter.append(("neu", name, d))
        elif norm(d) != norm(i[name]):
            import re
            a = re.match(r"VARCHAR\((\d+)\)(.*)$", norm(d))
            b = re.match(r"VARCHAR\((\d+)\)(.*)$", norm(i[name]))
            if a and b and a.group(2) == b.group(2) and int(a.group(1)) > int(b.group(1)):
                alter.append(("laenger", name, d))
            else:
                gruende.append("Spalte {}: {} -> {}".format(name, i[name], d))
    if soll["art"] != ist["art"]:
        gruende.append("Tabellenart {} -> {}".format(ist["art"], soll["art"]))
    if soll["index"] != ist["index"]:
        gruende.append("Index {} -> {}".format(ist["index"], soll["index"]))
    if sorted(soll["constraints"]) != sorted(ist["constraints"]):
        gruende.append("Constraints geändert")
    return alter, gruende, [n for n in i if n not in s]


def plan_strukturen(lauf, teil):
    paket, cur = lauf.paket, lauf.cur
    inhalt = paket.manifest["inhalt"][teil]
    plan = {"teil": teil, "tabellen": [], "views": [], "loeschen": [], "startdaten": []}
    lauf.log("\n== {}: {}".format(teil, ", ".join(inhalt["datenbanken"])))
    vorhandene_dbs = {r[0].upper() for r in abfrage(cur, "SELECT TRIM(DatabaseName) FROM dbc.DatabasesV")}
    ist = {}
    for db in inhalt["datenbanken"]:
        if db.upper() not in vorhandene_dbs:
            lauf.konflikt("Datenbank {} fehlt auf dem Ziel (anlegen mit datenbanken_sem.py)".format(db))
            ist[db] = {}
        else:
            ist[db] = objekte(cur, db)

    zaehler = {}
    for o in inhalt["objekte"]:
        db, name, art = o["db"], o["name"], o["art"]
        ddl = paket.text("{}/{}/{}.sql".format(teil, db, name))
        ist_art = ist[db].get(name)
        if art in ("T", "O"):
            soll = tabelle_zerlegen(ddl)
            if teil == "metaschema":
                lauf.geplante_spalten[name.upper()] = [n for n, _ in soll["spalten"]]
            if ist_art is None:
                aktion = {"aktion": "CREATE TABLE", "db": db, "name": name, "ddl": ddl}
            elif ist_art not in ("T", "O"):
                lauf.konflikt("{}.{} ist auf dem Ziel kein Tabelle (TableKind {})".format(db, name, ist_art))
                continue
            else:
                ist_ddl = tabelle_zerlegen(show(cur, db, name, "TABLE"))
                alter, gruende, nur_ziel = _spalten_vergleich(soll, ist_ddl)
                if nur_ziel:
                    lauf.hinweis("{}.{}: Spalten nur im Ziel (bleiben): {}".format(db, name, ", ".join(nur_ziel)))
                if not alter and not gruende:
                    zaehler["gleich"] = zaehler.get("gleich", 0) + 1
                    continue
                n = _zeilen(cur, db, name)
                if gruende:
                    if n == 0 and lauf.args.leere_neu:
                        aktion = {"aktion": "DROP + CREATE (leer)", "db": db, "name": name, "ddl": ddl,
                                  "gruende": gruende}
                    else:
                        lauf.konflikt("{}.{} ({} Zeilen) braucht eine Migration: {}{}".format(
                            db, name, n, "; ".join(gruende),
                            " - leer: mit --leere-neu neu anlegen" if n == 0 else ""))
                        continue
                else:
                    sqls = []
                    for was, sp, d in alter:
                        if was == "neu" and n > 0 and "NOT NULL" in norm(d) and "DEFAULT" not in norm(d):
                            lauf.konflikt("{}.{}: neue Spalte {} ist NOT NULL ohne DEFAULT, Tabelle hat {} Zeilen "
                                          "- Migration nötig".format(db, name, sp, n))
                            sqls = None
                            break
                        sqls.append(('ALTER TABLE {}."{}" ADD "{}" {}'.format(db, name, sp, d), was, sp))
                    if sqls is None:
                        continue
                    aktion = {"aktion": "ALTER TABLE", "db": db, "name": name, "sqls": sqls, "zeilen": n}
            plan["tabellen"].append(aktion)
        else:
            if ist_art is not None and ist_art != "V":
                lauf.konflikt("{}.{} ist auf dem Ziel keine View (TableKind {})".format(db, name, ist_art))
                continue
            alt = show(cur, db, name, "VIEW") if ist_art == "V" else None
            if alt is not None and view_signatur(alt) == view_signatur(ddl):
                zaehler["gleich"] = zaehler.get("gleich", 0) + 1
                continue
            plan["views"].append({"aktion": "REPLACE VIEW" if alt else "CREATE VIEW", "db": db, "name": name,
                                  "ddl": view_als_replace(ddl), "alt": alt})

    soll_namen = {(o["db"].upper(), o["name"].upper()) for o in inhalt["objekte"]}
    auslassen = set(inhalt.get("auslassen", []))
    for db, objs in ist.items():
        for name, art in objs.items():
            if (db.upper(), name.upper()) in soll_namen or name.upper() in auslassen:
                continue
            if teil == "metaschema":
                continue  # Tabellen nur im Ziel-Meta-Schema (z. B. META_DEPLOY) bleiben immer
            plan["loeschen"].append({"db": db, "name": name, "art": art})

    for v in inhalt.get("voraussetzungen", []):
        db, name = v["db"], v["name"]
        if not abfrage(cur, "SELECT 1 FROM dbc.TablesV WHERE DatabaseName = ? AND TableName = ?", (db, name)):
            lauf.konflikt("Voraussetzung {}.{} fehlt auf dem Ziel".format(db, name))
            continue
        ist_sig = spalten_signatur(cur, db, name)
        if ist_sig != v["spalten"]:
            fehlt = [s for s in v["spalten"] if s not in ist_sig]
            lauf.hinweis("Voraussetzung {}.{}: Spalten weichen von der Entwicklung ab ({} Unterschiede, z. B. {})".format(
                db, name, len(fehlt) or len(ist_sig), (fehlt or ist_sig)[:2]))

    for s in inhalt.get("startdaten", []):
        zeilen = paket.zeilen(s["datei"])
        plan["startdaten"].append({"eintrag": s, "zeilen": zeilen})

    # Anzeige
    for t in plan["tabellen"]:
        lauf.log("  {:22} {}.{}".format(t["aktion"], t["db"], t["name"]))
        for sql, was, sp in t.get("sqls", []):
            lauf.log("      {} {}: {}".format(was, sp, sql))
        for g in t.get("gruende", []):
            lauf.log("      " + g)
    for v in plan["views"]:
        lauf.log("  {:22} {}.{}".format(v["aktion"], v["db"], v["name"]))
    for l in plan["loeschen"]:
        if lauf.args.loeschen:
            lauf.log("  {:22} {}.{} ({})".format("ENTFERNEN", l["db"], l["name"], l["art"]))
        else:
            lauf.hinweis("{}.{} ({}) nur im Ziel - bleibt (entfernen mit --loeschen)".format(l["db"], l["name"], l["art"]))
    for s in plan["startdaten"]:
        lauf.log("  {:22} {}.{}: {} Zeilen im Paket (eingefügt werden fehlende Schlüssel)".format(
            "STARTDATEN", s["eintrag"]["db"], s["eintrag"]["tabelle"], len(s["zeilen"])))
    lauf.log("  unverändert: {} Objekte; Tabellen: {} Aktionen, Views: {}, Voraussetzungen geprüft: {}".format(
        zaehler.get("gleich", 0), len(plan["tabellen"]), len(plan["views"]), len(inhalt.get("voraussetzungen", []))))
    return plan


def ausfuehren_strukturen(lauf, plan):
    cur = lauf.cur
    for t in plan["tabellen"]:
        db, name = t["db"], t["name"]
        if t["aktion"] == "CREATE TABLE":
            ausfuehren_sql(lauf, t["ddl"].strip().rstrip(";"))
            lauf.ruecknahme_merken({"typ": "tabelle_neu", "db": db, "name": name})
        elif t["aktion"].startswith("DROP + CREATE"):
            alt = show(cur, db, name, "TABLE")
            ausfuehren_sql(lauf, 'DROP TABLE {}."{}"'.format(db, name))
            ausfuehren_sql(lauf, t["ddl"].strip().rstrip(";"))
            lauf.ruecknahme_merken({"typ": "tabelle_ersetzt", "db": db, "name": name, "alt": alt})
        else:
            for sql, was, sp in t["sqls"]:
                ausfuehren_sql(lauf, sql)
                lauf.ruecknahme_merken({"typ": "spalte", "db": db, "name": name, "spalte": sp, "was": was})

    offen = list(plan["views"])
    runde = 0
    while offen:
        runde += 1
        weiter, letzte = [], {}
        for v in offen:
            try:
                lauf.cur.execute("DATABASE {}".format(v["db"]))
                lauf.cur.execute(v["ddl"].strip().rstrip(";"))
                lauf.log("    View {}.{}: OK (Runde {})".format(v["db"], v["name"], runde))
                lauf.ruecknahme_merken({"typ": "view", "db": v["db"], "name": v["name"], "alt": v["alt"]})
            except Exception as e:  # noqa: BLE001 - Abhängigkeiten zwischen Views sind nicht bekannt
                letzte[v["name"]] = str(e).splitlines()[0]
                weiter.append(v)
        if len(weiter) == len(offen):
            raise RuntimeError("Views nicht anlegbar: " + "; ".join(
                "{}.{}: {}".format(v["db"], v["name"], letzte[v["name"]]) for v in weiter))
        offen = weiter

    if lauf.args.loeschen:
        for l in plan["loeschen"]:
            if l["art"] == "V":
                alt = show(cur, l["db"], l["name"], "VIEW")
                ausfuehren_sql(lauf, 'DROP VIEW {}."{}"'.format(l["db"], l["name"]))
                lauf.ruecknahme_merken({"typ": "view_entfernt", "db": l["db"], "name": l["name"], "alt": alt})
            elif l["art"] in ("T", "O") and _zeilen(cur, l["db"], l["name"]) == 0:
                alt = show(cur, l["db"], l["name"], "TABLE")
                ausfuehren_sql(lauf, 'DROP TABLE {}."{}"'.format(l["db"], l["name"]))
                lauf.ruecknahme_merken({"typ": "tabelle_entfernt", "db": l["db"], "name": l["name"], "alt": alt})
            else:
                lauf.hinweis("{}.{} hat Daten - wird nicht entfernt".format(l["db"], l["name"]))

    for s in plan["startdaten"]:
        e = s["eintrag"]
        cols = e["spalten"]
        pos = [cols.index(k) for k in e["schluessel"]]
        neu = 0
        for z in s["zeilen"]:
            werte = [wert_fuer_db(v) for v in z]
            bed = " AND ".join('"{}" = ?'.format(k) for k in e["schluessel"])
            if abfrage(cur, 'SELECT 1 FROM {}."{}" WHERE {}'.format(e["db"], e["tabelle"], bed), [werte[p] for p in pos]):
                continue
            cur.execute('INSERT INTO {}."{}" ({}) VALUES ({})'.format(
                e["db"], e["tabelle"], ", ".join('"{}"'.format(c) for c in cols), ", ".join("?" * len(cols))), werte)
            neu += 1
            lauf.ruecknahme_merken({"typ": "startzeile", "db": e["db"], "tabelle": e["tabelle"],
                                    "schluessel": e["schluessel"], "werte": [z[p] for p in pos]})
        lauf.log("    Startdaten {}.{}: {} Zeilen eingefügt".format(e["db"], e["tabelle"], neu))


# ===========================================================================
# META-Zeilen (Teile "jobs" und "vorlagen")
# ===========================================================================
def plan_meta(lauf, teil):
    paket, cur = lauf.paket, lauf.cur
    inhalt = paket.manifest["inhalt"][teil]["meta"]
    schema = lauf.meta_schema
    lauf.log("\n== {}: META-Zeilen in {}".format(teil, schema))
    vorhanden = {k.upper(): k for k in objekte(cur, schema)}
    ident = {(t.upper(), c.upper()): typ.strip() for t, c, typ in abfrage(
        cur, "SELECT TRIM(TableName), TRIM(ColumnName), IdColType FROM dbc.ColumnsV "
             "WHERE DatabaseName = ? AND IdColType IS NOT NULL", (schema,))}
    plan = {"teil": teil, "tabellen": []}
    for e in inhalt["tabellen"]:
        t = e["tabelle"]
        cols = e["spalten"]
        if t.upper() in vorhanden:
            ziel_cols = spalten(cur, schema, t)
        elif t.upper() in lauf.geplante_spalten:
            ziel_cols = []  # legt metaschema an; Tabelle ist dann leer
        else:
            lauf.konflikt("{}.{} fehlt auf dem Ziel".format(schema, t))
            continue
        geplant = {c.upper() for c in ziel_cols} | {c.upper() for c in lauf.geplante_spalten.get(t.upper(), [])}
        fehlend = [c for c in cols if c.upper() not in geplant]
        if fehlend:
            lauf.konflikt("{}.{}: Spalten fehlen auf dem Ziel: {} (Meta-Schema veraltet)".format(schema, t, ", ".join(fehlend)))
            continue
        for c in e["id"]:
            if ident.get((t.upper(), c.upper())) == "GA":
                lauf.konflikt("{}.{}.{} ist GENERATED ALWAYS - für explizite IDs muss sie GENERATED BY DEFAULT sein".format(
                    schema, t, c))

        soll = paket.zeilen(e["datei"])
        ipos = [cols.index(c) for c in e["id"]]
        kpos = [cols.index(c) for c in e["schluessel"]] if e["schluessel"] else None
        ist = []
        if ziel_cols:
            # Spalten, die metaschema erst ergänzt, sind auf dem Ziel noch leer (None)
            da = {c.upper() for c in ziel_cols}
            lesen = ['"{}"'.format(c) if c.upper() in da else "NULL" for c in cols]
            ist = [[wert_aus_db(v) for v in r] for r in abfrage(cur, "SELECT {} FROM {}.{}".format(
                ", ".join(lesen), schema, t))]
        ist_nach_id = {json.dumps([z[p] for p in ipos]): z for z in ist}
        ist_nach_key = {json.dumps([z[p] for p in kpos]): json.dumps([z[p] for p in ipos]) for z in ist} if kpos else {}
        einfuegen, aendern, gleich = [], [], 0
        for z in soll:
            i = json.dumps([z[p] for p in ipos])
            k = json.dumps([z[p] for p in kpos]) if kpos else None
            vorher = ist_nach_id.get(i)
            if kpos:
                if vorher is not None and json.dumps([vorher[p] for p in kpos]) != k:
                    lauf.konflikt("{} ID {}: Ziel hat Schlüssel {}, Paket {}".format(
                        t, i, json.dumps([vorher[p] for p in kpos], ensure_ascii=False), k))
                    continue
                if vorher is None and k in ist_nach_key:
                    lauf.konflikt("{} Schlüssel {}: auf dem Ziel unter ID {}, im Paket unter {}".format(
                        t, k, ist_nach_key[k], i))
                    continue
            if vorher is None:
                einfuegen.append(z)
            else:
                diff = [j for j, c in enumerate(cols) if z[j] != vorher[j]]
                if diff:
                    aendern.append((z, diff, vorher))
                else:
                    gleich += 1
        soll_ids = {json.dumps([z[p] for p in ipos]) for z in soll}
        filt = e.get("filter")
        if filt:
            fpos = cols.index(filt["spalte"])
            werte = set(filt["werte"])
            im_umfang = [z for z in ist if z[fpos] in werte]
        else:
            im_umfang = ist
        nur_ziel = [z for z in im_umfang if json.dumps([z[p] for p in ipos]) not in soll_ids]
        plan["tabellen"].append({"eintrag": e, "einfuegen": einfuegen, "aendern": aendern, "nur_ziel": nur_ziel})
        geaenderte_spalten = sorted({cols[j] for _, d, _ in aendern for j in d})
        lauf.log("  {:32} neu {:>5}  geändert {:>5}  gleich {:>5}  nur im Ziel {:>4}{}".format(
            t, len(einfuegen), len(aendern), gleich, len(nur_ziel),
            "  Spalten: " + ", ".join(geaenderte_spalten[:8]) if geaenderte_spalten else ""))
        if nur_ziel and not lauf.args.loeschen:
            lauf.hinweis("{}: {} Zeilen nur im Ziel - bleiben (entfernen mit --loeschen)".format(t, len(nur_ziel)))
    return plan


def ausfuehren_meta(lauf, plan):
    cur, conn, schema = lauf.cur, lauf.conn, lauf.meta_schema
    sicherung = lauf.ordner / "vorher" / plan["teil"]
    sicherung.mkdir(parents=True, exist_ok=True)
    cur.execute("{fn teradata_nativesql}{fn teradata_autocommit_off}")
    try:
        # Löschen: Kinder vor Eltern
        for p in reversed(plan["tabellen"]):
            if not (lauf.args.loeschen and p["nur_ziel"]):
                continue
            e = p["eintrag"]
            bed = " AND ".join('"{}" = ?'.format(c) for c in e["id"])
            ipos = [e["spalten"].index(c) for c in e["id"]]
            for z in p["nur_ziel"]:
                cur.execute('DELETE FROM {}.{} WHERE {}'.format(schema, e["tabelle"], bed),
                            [wert_fuer_db(z[i]) for i in ipos])
            lauf.log("    {}: {} Zeilen gelöscht".format(e["tabelle"], len(p["nur_ziel"])))
        # Einfügen und Ändern: Eltern vor Kindern
        for p in plan["tabellen"]:
            e = p["eintrag"]
            t, cols = e["tabelle"], e["spalten"]
            ipos = [cols.index(c) for c in e["id"]]
            vorher = [v for _, _, v in p["aendern"]] + (p["nur_ziel"] if lauf.args.loeschen else [])
            if vorher:
                (sicherung / (t + ".ndjson")).write_text(
                    "".join(json.dumps(z, ensure_ascii=False) + "\n" for z in vorher), encoding="utf-8")
            ins = 'INSERT INTO {}.{} ({}) VALUES ({})'.format(
                schema, t, ", ".join('"{}"'.format(c) for c in cols), ", ".join("?" * len(cols)))
            for i in range(0, len(p["einfuegen"]), BATCH):
                cur.executemany(ins, [[wert_fuer_db(v) for v in z] for z in p["einfuegen"][i:i + BATCH]])
            bed = " AND ".join('"{}" = ?'.format(c) for c in e["id"])
            for z, diff, _ in p["aendern"]:
                cur.execute('UPDATE {}.{} SET {} WHERE {}'.format(
                    schema, t, ", ".join('"{}" = ?'.format(cols[j]) for j in diff), bed),
                    [wert_fuer_db(z[j]) for j in diff] + [wert_fuer_db(z[i]) for i in ipos])
            if p["einfuegen"] or p["aendern"]:
                lauf.log("    {}: {} eingefügt, {} geändert".format(t, len(p["einfuegen"]), len(p["aendern"])))
            if p["einfuegen"] or vorher:
                lauf.ruecknahme_merken({
                    "typ": "meta", "schema": schema, "tabelle": t, "spalten": cols, "id": e["id"],
                    "eingefuegt": [[z[i] for i in ipos] for z in p["einfuegen"]],
                    "vorher": str((sicherung / (t + ".ndjson")).relative_to(lauf.ordner)) if vorher else None})
        conn.commit()
    except Exception:
        conn.rollback()
        lauf.ruecknahme = [r for r in lauf.ruecknahme if r.get("typ") != "meta" or r.get("schema") != schema]
        lauf.ruecknahme_merken({"typ": "hinweis", "text": "META-Teil {} zurückgerollt".format(plan["teil"])})
        raise
    finally:
        cur.execute("{fn teradata_nativesql}{fn teradata_autocommit_on}")


# ===========================================================================
# Dateien
# ===========================================================================
def ziel_ordner(lauf, bereich):
    if bereich == "etl_jobs":
        return lauf.studio.etl_jobs(lauf.env_id)
    if bereich == "sql_templates":
        return lauf.studio.sql_templates()
    if bereich == "dashboards":
        return lauf.studio.dashboards(lauf.env_id)
    raise ValueError("unbekannter Dateibereich " + bereich)


def plan_dateien(lauf, teil):
    plaene = []
    for e in lauf.paket.manifest["inhalt"][teil].get("dateien", []):
        ziel = ziel_ordner(lauf, e["bereich"])
        lauf.log("\n== {}: Dateien {} -> {}".format(teil, e["bereich"], ziel))
        neu, geaendert, gleich = [], [], 0
        for rel in sorted(e["dateien"]):
            sha = lauf.paket.summen["dateien/{}/{}/{}".format(teil, e["bereich"], rel)]
            p = ziel / rel
            if not p.exists():
                neu.append(rel)
            elif sha256_datei(p) != sha:
                geaendert.append(rel)
            else:
                gleich += 1
        nur_ziel = []
        if ziel.is_dir():
            for p in sorted(ziel.rglob("*")):
                if not p.is_file() or "__pycache__" in p.parts:
                    continue
                rel = p.relative_to(ziel).as_posix()
                if e["ordner"] is not None and rel.split("/", 1)[0] not in e["ordner"]:
                    continue
                if rel not in e["dateien"]:
                    nur_ziel.append(rel)
        lauf.log("  neu {}  geändert {}  gleich {}  nur im Ziel {}".format(len(neu), len(geaendert), gleich, len(nur_ziel)))
        for rel in geaendert[:20]:
            lauf.log("    geändert: " + rel)
        if nur_ziel and not lauf.args.loeschen:
            lauf.hinweis("{}: {} Dateien nur im Ziel - bleiben (entfernen mit --loeschen), z. B. {}".format(
                e["bereich"], len(nur_ziel), nur_ziel[:3]))
        plaene.append({"eintrag": e, "ziel": ziel, "neu": neu, "geaendert": geaendert, "nur_ziel": nur_ziel,
                       "praefix": "dateien/{}/{}/".format(teil, e["bereich"])})
    return plaene


def ausfuehren_dateien(lauf, plaene):
    for p in plaene:
        e, ziel = p["eintrag"], p["ziel"]
        sich = lauf.ordner / "dateien" / e["bereich"]
        for rel in p["neu"] + p["geaendert"]:
            z = ziel / rel
            backup = None
            if rel in p["geaendert"]:
                backup = sich / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(z), str(backup))
            z.parent.mkdir(parents=True, exist_ok=True)
            z.write_bytes(lauf.paket.bytes(p["praefix"] + rel))
            lauf.ruecknahme_merken({"typ": "datei", "ziel": str(z),
                                    "sicherung": str(backup.relative_to(lauf.ordner)) if backup else None})
        if lauf.args.loeschen:
            for rel in p["nur_ziel"]:
                z = ziel / rel
                backup = sich / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(z), str(backup))
                lauf.ruecknahme_merken({"typ": "datei_entfernt", "ziel": str(z), "sicherung": str(backup.relative_to(lauf.ordner))})
        lauf.log("    {}: {} geschrieben{}".format(e["bereich"], len(p["neu"]) + len(p["geaendert"]),
                                                  ", {} entfernt".format(len(p["nur_ziel"])) if lauf.args.loeschen else ""))


# ===========================================================================
# Software (daita-studio selbst)
# ===========================================================================
MARKE = ".paket_requirements.sha256"


def plan_software(lauf):
    s = lauf.paket.manifest["inhalt"]["software"]
    root = lauf.studio.root
    lauf.log("\n== software: daita-studio in {}".format(root))
    neu, geaendert, gleich = [], [], 0
    for rel in sorted(s["dateien"]):
        p = root / rel
        if not p.exists():
            neu.append(rel)
        elif sha256_datei(p) != lauf.paket.summen["software/code/" + rel]:
            geaendert.append(rel)
        else:
            gleich += 1
    aus = s.get("ausschluss", [])
    nur_ziel = []
    for d in SOFTWARE_PRUEFORDNER:
        for p in sorted((root / d).rglob("*")) if (root / d).is_dir() else []:
            if not p.is_file() or "__pycache__" in p.parts or p.suffix == ".pyc":
                continue
            rel = p.relative_to(root).as_posix()
            if rel not in s["dateien"] and not any(rel == a or (a.endswith("/") and rel.startswith(a)) for a in aus):
                nur_ziel.append(rel)
    lauf.log("  Dateien: neu {}  geändert {}  gleich {}  nur im Ziel {}".format(len(neu), len(geaendert), gleich, len(nur_ziel)))
    for rel in geaendert[:20]:
        lauf.log("    geändert: " + rel)
    if nur_ziel and not lauf.args.loeschen:
        lauf.hinweis("software: {} Dateien nur im Ziel - bleiben (entfernen mit --loeschen), z. B. {}".format(
            len(nur_ziel), nur_ziel[:3]))
    marke = root / MARKE
    ist = marke.read_text(encoding="utf-8").strip() if marke.exists() else None
    installieren = ist != s["requirements_hash"]
    if installieren and not s["wheels"]:
        lauf.konflikt("software: Abhängigkeiten weichen ab (oder unbekannt), das Paket enthält aber keine Wheels")
    lauf.log("  Abhängigkeiten: {}".format(
        "unverändert" if not installieren else "installieren ({} Wheels, Python {}, in {})".format(
            len(s["wheels"]), s["python"], sys.prefix)))
    if geaendert or neu or installieren:
        lauf.hinweis("software: nach dem Einspielen daita-studio neu starten (bin/start.sh)")
    return {"eintrag": {"bereich": "software"}, "ziel": root, "neu": neu, "geaendert": geaendert,
            "nur_ziel": nur_ziel, "praefix": "software/code/", "installieren": installieren}


def ausfuehren_software(lauf, plan):
    ausfuehren_dateien(lauf, [plan])
    if not plan["installieren"]:
        return
    s = lauf.paket.manifest["inhalt"]["software"]
    wdir = lauf.ordner / "wheels"
    wdir.mkdir(exist_ok=True)
    for w in s["wheels"]:
        (wdir / w).write_bytes(lauf.paket.bytes("software/wheels/" + w))
    req = lauf.ordner / "requirements.lock.txt"
    req.write_bytes(lauf.paket.bytes("software/requirements.lock.txt"))
    cmd = [UV, "pip", "install", "--python", sys.executable, "--no-index", "--find-links", str(wdir), "-r", str(req)]
    lauf.log("    " + " ".join(cmd))
    import subprocess
    subprocess.check_call(cmd)
    (lauf.studio.root / MARKE).write_text(s["requirements_hash"] + "\n", encoding="utf-8")
    lauf.ruecknahme_merken({"typ": "hinweis", "text": "Python-Pakete in {} wurden aktualisiert; "
                            "keine automatische Rücknahme".format(sys.prefix)})


# ===========================================================================
# Rechte
# ===========================================================================
def plan_rechte(lauf):
    r = lauf.paket.manifest["inhalt"]["rechte"]
    cur = lauf.cur
    lauf.log("\n== rechte")
    rollen_ist = {x[0].upper() for x in abfrage(cur, "SELECT TRIM(RoleName) FROM dbc.RoleInfoV")}
    user_ist = {x[0].upper() for x in abfrage(cur, "SELECT TRIM(DatabaseName) FROM dbc.DatabasesV")}
    neu_rollen = [x for x in r["rollen"] if x.upper() not in rollen_ist]
    user_grants = []
    for u, sql in r["user_grants"]:
        if u.upper() in user_ist:
            user_grants.append(sql)
        else:
            lauf.hinweis("User {} fehlt auf dem Ziel - übersprungen: {}".format(u, sql))
    lese = []
    for lu in r.get("lese_user", []):
        if lu["user"].upper() in user_ist:
            lauf.log("  Lese-User {}: vorhanden".format(lu["user"]))
        else:
            lese.append(lu)
            lauf.log("  Lese-User {}: anlegen unter {} mit Rolle {} (Passwort entsteht hier)".format(
                lu["user"], lu["eltern"], lu["rolle"]))
    lauf.log("  Rollen neu: {}  vorhanden: {}".format(", ".join(neu_rollen) or "-", len(r["rollen"]) - len(neu_rollen)))
    lauf.log("  GRANT an Rollen und Datenbanken: {} (wiederholbar)  GRANT an User: {}".format(len(r["grants"]), len(user_grants)))
    return {"teil": "rechte", "rollen": neu_rollen, "grants": r["grants"], "user_grants": user_grants, "lese_user": lese}


def ausfuehren_rechte(lauf, plan):
    for rolle in plan["rollen"]:
        ausfuehren_sql(lauf, "CREATE ROLE {}".format(rolle))
    for sql in plan["grants"] + plan["user_grants"]:
        ausfuehren_sql(lauf, sql.rstrip(";"))
    for lu in plan["lese_user"]:
        passwort = "Db" + secrets.token_hex(14)
        lauf.cur.execute('CREATE USER {} FROM {} AS PERM = 0, SPOOL = {}, PASSWORD = "{}"'.format(
            lu["user"], lu["eltern"], int(lu["spool"]), passwort))
        lauf.log("    CREATE USER {} FROM {} (Passwort nicht protokolliert)".format(lu["user"], lu["eltern"]))
        ausfuehren_sql(lauf, "GRANT {} TO {}".format(lu["rolle"], lu["user"]))
        ausfuehren_sql(lauf, "MODIFY USER {} AS DEFAULT ROLE = {}".format(lu["user"], lu["rolle"]))
        secret = lauf.ordner / "lese_user_{}.secret".format(lu["user"])
        secret.write_text("user: {}\npassword: '{}'\n".format(lu["user"], passwort), encoding="utf-8")
        os.chmod(str(secret), 0o600)
        lauf.log("    Zugangsdaten in {} - in cfg/environments.yml unter dashboards_db eintragen, "
                 "danach die Datei löschen".format(secret))


# ===========================================================================
# Rechte des Einspiel-Users prüfen (vor dem Ausführen)
# ===========================================================================
KUERZEL = {"SELECT": "R", "INSERT": "I", "UPDATE": "U", "DELETE": "D", "SHOW": "SH",
           "CREATE TABLE": "CT", "DROP TABLE": "DT", "CREATE VIEW": "CV", "DROP VIEW": "DV",
           "STATISTICS": "ST", "CREATE USER": "CU"}


def _rechte_ist(cur):
    rows = []
    for v in ("dbc.UserRightsV", "dbc.UserRoleRightsV"):
        rows += abfrage(cur, "SELECT TRIM(DatabaseName), TRIM(AccessRight) FROM {} WHERE TableName = 'All'".format(v))
    return {(d.upper(), r.upper()) for d, r in rows}


def _rechte_aus_paket(lauf, user):
    """Rechte, die der Teil rechte desselben Pakets dem Einspiel-User (über Rollen) gibt."""
    import re
    r = lauf.paket.manifest["inhalt"].get("rechte")
    if not r or "rechte" not in lauf.teile:
        return set()
    rollen_rechte = {}
    for sql in r["grants"]:
        m = re.match(r"\s*GRANT\s+(.+?)\s+ON\s+(\S+)\s+TO\s+(\S+?)\s*;?\s*$", sql, re.I)
        if m:
            codes = {KUERZEL.get(x.strip().upper()) for x in m.group(1).split(",")}
            rollen_rechte.setdefault(m.group(3).upper(), set()).update((m.group(2).upper(), c) for c in codes if c)
    erg = set()
    for u, sql in r["user_grants"]:
        m = re.match(r"\s*GRANT\s+(\S+)\s+TO\s+(\S+?)\s*;?\s*$", sql, re.I)
        if m and u.upper() == user.upper():
            erg |= rollen_rechte.get(m.group(1).upper(), set())
    return erg


def rechte_pruefen(lauf, plaene):
    bedarf = {}

    def braucht(db, code, grund):
        bedarf.setdefault((db.upper(), code), grund)
    for teil, plan, _ in plaene:
        if teil in ("metaschema", "strukturen"):
            for t in plan["tabellen"]:
                if t["aktion"] == "CREATE TABLE":
                    braucht(t["db"], "CT", "Tabelle anlegen")
                elif t["aktion"].startswith("DROP"):
                    braucht(t["db"], "DT", "Tabelle neu anlegen")
                    braucht(t["db"], "CT", "Tabelle neu anlegen")
                else:
                    braucht(t["db"], "DT", "ALTER TABLE")
            for v in plan["views"]:
                braucht(v["db"], "DV" if v["alt"] else "CV", "View ersetzen" if v["alt"] else "View anlegen")
            if lauf.args.loeschen:
                for l in plan["loeschen"]:
                    braucht(l["db"], "DV" if l["art"] == "V" else "DT", "Objekt entfernen")
            for s in plan["startdaten"]:
                braucht(s["eintrag"]["db"], "I", "Startdaten")
        elif teil in ("jobs", "vorlagen") and "tabellen" in plan and isinstance(plan, dict):
            for p in plan["tabellen"]:
                if p["einfuegen"]:
                    braucht(lauf.meta_schema, "I", "META-Zeilen einfügen")
                if p["aendern"]:
                    braucht(lauf.meta_schema, "U", "META-Zeilen ändern")
                if p["nur_ziel"] and lauf.args.loeschen:
                    braucht(lauf.meta_schema, "D", "META-Zeilen löschen")
        elif teil == "rechte":
            for lu in plan["lese_user"]:
                braucht(lu["eltern"], "CU", "Lese-User anlegen")
    if not bedarf:
        return
    user = abfrage(lauf.cur, "SELECT USER")[0][0].strip()
    ist = _rechte_ist(lauf.cur) | _rechte_aus_paket(lauf, user)
    fehlt = sorted(k for k in bedarf if k not in ist)
    lauf.log("\n== Rechte des Einspiel-Users {}: {} benötigt, {} fehlen".format(user, len(bedarf), len(fehlt)))
    for db, code in fehlt:
        lauf.konflikt("Recht {} auf {} fehlt dem User {} ({}) - einspielen_db in cfg/environments.yml "
                      "oder Recht vergeben".format(code, db, user, bedarf[(db, code)]))
    if "rechte" in lauf.teile and lauf.paket.manifest["inhalt"]["rechte"]["rollen"]:
        lauf.hinweis("Teil rechte: CREATE ROLE und GRANT ... WITH GRANT OPTION setzen Admin-Rechte des Users {} voraus "
                     "(vorab nicht prüfbar)".format(user))


# ===========================================================================
# Ablauf
# ===========================================================================
def ziel_bestimmen(studio, manifest):
    ziel = manifest["ziel"]
    env_id = ziel["studio_env"]
    if studio.umgebung(env_id) is None:
        if list(studio.umgebungen) == ["default"]:
            env_id = "default"
        else:
            sys.exit("Umgebung {} aus dem Manifest fehlt in {} (vorhanden: {})".format(
                ziel["studio_env"], studio.quelle_umgebungen, ", ".join(studio.umgebungen)))
    schema = studio.umgebung(env_id).get("schema", "")
    if schema.upper() != ziel["meta_schema"].upper():
        sys.exit("Meta-Schema der Umgebung {} ist {}, das Paket ist für {} gebaut - Abbruch.".format(
            env_id, schema, ziel["meta_schema"]))
    return env_id, schema


def meta_deploy(lauf, teil, ergebnis, zusammenfassung):
    """Lauf in META_DEPLOY festhalten; scheitert das (z. B. Recht fehlt), nur Hinweis."""
    try:
        _meta_deploy(lauf, teil, ergebnis, zusammenfassung)
    except Exception as e:  # noqa: BLE001 - Protokolldatei bleibt maßgeblich
        lauf.hinweis("META_DEPLOY nicht geschrieben ({}): {}".format(teil, str(e).splitlines()[0][:160]))


def _meta_deploy(lauf, teil, ergebnis, zusammenfassung):
    m = lauf.paket.manifest
    cur = lauf.cur
    if "META_DEPLOY" not in {k.upper() for k in objekte(cur, lauf.meta_schema)}:
        cur.execute(META_DEPLOY_DDL.format(schema=lauf.meta_schema))
        lauf.log("    {}.META_DEPLOY angelegt".format(lauf.meta_schema))
    cur.execute("INSERT INTO {}.META_DEPLOY (LAUF_ID, TEIL, PAKET, KUNDE, VERSION, INHALT_HASH, UMFANG, ERGEBNIS, "
                "ZUSAMMENFASSUNG, PROTOKOLL, BENUTZER, ZEITPUNKT) VALUES (?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP(0))"
                .format(lauf.meta_schema),
                [lauf.lauf_id, teil, lauf.paket.pfad.name, m.get("kunde"), m.get("version", {}).get("bezeichnung"),
                 m.get("inhalt_hash"), json.dumps(m.get("umfang", {}), ensure_ascii=False)[:4000], ergebnis,
                 zusammenfassung[:4000], str(lauf.ordner), getpass.getuser()])


def einspielen(args):
    try:
        paket = Paket(args.paket)
    except PaketFehler as e:
        sys.exit(str(e))
    studio = Studio()
    m = paket.manifest
    env_id, schema = ziel_bestimmen(studio, m)
    lauf = Lauf(args, studio, datetime.now().strftime("%Y%m%d_%H%M%S") + ("" if args.ausfuehren else "_plan"))
    lauf.paket, lauf.env_id, lauf.meta_schema = paket, env_id, schema
    teile = [t for t in paket.teile() if not args.teil or t in args.teil]

    lauf.log("Paket      {}  (Prüfsummen OK)".format(paket.pfad.name))
    lauf.log("Kunde      {}  Version {}  Inhalt {}".format(m.get("kunde"), m["version"].get("bezeichnung"), m["inhalt_hash"][:12]))
    lauf.log("Quelle     {} ({})   Ziel {} -> Umgebung {} ({})".format(
        m["quelle"]["umgebung"], m["quelle"]["studio_env"], m["ziel"]["umgebung"], env_id, studio.quelle_umgebungen))
    lauf.log("Meta-Schema {}   Teile {}   Modus {}".format(schema, ", ".join(teile),
                                                          "AUSFÜHREN" if args.ausfuehren else "Plan (Dry-Run)"))
    lauf.log("Protokoll  {}".format(lauf.ordner))
    if m["ziel"].get("studio_env") != env_id:
        lauf.hinweis("Umgebung {} gibt es hier nicht; verwendet wird {} (Step-Dateien nach etl/jobs/{}/)".format(
            m["ziel"]["studio_env"], env_id, env_id))

    host, user, _ = studio.zugang(env_id, "einspielen_db")
    lauf.log("Verbindung {} als {}{}".format(host, user, " (einspielen_db)" if user != studio.umgebung(env_id)["user"] else ""))
    lauf.conn = studio.verbinden(env_id, "einspielen_db")
    lauf.cur = lauf.conn.cursor()
    lauf.teile = teile

    plaene = []
    for teil in teile:
        if teil == "software":
            plaene.append((teil, plan_software(lauf), ausfuehren_software))
        if teil in ("metaschema", "strukturen"):
            plaene.append((teil, plan_strukturen(lauf, teil), ausfuehren_strukturen))
        elif teil == "rechte":
            plaene.append((teil, plan_rechte(lauf), ausfuehren_rechte))
        if teil in ("vorlagen", "jobs"):
            if m["inhalt"][teil].get("meta"):
                plaene.append((teil, plan_meta(lauf, teil), ausfuehren_meta))
        if teil in ("vorlagen", "jobs", "dashboards") and m["inhalt"][teil].get("dateien"):
            plaene.append((teil, plan_dateien(lauf, teil), ausfuehren_dateien))

    rechte_pruefen(lauf, [x for x in plaene if not isinstance(x[1], list)])

    lauf.log("\n== Ergebnis Plan: {} Konflikte, {} Hinweise".format(len(lauf.konflikte), len(lauf.hinweise)))
    for k in lauf.konflikte:
        lauf.log("  KONFLIKT " + k)
    if lauf.konflikte:
        lauf.log("Nichts eingespielt. Konflikte lösen und erneut aufrufen.")
        return 1
    if not args.ausfuehren:
        lauf.log("Dry-Run - nichts geschrieben. Einspielen mit --ausfuehren.")
        return 0

    lauf.log("\n== Ausführung")
    fehler = 0
    for teil, plan, fn in plaene:
        lauf.log("  {}".format(teil))
        try:
            fn(lauf, plan)
            ergebnis = "OK"
        except Exception as e:  # noqa: BLE001 - Lauf protokollieren, dann abbrechen
            lauf.log("  FEHLER {}: {}".format(teil, str(e).splitlines()[0] if str(e) else repr(e)))
            ergebnis, fehler = "FEHLER", 1
        meta_deploy(lauf, teil, ergebnis, "{} Hinweise im Plan".format(len(lauf.hinweise)))
        if fehler:
            lauf.log("Abbruch. Rücknahme der bisherigen Schritte: einspielen.py --zuruecknehmen {}".format(lauf.lauf_id))
            return 1

    lauf.log("\n== Abnahme")
    fehler = abnahme.pruefen(paket, studio, env_id, lauf.cur, lauf.log, lauf.ordner)
    meta_deploy(lauf, "abnahme", "OK" if fehler == 0 else "FEHLER", "{} Fehler".format(fehler))
    lauf.log("Rücknahme bei Bedarf: einspielen.py --zuruecknehmen {}".format(lauf.lauf_id))
    return 1 if fehler else 0


# ===========================================================================
# Rücknahme
# ===========================================================================
def zuruecknehmen(args):
    studio = Studio()
    ordner = studio.root / PROTOKOLL / args.zuruecknehmen
    datei = ordner / "ruecknahme.json"
    if not datei.exists():
        sys.exit("Keine Rücknahme-Daten: {}".format(datei))
    eintraege = json.loads(datei.read_text(encoding="utf-8"))
    print("Rücknahme von Lauf {} ({} Schritte, in umgekehrter Reihenfolge){}".format(
        args.zuruecknehmen, len(eintraege), "" if args.ausfuehren else " - Plan"))
    env_id = args.umgebung
    cur = conn = None
    if any(e["typ"] not in ("datei", "datei_entfernt", "hinweis") for e in eintraege):
        if not env_id:
            log = (ordner / "einspielen.log").read_text(encoding="utf-8")
            for z in log.splitlines():
                if z.startswith("Quelle") and "-> Umgebung" in z:
                    env_id = z.split("-> Umgebung ", 1)[1].split(" ", 1)[0]
        conn = studio.verbinden(env_id, "einspielen_db")
        cur = conn.cursor()
    for e in reversed(eintraege):
        typ = e["typ"]
        if typ == "hinweis":
            print("  Hinweis: " + e["text"])
        elif typ in ("datei", "datei_entfernt"):
            if e["sicherung"]:
                print("  Datei zurück: {}".format(e["ziel"]))
                if args.ausfuehren:
                    Path(e["ziel"]).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(ordner / e["sicherung"]), e["ziel"])
            else:
                print("  Datei entfernen (war neu): {}".format(e["ziel"]))
                if args.ausfuehren and Path(e["ziel"]).exists():
                    os.remove(e["ziel"])
        elif typ == "meta":
            n = len(e["eingefuegt"])
            vorher = [json.loads(z) for z in (ordner / e["vorher"]).read_text(encoding="utf-8").splitlines()] if e["vorher"] else []
            print("  META {}: {} eingefügte Zeilen löschen, {} Zeilen auf Vorher-Stand".format(e["tabelle"], n, len(vorher)))
            if args.ausfuehren:
                bed = " AND ".join('"{}" = ?'.format(c) for c in e["id"])
                ipos = [e["spalten"].index(c) for c in e["id"]]
                for ids in e["eingefuegt"]:
                    cur.execute("DELETE FROM {}.{} WHERE {}".format(e["schema"], e["tabelle"], bed), [wert_fuer_db(v) for v in ids])
                for z in vorher:
                    cur.execute("DELETE FROM {}.{} WHERE {}".format(e["schema"], e["tabelle"], bed), [wert_fuer_db(z[i]) for i in ipos])
                    cur.execute("INSERT INTO {}.{} ({}) VALUES ({})".format(
                        e["schema"], e["tabelle"], ", ".join('"{}"'.format(c) for c in e["spalten"]),
                        ", ".join("?" * len(e["spalten"]))), [wert_fuer_db(v) for v in z])
        elif typ in ("view", "view_entfernt"):
            if e["alt"]:
                print("  View {}.{}: alter Text".format(e["db"], e["name"]))
                if args.ausfuehren:
                    cur.execute("DATABASE {}".format(e["db"]))
                    cur.execute(view_als_replace(e["alt"]).strip().rstrip(";"))
            else:
                print("  View {}.{}: entfernen (war neu)".format(e["db"], e["name"]))
                if args.ausfuehren:
                    cur.execute('DROP VIEW {}."{}"'.format(e["db"], e["name"]))
        elif typ == "tabelle_neu":
            n = _zeilen(cur, e["db"], e["name"])
            if n:
                print("  Tabelle {}.{}: war neu, hat jetzt {} Zeilen - bleibt".format(e["db"], e["name"], n))
            else:
                print("  Tabelle {}.{}: entfernen (war neu, leer)".format(e["db"], e["name"]))
                if args.ausfuehren:
                    cur.execute('DROP TABLE {}."{}"'.format(e["db"], e["name"]))
        elif typ in ("tabelle_ersetzt", "tabelle_entfernt"):
            print("  Tabelle {}.{}: alte Struktur wiederherstellen (war leer)".format(e["db"], e["name"]))
            if args.ausfuehren:
                if typ == "tabelle_ersetzt":
                    cur.execute('DROP TABLE {}."{}"'.format(e["db"], e["name"]))
                cur.execute(e["alt"].strip().rstrip(";"))
        elif typ == "spalte":
            print("  Spalte {}.{}.{} ({}): nicht automatisch - bei Bedarf ALTER TABLE {}.\"{}\" DROP \"{}\"".format(
                e["db"], e["name"], e["spalte"], e["was"], e["db"], e["name"], e["spalte"]))
        elif typ == "startzeile":
            print("  Startzeile {}.{} {}: löschen".format(e["db"], e["tabelle"], e["werte"]))
            if args.ausfuehren:
                bed = " AND ".join('"{}" = ?'.format(c) for c in e["schluessel"])
                cur.execute('DELETE FROM {}."{}" WHERE {}'.format(e["db"], e["tabelle"], bed), [wert_fuer_db(v) for v in e["werte"]])
    if conn:
        conn.close()
    print("Erledigt." if args.ausfuehren else "Plan - nichts geändert. Ausführen mit --ausfuehren.")
    print("Rechte werden nicht zurückgenommen (nur additiv).")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paket", nargs="?", help="Paket (ZIP)")
    ap.add_argument("--ausfuehren", action="store_true", help="wirklich einspielen (sonst nur Plan)")
    ap.add_argument("--teil", action="append", help="nur diesen Teil (mehrfach möglich)")
    ap.add_argument("--loeschen", action="store_true", help="was nicht mehr im Paket ist, im Umfang entfernen")
    ap.add_argument("--leere-neu", action="store_true", help="geänderte leere Tabellen neu anlegen")
    ap.add_argument("--zuruecknehmen", metavar="LAUF_ID", help="Lauf zurücknehmen")
    ap.add_argument("--umgebung", help="nur für --zuruecknehmen: Umgebung, falls nicht aus dem Log lesbar")
    args = ap.parse_args()
    if args.zuruecknehmen:
        sys.exit(zuruecknehmen(args))
    if not args.paket:
        ap.error("Paket fehlt")
    sys.exit(einspielen(args))


if __name__ == "__main__":
    main()
