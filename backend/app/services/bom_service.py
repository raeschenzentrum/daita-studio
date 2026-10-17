"""
BOM-Explorer – ein normalisiertes Modell (3NF, Entitäten mit Historie) interaktiv
abfragen (Widget-Typ „bom-explorer“). Gegenstück zum Star-Explorer: zeigt, was
eine Abfrage im Reusable gegenüber dem Stern zusätzlich entscheiden muss.

Definition: <Dashboard-Ablage>/bom.yml

    zeitbezug:                       # technische Spalten der gelesenen Views
      von: DWH_GUELTIG_VON
      bis: DWH_GUELTIG_BIS
      aktuell: DWH_IST_AKTUELL
      aktuell_wert: "Y"
      unbekannt: -1                  # Schlüssel der Unbekannt-Zeile (zählt nicht)
    texte: {sprache_spalte: LANG_CD, sprache: de, text_spalte: TXT}
    codes:                           # Code -> Texttabelle (je Schlüssel und Sprache ein Text)
      geschlecht: {tabelle: ${REU_ACCESS}.CD_GESCHLECHT_TXT, schluessel: GESCHLECHT_SK}
    entitaeten:
      person:
        titel: Person
        tabelle: ${REU_ACCESS}.PART_PERSON
        schluessel: PART_PERSON_SK
        alias: pe
        attribute:
          - {spalte: DATENSPERRE_JN, titel: Datensperre, auswahl: true}
          - {spalte: GESCHLECHT_SK, titel: Geschlecht, code: geschlecht, auswahl: true}   # Text über Code
          - {id: GEBURTSJAHR, titel: Geburtsjahr, typ: zahl, ausdruck: "EXTRACT(YEAR FROM {a}.GEBURTSDATUM)"}
    beziehungen:                     # Kind -> Eltern über Fremdschlüssel (n:1); je Entität höchstens ein Elternteil
      - {kind: identitaet, eltern: person, spalte: PERSON_SK}

Regeln der Abfrage (ab der gewählten Ausgangsentität „Basis“, eine Zeile je Basis-Satz):
- oben (Vorfahren, n:1): LEFT JOIN – gruppieren, filtern, verschiedene zählen.
- unten (Nachfahren, 1:n): würden Zeilen vervielfachen. Nur als Bedingung (EXISTS) und
  als Anzahl (vorab je Basis-Satz gezählt und angehängt); Bedingungen an einem Kind
  gelten auch für dessen Zählung.
- daneben (über einen Vorfahren erreichbar, z. B. Identitäten der Person ab Geschäft):
  nur als Bedingung (EXISTS).
- Zeitbezug in jeder Tabelle: aktuell (Kennzeichen) oder Stand am Stichtag
  (Gültig-von ≤ Stichtag < Gültig-bis, auf Tagesebene); Unbekannt-Zeilen zählen nicht.

Wie beim Star-Explorer: nur freigegebene Attribute, Werte als Bind-Parameter, nur
SELECT, Ergebnis gruppiert, Gruppen unter min_zelle maskiert, Seiten aus dem Cache,
R-Gerüst über dieselbe Vorlage.
"""

import datetime as _dt
import re
from typing import Any, Optional

from app.services import dashboard_service as ds
from app.services import sql_analyse, td_readonly
from app.services import star_service as st

DATEI = "bom.yml"
_ID = re.compile(r"^[A-Za-z0-9_]+$")
_OBJ = re.compile(r"^[A-Za-z0-9_$#]+\.[A-Za-z0-9_$#]+$")


# Kurze Teradata-Schlüsselwörter, die als Alias einen Syntaxfehler geben
_RESERVIERT = {"AS", "AT", "BY", "DO", "EQ", "GE", "GT", "IF", "IN", "IS", "LE", "LT", "NE", "NO", "OF", "ON", "OR",
               "TO", "UP", "AND", "ANY", "ALL", "AVG", "END", "FOR", "MAX", "MIN", "MOD", "NOT", "SET", "SUM", "TOP"}


class BomError(ds.DashboardError):
    pass


# ---------------------------------------------------------------------------
# Definition
# ---------------------------------------------------------------------------

def _definition() -> dict:
    path = ds._root() / DATEI
    if not path.exists():
        raise BomError(404, f"{DATEI} fehlt in der Dashboard-Ablage")
    roh = ds._load_yaml(path)
    werte = ds.variables()

    def objekt(text: str) -> dict:
        v = ds._substitute(str(text), werte, strict=True)
        if not _OBJ.match(v):
            raise BomError(500, f"Ungültiges Objekt in {DATEI}: {text!r}")
        return {"aufgeloest": v, "roh": str(text)}

    def ident(wert, wo: str) -> str:
        if not _ID.match(str(wert or "")):
            raise BomError(500, f"{DATEI}: ungültiger Name {wert!r} ({wo})")
        return str(wert).upper()

    zb = roh.get("zeitbezug") or {}
    zeit = {k: ident(zb.get(k), f"zeitbezug.{k}") for k in ("von", "bis", "aktuell")}
    zeit["aktuell_wert"] = str(zb.get("aktuell_wert", "Y")).replace("'", "")
    zeit["unbekannt"] = int(zb.get("unbekannt", -1))
    tx = roh.get("texte") or {}
    texte = {"sprache_spalte": ident(tx.get("sprache_spalte", "LANG_CD"), "texte.sprache_spalte"),
             "sprache": str(tx.get("sprache", "de")).replace("'", ""),
             "text_spalte": ident(tx.get("text_spalte", "TXT"), "texte.text_spalte")}
    codes = {}
    for cid, c in (roh.get("codes") or {}).items():
        o = objekt(c["tabelle"])
        codes[cid] = {"id": cid, "tabelle": o["aufgeloest"], "tabelle_roh": o["roh"],
                      "schluessel": ident(c.get("schluessel"), f"codes.{cid}.schluessel")}
    ents = {}
    belegt = set()
    for eid, e in (roh.get("entitaeten") or {}).items():
        o = objekt(e["tabelle"])
        alias = str(e.get("alias") or eid[:2]).lower()
        if not _ID.match(alias) or alias in belegt or alias.upper() in _RESERVIERT:
            raise BomError(500, f"{DATEI}: Alias {alias!r} von {eid} ungültig, doppelt oder reserviert")
        belegt.add(alias)
        attrs = st._attribute(e, eid)
        for a in attrs:
            if a.get("code") and a["code"] not in codes:
                raise BomError(500, f"{DATEI}: {eid}.{a['id']} verweist auf unbekannten Code {a['code']!r}")
        ents[eid] = {**e, "id": eid, "titel": e.get("titel", eid), "tabelle": o["aufgeloest"], "tabelle_roh": o["roh"],
                     "schluessel": ident(e.get("schluessel"), f"{eid}.schluessel"), "alias": alias, "attribute": attrs}
    eltern = {}
    for b in roh.get("beziehungen") or []:
        k, p = b.get("kind"), b.get("eltern")
        if k not in ents or p not in ents:
            raise BomError(500, f"{DATEI}: Beziehung mit unbekannter Entität {b}")
        if k in eltern:
            raise BomError(500, f"{DATEI}: {k} hat mehr als einen Elternteil")
        eltern[k] = {"eltern": p, "spalte": ident(b.get("spalte"), f"beziehung {k}->{p}"), "titel": b.get("titel")}
    # Zyklen ausschließen
    for e in ents:
        gesehen, x = set(), e
        while x in eltern:
            if x in gesehen:
                raise BomError(500, f"{DATEI}: Zyklus in den Beziehungen bei {e}")
            gesehen.add(x)
            x = eltern[x]["eltern"]
    return {"zeit": zeit, "texte": texte, "codes": codes, "entitaeten": ents, "eltern": eltern}


def _vorfahren(defi: dict, e: str) -> list:
    """[e, Eltern, Großeltern, …]"""
    kette = [e]
    while kette[-1] in defi["eltern"]:
        kette.append(defi["eltern"][kette[-1]]["eltern"])
    return kette


def struktur(defi: dict, basis: str) -> dict:
    """Je Entität aus Sicht der Basis: art (basis | oben | unten | daneben), ebene
    (Zeilen relativ zur Basis: oben negativ, unten positiv), anker (für unten/daneben:
    der gejointe Vorfahre, an dem die Unterabfrage hängt), abwaerts (Kette vom Kind des
    Ankers bis zur Entität)."""
    hoch = _vorfahren(defi, basis)
    out = {}
    for e in defi["entitaeten"]:
        if e == basis:
            out[e] = {"art": "basis", "ebene": 0}
            continue
        if e in hoch:
            out[e] = {"art": "oben", "ebene": -hoch.index(e)}
            continue
        kette = _vorfahren(defi, e)
        anker = next(x for x in kette if x in hoch) if any(x in hoch for x in kette) else None
        if anker is None:
            out[e] = {"art": "getrennt", "ebene": 99}
            continue
        abwaerts = list(reversed(kette[:kette.index(anker)]))   # Kind des Ankers … e
        out[e] = {"art": "unten" if anker == basis else "daneben",
                  "ebene": len(abwaerts) - hoch.index(anker), "anker": anker, "abwaerts": abwaerts}
    return out


def _widget(dashboard_id: str, widget_id: str) -> tuple[dict, dict, dict]:
    dash = ds._load_dashboard(dashboard_id)
    widget = ds._widget(dash, widget_id)
    if widget.get("typ") != "bom-explorer":
        raise BomError(400, f"Widget '{widget_id}' ist kein BOM-Explorer")
    return dash, widget, _definition()


def definition(dashboard_id: str, widget_id: str) -> dict:
    dash, widget, defi = _widget(dashboard_id, widget_id)
    ents = []
    for e in defi["entitaeten"].values():
        el = defi["eltern"].get(e["id"])
        ents.append({
            "id": e["id"], "titel": e["titel"], "tabelle": e["tabelle"], "schluessel": e["schluessel"],
            "alias": e["alias"], "beschreibung": e.get("beschreibung"),
            "eltern": el["eltern"] if el else None, "fk": el["spalte"] if el else None,
            "attribute": [{**st._attr_client(a), **({"code": a["code"]} if a.get("code") else {})} for a in e["attribute"]],
        })
    basen = {e: struktur(defi, e) for e in defi["entitaeten"]}
    standard = (widget.get("optionen") or {}).get("basis")
    return {"entitaeten": ents, "basen": basen, "basis": standard if standard in defi["entitaeten"] else ents[0]["id"],
            "zeitbezug": defi["zeit"], "texte": defi["texte"],
            "min_zelle": ds._min_zelle(dash), "max_gruppen": st.MAX_GRUPPEN}


# ---------------------------------------------------------------------------
# Abfrage bauen
# ---------------------------------------------------------------------------

def _attr(defi: dict, ent: str, attr: str) -> tuple[dict, dict]:
    e = defi["entitaeten"].get(ent)
    if e:
        for a in e["attribute"]:
            if a["id"] == str(attr).upper():
                return e, a
    raise BomError(400, f"Attribut nicht freigegeben: {ent}.{attr}")


def _zeitwert(zeit: dict) -> Optional[_dt.date]:
    if (zeit or {}).get("art", "aktuell") == "aktuell":
        return None
    try:
        return _dt.date.fromisoformat(str((zeit or {}).get("datum"))[:10])
    except ValueError:
        raise BomError(400, f"Ungültiger Stichtag: {(zeit or {}).get('datum')!r}")


_MARKE = re.compile(r"§W(\d+)§")


def _kurz(a: dict) -> str:
    """Attribut-ID ohne _SK (Code-Attribute zeigen den Text, nicht den Schlüssel)."""
    i = a["id"]
    return (i[:-3] if a.get("code") and i.endswith("_SK") else i).lower()[:24]


class _Werte:
    """Sammelt Werte hinter Marken §W<n>§; am Ende werden die Marken in Textreihenfolge
    durch ? (Bind-Parameter) oder ${FILTER:id} (R-Gerüst) ersetzt."""

    def __init__(self):
        self.liste = []

    def marke(self, fid: str, titel: str, typ: str, wert: Any) -> str:
        self.liste.append({"id": fid, "titel": titel, "typ": typ, "wert": wert})
        return f"§W{len(self.liste) - 1}§"

    def ph(self, basis: str, titel: str, typ: str):
        """Platzhalter-Funktion für star_service.bedingung()."""
        return lambda wert, nr=None: self.marke(basis if nr is None else f"{basis}_{nr}", titel, typ, wert)

    def aufloesen(self, sql: str, r_vorlage: bool) -> tuple[str, list, list]:
        params, r_filter, ids = [], [], set()
        def ers(m):
            w = self.liste[int(m.group(1))]
            if not r_vorlage:
                params.append(w["wert"])
                return "?"
            fid, n = w["id"], 2
            while fid in ids and not (w["id"] == "stichtag"):
                fid, n = f"{w['id']}_{n}", n + 1
            if fid not in ids:
                ids.add(fid)
                r_filter.append({**w, "id": fid})
            return "${FILTER:" + fid + "}"
        return _MARKE.sub(ers, sql), params, r_filter


def baue(defi: dict, basis: str, auswahl: dict, r_vorlage: bool = False) -> dict:
    """auswahl: {zeit: {art: aktuell|stichtag, datum}, gruppen: [{entitaet, attr}],
    filter: [{entitaet, attr, op, werte}], kennzahlen: [{entitaet}]}"""
    ents, z, tx = defi["entitaeten"], defi["zeit"], defi["texte"]
    if basis not in ents:
        raise BomError(400, f"Unbekannte Ausgangsentität {basis!r}")
    tab = (lambda o: o["tabelle_roh"]) if r_vorlage else (lambda o: o["tabelle"])
    stru = struktur(defi, basis)
    hoch = _vorfahren(defi, basis)
    w = _Werte()
    stichtag = _zeitwert(auswahl.get("zeit"))

    def zeitbed(alias: str) -> str:
        if stichtag is None:
            return f"{alias}.{z['aktuell']} = '{z['aktuell_wert']}'"
        m = lambda: w.marke("stichtag", "Stand am Stichtag", "datum", stichtag)
        return f"CAST({alias}.{z['von']} AS DATE) <= {m()} AND CAST({alias}.{z['bis']} AS DATE) > {m()}"

    def ausdruck(alias: str, a: dict, text_joins: list) -> str:
        """Ausdruck eines Attributs; Code-Attribute lesen den Text aus der Texttabelle
        (JOIN wird in text_joins gesammelt)."""
        if not a.get("code"):
            return st._ausdruck(a, alias)
        c = defi["codes"][a["code"]]
        ta = f"{alias}_{_kurz(a)}"
        if not any(j[0] == ta for j in text_joins):
            text_joins.append((ta, f"LEFT JOIN {tab(c)} {ta}\n    ON {ta}.{c['schluessel']} = {alias}.{a['spalte'].upper()}"
                                   f"\n   AND {ta}.{tx['sprache_spalte']} = '{tx['sprache']}'\n   AND {zeitbed(ta)}"))
        return f"{ta}.{tx['text_spalte']}"

    noetig_hoch: set = set()
    def brauche(eid: str):
        noetig_hoch.update(hoch[1:hoch.index(eid) + 1])

    namen: set = set()
    def spaltenname(roh: str) -> str:
        n, i = roh.upper()[:60], 2
        while n in namen:
            n, i = f"{roh.upper()[:57]}_{i}", i + 1
        namen.add(n)
        return n

    # ---- Auswahl prüfen und einordnen
    gruppen = []
    for g in (auswahl.get("gruppen") or [])[:12]:
        e, a = _attr(defi, g.get("entitaet"), g.get("attr"))
        if stru[e["id"]]["art"] not in ("basis", "oben"):
            raise BomError(400, f"Gruppieren nur nach {ents[basis]['titel']} und ihren Vorfahren (n:1); "
                                f"{e['titel']} würde Zeilen vervielfachen")
        if stru[e["id"]]["art"] == "oben":
            brauche(e["id"])
        gruppen.append((e, a))
    direkt, unter = [], {}
    for fl in (auswahl.get("filter") or [])[:30]:
        e, a = _attr(defi, fl.get("entitaet"), fl.get("attr"))
        werte = fl.get("werte")
        werte = werte if isinstance(werte, list) else ([] if werte is None else [werte])
        art = stru[e["id"]]["art"]
        if art in ("basis", "oben"):
            if art == "oben":
                brauche(e["id"])
            direkt.append((e, a, fl.get("op", "eq"), werte))
        elif art in ("unten", "daneben"):
            unter.setdefault(e["id"], []).append((a, fl.get("op", "eq"), werte))
            if art == "daneben":
                brauche(stru[e["id"]]["anker"])
        else:
            raise BomError(400, f"{e['titel']} ist von {ents[basis]['titel']} aus nicht erreichbar")
    zaehlen = []
    for k in (auswahl.get("kennzahlen") or [{"entitaet": basis}])[:12]:
        eid = k.get("entitaet")
        if eid not in ents:
            raise BomError(400, f"Unbekannte Entität für Kennzahl: {eid!r}")
        art = stru[eid]["art"]
        if art not in ("basis", "oben", "unten"):
            raise BomError(400, f"{ents[eid]['titel']} lässt sich je {ents[basis]['titel']} nicht eindeutig zählen")
        if art == "oben":
            brauche(eid)
        zaehlen.append((eid, art))

    def abwaerts(eid: str, modus: str) -> str:
        """Unterabfrage vom Anker abwärts bis eid: EXISTS(…) oder Zählung je Anker-Schlüssel."""
        s = stru[eid]
        kette, anker = s["abwaerts"], ents[s["anker"]]
        ziel, erstes = ents[eid], ents[s["abwaerts"][0]]
        fk = defi["eltern"][erstes["id"]]["spalte"]
        tj: list = []
        von = [f"FROM {tab(ziel)} {ziel['alias']}"]
        for i in range(len(kette) - 1, 0, -1):     # von eid aufwärts bis zum Kind des Ankers
            kind, elt = ents[kette[i]], ents[kette[i - 1]]
            von.append(f"JOIN {tab(elt)} {elt['alias']}\n      ON {elt['alias']}.{elt['schluessel']} = "
                       f"{kind['alias']}.{defi['eltern'][kind['id']]['spalte']}\n     AND {zeitbed(elt['alias'])}")
        bed = [f"{ziel['alias']}.{ziel['schluessel']} <> {z['unbekannt']}", zeitbed(ziel["alias"])]
        for a, op, werte in unter.get(eid, []):
            expr = ausdruck(ziel["alias"], a, tj)
            bed.append(st.bedingung(expr, a, op, werte, w.ph(f"{eid}_{a['id']}".lower(),
                                                              f"{ziel['titel']}: {a.get('titel') or a['id']}",
                                                              a.get("typ", "text"))))
        von += [j.replace("\n", "\n  ") for _, j in tj]
        if modus == "exists":
            kopf = "EXISTS (SELECT 1"
            bed.insert(0, f"{erstes['alias']}.{fk} = {anker['alias']}.{anker['schluessel']}")
            fuss = ")"
        else:
            kopf = (f"(SELECT {erstes['alias']}.{fk} AS SCHLUESSEL, "
                    f"COUNT(DISTINCT {ziel['alias']}.{ziel['schluessel']}) AS ANZAHL")
            fuss = f"\n    GROUP BY {erstes['alias']}.{fk})"
        return (kopf + "\n    " + "\n    ".join(von) + "\n    WHERE " + "\n      AND ".join(bed) + fuss)

    # ---- SELECT-Liste (Text in Lesereihenfolge; Werte nur über Marken)
    b = ents[basis]
    haupt_tj: list = []
    select, group, spalten = [], [], []
    for e, a in gruppen:
        expr = ausdruck(e["alias"], a, haupt_tj)
        name = spaltenname(f"{e['id']}_{_kurz(a)}")
        select.append(f"{expr} AS {name}")
        group.append(expr)
        spalten.append({"name": name, "titel": a.get("titel") or a["id"], "rolle": e["titel"], "art": "gruppe",
                        "typ": a.get("typ", "text")})
    zaehl_joins = []
    for eid, art in zaehlen:
        e = ents[eid]
        name = spaltenname(f"ANZAHL_{eid}")
        if art == "basis":
            select.append(f"COUNT(*) AS {name}")
        elif art == "oben":
            select.append(f"COUNT(DISTINCT NULLIF({e['alias']}.{e['schluessel']}, {z['unbekannt']})) AS {name}")
        else:
            ka = f"k_{e['alias']}"
            select.append(f"SUM(COALESCE({ka}.ANZAHL, 0)) AS {name}")
            zaehl_joins.append((ka, eid))
        spalten.append({"name": name, "titel": f"Anzahl {e['titel']}" + (" (verschiedene)" if art == "oben" else ""),
                        "art": "kennzahl", "agg": "count" if art == "basis" else "count_distinct", "typ": "zahl"})
    kontrolle = next((i for i, sp in enumerate(spalten) if sp.get("agg") == "count"), None)
    if kontrolle is None:
        name = spaltenname(f"ZEILEN_{basis}")
        select.append(f"COUNT(*) AS {name}")
        spalten.append({"name": name, "titel": f"Zeilen {b['titel']}", "art": "kontrolle", "agg": "count", "typ": "zahl"})
        kontrolle = len(spalten) - 1

    z_out = [f"-- Ausgangsentität: {b['titel']} – eine Zeile je {b['titel']}, "
             + ("aktueller Stand" if stichtag is None else f"Stand am {stichtag.isoformat()}"),
             "SELECT"] + [f"    {x}," for x in select[:-1]] + [f"    {select[-1]}", f"FROM {tab(b)} {b['alias']}"]
    for i in range(1, len(hoch)):
        e, kind = ents[hoch[i]], ents[hoch[i - 1]]
        if e["id"] not in noetig_hoch:
            continue
        fk = defi["eltern"][kind["id"]]["spalte"]
        z_out.append(f"-- {e['titel']}: n:1 über {kind['titel']}.{fk}")
        z_out.append(f"LEFT JOIN {tab(e)} {e['alias']}\n    ON {e['alias']}.{e['schluessel']} = {kind['alias']}.{fk}"
                     f"\n   AND {zeitbed(e['alias'])}")
    wh = [(f"{b['alias']}.{b['schluessel']} <> {z['unbekannt']}", "ohne Unbekannt-Zeile"),
          (zeitbed(b["alias"]), "Zeitbezug")]
    for e, a, op, werte in direkt:
        expr = ausdruck(e["alias"], a, haupt_tj)
        wh.append((st.bedingung(expr, a, op, werte, w.ph(f"{e['id']}_{a['id']}".lower(),
                                                          f"{e['titel']}: {a.get('titel') or a['id']}",
                                                          a.get("typ", "text"))), e["titel"]))
    if haupt_tj:
        z_out.append(f"-- Codes: Text in der Sprache '{tx['sprache']}'")
        z_out += [j for _, j in haupt_tj]
    for ka, eid in zaehl_joins:
        e = ents[eid]
        z_out.append(f"-- {e['titel']} (1:n): je {b['titel']} vorab gezählt, damit sich nichts vervielfacht")
        z_out.append(f"LEFT JOIN {abwaerts(eid, 'zaehlen')} {ka}\n    ON {ka}.SCHLUESSEL = {b['alias']}.{b['schluessel']}")
    for eid in unter:
        e = ents[eid]
        wh.append((abwaerts(eid, "exists"),
                   f"{e['titel']} ({'Nachfahre' if stru[eid]['art'] == 'unten' else 'über ' + ents[stru[eid]['anker']]['titel']}, 1:n): "
                   f"mindestens einer erfüllt die Bedingung"))
    z_out.append("WHERE " + "\n  AND ".join(f"{x}  -- {k}" for x, k in wh))
    if group:
        z_out.append("GROUP BY " + ", ".join(group))
        z_out.append("ORDER BY " + ", ".join(str(i + 1) for i in range(len(group))))
    sql, params, r_filter = w.aufloesen("\n".join(z_out), r_vorlage)
    return {"sql": sql, "params": params, "r_filter": r_filter, "spalten": spalten, "kontrolle": kontrolle}


# ---------------------------------------------------------------------------
# Öffentliche Funktionen
# ---------------------------------------------------------------------------

def abfrage(dashboard_id: str, widget_id: str, basis: str, auswahl: dict,
            offset: int = 0, limit: int = 100, ausfuehren: bool = True) -> dict:
    dash, _, defi = _widget(dashboard_id, widget_id)
    q = baue(defi, basis, auswahl or {})
    out = {"sql": q["sql"], "sql_mit_werten": sql_analyse.mit_werten(q["sql"], q["params"]), "spalten": q["spalten"]}
    if ausfuehren:
        out.update(st.seite(dash, dashboard_id, "bom", q, offset, limit))
    return out


def r_code(dashboard_id: str, widget_id: str, basis: str, auswahl: dict) -> dict:
    dash, _, defi = _widget(dashboard_id, widget_id)
    q = baue(defi, basis, auswahl or {}, r_vorlage=True)
    e = defi["entitaeten"][basis]
    grenze = ds._min_zelle(dash)
    widget = {
        "id": f"{widget_id}_{basis}", "typ": "table",
        "titel": f"BOM-Explorer {e['titel']}",
        "erlaeuterung": f"Abfrage aus dem BOM-Explorer, Ausgangsentität {e['titel']} (eine Zeile je {e['titel']}).",
        "hinweise": [f"Im Dashboard werden Gruppen unter {grenze} Zeilen maskiert; dieses Skript liefert die "
                     f"ungekürzten Werte. Vor der Weitergabe kleine Gruppen ausblenden."] if grenze else [],
    }
    return {"r_code": st.r_skript(dash, widget, q), "dateiname": f"{dashboard_id}_{basis}.R"}


def werte(dashboard_id: str, widget_id: str, entitaet: str, attr: str) -> dict:
    """Werte eines Attributs mit auswahl: true (Codes: Texte der aktuellen Texttabelle)."""
    dash, _, defi = _widget(dashboard_id, widget_id)
    e, a = _attr(defi, entitaet, attr)
    if not a.get("auswahl"):
        raise BomError(400, f"Attribut {attr} hat keine Auswahlliste")
    z, tx = defi["zeit"], defi["texte"]
    if a.get("code"):
        c = defi["codes"][a["code"]]
        sql = (f"SELECT DISTINCT x.{tx['text_spalte']} AS WERT FROM {c['tabelle']} x WHERE x.{tx['sprache_spalte']} = "
               f"'{tx['sprache']}' AND x.{z['aktuell']} = '{z['aktuell_wert']}' AND x.{tx['text_spalte']} IS NOT NULL ORDER BY 1")
    else:
        expr = st._ausdruck(a, "x")
        sql = f"SELECT DISTINCT {expr} AS WERT FROM {e['tabelle']} x WHERE {expr} IS NOT NULL ORDER BY 1"
    key = f"dash::{dashboard_id}::bom::werte::{sql}"
    try:
        res, _ = td_readonly.cached(key, lambda: td_readonly.query(sql, [], st.MAX_WERTE, art="daten"), st.WERTE_TTL)
    except Exception as ex:
        raise BomError(502, f"Werte nicht lesbar: {str(ex).splitlines()[0]}")
    return {"werte": [row[0] for row in res["rows"]], "abgeschnitten": res["truncated"]}


def modell_sql(dashboard_id: str, widget_id: str) -> str:
    """Je Beziehung und Code ein JOIN – Grundlage für Datenmodell, Joins und Herkunft im Info-Panel."""
    _, _, defi = _widget(dashboard_id, widget_id)
    ents, teile = defi["entitaeten"], []
    for kid, el in defi["eltern"].items():
        k, p = ents[kid], ents[el["eltern"]]
        teile.append(f"-- {k['titel']} -> {p['titel']} (n:1)\nSELECT COUNT(*)\nFROM {k['tabelle']} {k['alias']}\n"
                     f"JOIN {p['tabelle']} {p['alias']}\n    ON {p['alias']}.{p['schluessel']} = {k['alias']}.{el['spalte']}")
    for e in ents.values():
        for a in e["attribute"]:
            if a.get("code"):
                c = defi["codes"][a["code"]]
                teile.append(f"-- {e['titel']}.{a.get('titel', a['id'])} -> Text\nSELECT COUNT(*)\nFROM {e['tabelle']} {e['alias']}\n"
                             f"JOIN {c['tabelle']} t\n    ON t.{c['schluessel']} = {e['alias']}.{a['spalte'].upper()}")
    return ";\n\n".join(teile)
