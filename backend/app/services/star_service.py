"""
Star-Explorer – ein Sternschema interaktiv abfragen (Widget-Typ „star-explorer“).

Definition: <Dashboard-Ablage>/sterne.yml

    dimensionen:
      <dim-id>:
        titel: Datum
        view: ${CON_ACCESS}.V_DIM_DATUM_SK
        schluessel: DATUM_SK
        attribute:
          - {spalte: JAHR, titel: Jahr, typ: zahl, auswahl: true}
          - {id: GEBURTSJAHR, titel: Geburtsjahr, typ: zahl,
             ausdruck: "EXTRACT(YEAR FROM {a}.GEBURTSDATUM)"}      # {a} = Alias der Dimension
    fakten:
      <fakt-id>:
        titel: Geschäft-Status
        view: ${CON_ACCESS}.V_FACT_GESCHAEFT_STATUS_SK
        beschreibung: Eine Zeile je Asylgeschäft …
        attribute: [ … ]                     # eigene Spalten des Fakts (degenerierte Dimensionen)
        kennzahlen:
          - {id: anzahl, titel: Anzahl Geschäfte, agg: [count]}
          - {id: personen, titel: Personen, spalte: PERSON_ID, agg: [count_distinct]}
          - {id: tage_offen, titel: Tage offen, spalte: TAGE_OFFEN, agg: [avg, sum, min, max]}
        dimensionen:
          - {rolle: eroeffnung, titel: Eröffnungsdatum, dim: datum, spalte: DATUM_EROEFFNUNG_SK, alias: de}

Das Widget nennt in optionen.fakten, welche Fakten es zeigt; nur diese sind
abfragbar. Der Client schickt nie SQL, nur die Auswahl (Rolle/Attribut-IDs,
Operator, Werte); Werte gehen als Bind-Parameter an die DB. Ausgeführt wird nur
SELECT (td_readonly). Ergebnis immer gruppiert; Gruppen mit weniger als
min_zelle Faktzeilen werden maskiert. Das Ergebnis (höchstens MAX_GRUPPEN
Gruppen) wird zwischengespeichert, geblättert wird im Cache.
"""

import datetime as _dt
import hashlib
import json
import logging
import re
import time
from typing import Any, Optional

from app.services import dashboard_service as ds
from app.services import sql_analyse, td_readonly

logger = logging.getLogger(__name__)

DATEI = "sterne.yml"
MAX_GRUPPEN = 10000
MAX_SEITE = 500
MAX_WERTE = 500
CACHE_TTL = 600
WERTE_TTL = 1800

_ID = re.compile(r"^[A-Za-z0-9_]+$")
_OBJ = re.compile(r"^[A-Za-z0-9_$#]+\.[A-Za-z0-9_$#]+$")

AGG = {
    "count": ("Anzahl", "COUNT(*)"),
    "count_distinct": ("Anzahl verschiedene", "COUNT(DISTINCT {s})"),
    "sum": ("Summe", "SUM({s})"),
    "avg": ("Durchschnitt", "AVG(CAST({s} AS DECIMAL(18,4)))"),
    "min": ("Minimum", "MIN({s})"),
    "max": ("Maximum", "MAX({s})"),
}
ZAEHLEND = {"count", "count_distinct"}
OPS = {"eq", "ne", "in", "like", "ge", "le", "between", "null", "notnull"}


class StarError(ds.DashboardError):
    pass


# ---------------------------------------------------------------------------
# Definition
# ---------------------------------------------------------------------------

def _definition() -> dict:
    path = ds._root() / DATEI
    if not path.exists():
        raise StarError(404, f"{DATEI} fehlt in der Dashboard-Ablage")
    roh = ds._load_yaml(path)
    werte = ds.variables()
    def aufloesen(view: str) -> str:
        v = ds._substitute(str(view), werte, strict=True)
        if not _OBJ.match(v):
            raise StarError(500, f"Ungültige View in {DATEI}: {view!r}")
        return v
    dims = {}
    for did, d in (roh.get("dimensionen") or {}).items():
        if not _ID.match(str(d.get("schluessel", ""))):
            raise StarError(500, f"{DATEI}: Dimension {did}: ungültiger Schlüssel {d.get('schluessel')!r}")
        dims[did] = {**d, "id": did, "view": aufloesen(d["view"]), "view_roh": str(d["view"]),
                     "attribute": _attribute(d, did)}
    fakten = {}
    for fid, f in (roh.get("fakten") or {}).items():
        fakten[fid] = {**f, "id": fid, "view": aufloesen(f["view"]), "view_roh": str(f["view"]),
                       "attribute": _attribute(f, fid),
                       "kennzahlen": f.get("kennzahlen") or [], "dimensionen": f.get("dimensionen") or []}
        for r in fakten[fid]["dimensionen"]:
            if r.get("dim") not in dims:
                raise StarError(500, f"{DATEI}: Fakt {fid} verweist auf unbekannte Dimension {r.get('dim')!r}")
            for k in ("rolle", "spalte"):
                if not _ID.match(str(r.get(k, ""))):
                    raise StarError(500, f"{DATEI}: Fakt {fid}, ungültiges {k}: {r.get(k)!r}")
    return {"dimensionen": dims, "fakten": fakten}


def _attribute(node: dict, owner: str) -> list:
    out = []
    for a in node.get("attribute") or []:
        aid = a.get("id") or a.get("spalte")
        if not aid or not _ID.match(aid):
            raise StarError(500, f"{DATEI}: {owner}: ungültiges Attribut {a!r}")
        if a.get("spalte") and not _ID.match(a["spalte"]):
            raise StarError(500, f"{DATEI}: {owner}: ungültige Spalte {a['spalte']!r}")
        out.append({**a, "id": aid.upper()})
    return out


def _widget_fakten(dashboard_id: str, widget_id: str) -> tuple[dict, dict, list]:
    dash = ds._load_dashboard(dashboard_id)
    widget = ds._widget(dash, widget_id)
    if widget.get("typ") != "star-explorer":
        raise StarError(400, f"Widget '{widget_id}' ist kein Star-Explorer")
    ids = (widget.get("optionen") or {}).get("fakten") or []
    defi = _definition()
    fehlend = [f for f in ids if f not in defi["fakten"]]
    if fehlend:
        raise StarError(500, f"Fakten nicht in {DATEI}: {fehlend}")
    return dash, defi, ids


def _alias(rolle: str, belegt: set) -> str:
    """Kurzer, lesbarer Alias je Rolle (Anfangsbuchstaben), eindeutig."""
    teile = [t for t in rolle.lower().split("_") if t]
    kand = "".join(t[0] for t in teile) if len(teile) > 1 else rolle.lower()[:3]
    a, n = kand, 2
    while a in belegt or a == "f":
        a, n = f"{kand}{n}", n + 1
    belegt.add(a)
    return a


def _rollen(defi: dict, fakt: dict) -> list:
    belegt: set = set()
    out = []
    for r in fakt["dimensionen"]:
        dim = defi["dimensionen"][r["dim"]]
        eigen = str(r.get("alias") or "").lower()
        if eigen and _ID.match(eigen) and eigen not in belegt and eigen != "f":
            belegt.add(eigen)
        else:
            eigen = _alias(r["rolle"], belegt)
        out.append({"rolle": r["rolle"], "titel": r.get("titel") or dim.get("titel") or r["rolle"],
                    "dim": dim, "spalte": r["spalte"].upper(), "alias": eigen})
    return out


def _attr_client(a: dict) -> dict:
    return {k: a[k] for k in ("id", "titel", "typ", "auswahl", "beschreibung") if k in a} | \
           {"titel": a.get("titel") or a["id"].replace("_", " ").title(), "typ": a.get("typ", "text")}


def definition(dashboard_id: str, widget_id: str) -> dict:
    """Stern(e) des Widgets für den Client (ohne Ausdrücke)."""
    dash, defi, ids = _widget_fakten(dashboard_id, widget_id)
    out = []
    for fid in ids:
        f = defi["fakten"][fid]
        out.append({
            "id": fid, "titel": f.get("titel", fid), "view": f["view"], "beschreibung": f.get("beschreibung"),
            "alias": "f",
            "attribute": [_attr_client(a) for a in f["attribute"]],
            "kennzahlen": [{"id": k["id"], "titel": k.get("titel", k["id"]), "spalte": k.get("spalte"),
                            "agg": [{"id": g, "titel": AGG[g][0]} for g in (k.get("agg") or ["count"]) if g in AGG],
                            "standard": bool(k.get("standard"))}
                           for k in f["kennzahlen"]],
            "dimensionen": [{"rolle": r["rolle"], "titel": r["titel"], "dim": r["dim"]["id"],
                             "dim_titel": r["dim"].get("titel"), "view": r["dim"]["view"],
                             "schluessel": r["dim"]["schluessel"], "spalte": r["spalte"], "alias": r["alias"],
                             "attribute": [_attr_client(a) for a in r["dim"]["attribute"]]}
                            for r in _rollen(defi, f)],
        })
    return {"fakten": out, "min_zelle": ds._min_zelle(dash), "max_gruppen": MAX_GRUPPEN}


# ---------------------------------------------------------------------------
# Abfrage bauen
# ---------------------------------------------------------------------------

def _ausdruck(a: dict, alias: str) -> str:
    if a.get("ausdruck"):
        return str(a["ausdruck"]).replace("{a}", alias)
    return f"{alias}.{a.get('spalte', a['id']).upper()}"


def _finde(fakt: dict, rollen: list, rolle: str, attr: str) -> tuple[dict, str, str, Optional[dict]]:
    """(Attribut, Alias, Titel der Rolle, Rolle oder None für den Fakt)."""
    if rolle in ("", "fakt", None):
        for a in fakt["attribute"]:
            if a["id"] == str(attr).upper():
                return a, "f", fakt.get("titel", fakt["id"]), None
    else:
        for r in rollen:
            if r["rolle"] == rolle:
                for a in r["dim"]["attribute"]:
                    if a["id"] == str(attr).upper():
                        return a, r["alias"], r["titel"], r
    raise StarError(400, f"Attribut nicht freigegeben: {rolle}.{attr}")


def _wert(a: dict, v: Any) -> Any:
    typ = a.get("typ", "text")
    if v is None or v == "":
        raise StarError(400, f"Filter {a['id']}: Wert fehlt")
    try:
        if typ == "zahl":
            f = float(v)
            return int(f) if f.is_integer() else f
        if typ == "datum":
            return _dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        raise StarError(400, f"Filter {a['id']}: ungültiger Wert {v!r} für Typ {typ}")
    return str(v)


def baue(defi: dict, fakt: dict, auswahl: dict, r_vorlage: bool = False) -> dict:
    """SQL mit Bind-Parametern aus der Auswahl:
    {gruppen: [{rolle, attr}], filter: [{rolle, attr, op, werte}], kennzahlen: [{id, agg}]}.
    r_vorlage: Views mit Platzhaltern (${CON_ACCESS}) und Filterwerte als ${FILTER:<id>}
    statt ?, für das R-Gerüst; die Werte stehen dann in r_filter."""
    r_filter: list = []
    view = (lambda node: node["view_roh"]) if r_vorlage else (lambda node: node["view"])
    rollen = _rollen(defi, fakt)
    mehrfach = {r["dim"]["id"] for r in rollen if sum(x["dim"]["id"] == r["dim"]["id"] for x in rollen) > 1}
    genutzt: dict = {}           # rolle -> Rolle (nur JOINs, die gebraucht werden)
    select, group, spalten, params = [], [], [], []
    namen: set = set()

    def spaltenname(basis: str) -> str:
        n, i = basis[:60], 2
        while n in namen:
            n, i = f"{basis[:57]}_{i}", i + 1
        namen.add(n)
        return n

    for g in (auswahl.get("gruppen") or [])[:12]:
        a, alias, rtitel, r = _finde(fakt, rollen, g.get("rolle"), g.get("attr"))
        if r:
            genutzt[r["rolle"]] = r
        expr = _ausdruck(a, alias)
        # Rolle nur voranstellen, wo dieselbe Dimension mehrfach am Fakt hängt (z. B. zwei Datumsrollen)
        name = spaltenname((f"{r['rolle']}_" if r and r["dim"]["id"] in mehrfach else "") + a["id"]).upper()
        select.append(f"{expr} AS {name}")
        group.append(expr)
        spalten.append({"name": name, "titel": a.get("titel") or a["id"], "rolle": rtitel, "art": "gruppe",
                        "typ": a.get("typ", "text")})

    kz_def = {k["id"]: k for k in fakt["kennzahlen"]}
    kennzahlen = auswahl.get("kennzahlen") or [{"id": k["id"], "agg": (k.get("agg") or ["count"])[0]}
                                               for k in fakt["kennzahlen"] if k.get("standard")]
    for k in kennzahlen[:12]:
        kd = kz_def.get(k.get("id"))
        agg = k.get("agg") or ((kd or {}).get("agg") or ["count"])[0]
        if not kd or agg not in (kd.get("agg") or ["count"]) or agg not in AGG:
            raise StarError(400, f"Kennzahl nicht freigegeben: {k}")
        s = f"f.{kd['spalte'].upper()}" if kd.get("spalte") else "*"
        if s != "*" and not _ID.match(kd["spalte"]):
            raise StarError(500, f"Ungültige Spalte in Kennzahl {kd['id']}")
        expr = AGG[agg][1].format(s=s)
        name = spaltenname((kd["id"] if agg == "count" else f"{agg}_{kd['id']}").upper())
        select.append(f"{expr} AS {name}")
        spalten.append({"name": name, "titel": f"{AGG[agg][0]} {kd.get('titel', kd['id'])}"
                        if agg not in ("count",) else kd.get("titel", kd["id"]),
                        "art": "kennzahl", "agg": agg, "typ": "zahl"})
    # Faktzeilen je Gruppe für die Maskierung: eine gewählte COUNT(*)-Kennzahl oder eigene Kontrollspalte
    kontrolle = next((i for i, sp in enumerate(spalten) if sp.get("agg") == "count"), None)
    if kontrolle is None:
        select.append("COUNT(*) AS ZEILEN_IM_FAKT")
        spalten.append({"name": "ZEILEN_IM_FAKT", "titel": "Zeilen im Fakt", "art": "kontrolle", "agg": "count", "typ": "zahl"})
        kontrolle = len(spalten) - 1

    where, where_kommentar = [], []
    for fl in (auswahl.get("filter") or [])[:30]:
        a, alias, rtitel, r = _finde(fakt, rollen, fl.get("rolle"), fl.get("attr"))
        if r:
            genutzt[r["rolle"]] = r
        op = fl.get("op", "eq")
        if op not in OPS:
            raise StarError(400, f"Unbekannter Operator {op!r}")
        expr = _ausdruck(a, alias)
        werte = fl.get("werte")
        werte = werte if isinstance(werte, list) else ([] if werte is None else [werte])
        basis = f"{fl.get('rolle') or 'fakt'}_{a['id']}".lower()

        def ph(wert, nr=None):
            """Platzhalter für einen Filterwert: ? (Bind-Parameter) oder ${FILTER:id} (R)."""
            if not r_vorlage:
                params.append(wert)
                return "?"
            fid = basis if nr is None else f"{basis}_{nr}"
            r_filter.append({"id": fid, "titel": f"{rtitel}: {a.get('titel') or a['id']}", "typ": a.get("typ", "text"),
                             "wert": wert})
            return "${FILTER:" + fid + "}"
        if op == "null":
            where.append(f"{expr} IS NULL")
        elif op == "notnull":
            where.append(f"{expr} IS NOT NULL")
        elif op in ("in", "eq") and len(werte) > 1:
            werte = werte[:200]
            where.append(f"{expr} IN ({', '.join(ph(_wert(a, w), i + 1) for i, w in enumerate(werte))})")
        elif op == "between":
            if len(werte) != 2:
                raise StarError(400, f"Filter {a['id']}: von–bis braucht zwei Werte")
            where.append(f"{expr} BETWEEN {ph(_wert(a, werte[0]), 'von')} AND {ph(_wert(a, werte[1]), 'bis')}")
        elif op == "like":
            where.append(f"UPPER({expr}) LIKE UPPER({ph('%' + str(_wert({**a, 'typ': 'text'}, werte[0] if werte else '')) + '%')})")
        else:
            sym = {"eq": "=", "in": "=", "ne": "<>", "ge": ">=", "le": "<="}[op]
            where.append(f"{expr} {sym} {ph(_wert(a, werte[0] if werte else None))}")
        where_kommentar.append(rtitel)

    # Lesbares SQL mit Kommentaren (so wird es auch ausgeführt)
    z = [f"-- Fakt: {fakt.get('titel', fakt['id'])}"]
    z.append("SELECT")
    z += [f"    {s}," for s in select[:-1]] + [f"    {select[-1]}"]
    z.append(f"FROM {view(fakt)} f")
    for r in rollen:
        if r["rolle"] in genutzt:
            z.append(f"-- Dimension {r['titel']}")
            z.append(f"LEFT JOIN {view(r['dim'])} {r['alias']}")
            z.append(f"    ON {r['alias']}.{r['dim']['schluessel']} = f.{r['spalte']}")
    if where:
        z.append("WHERE " + "\n  AND ".join(f"{w}  -- {k}" for w, k in zip(where, where_kommentar)))
    if group:
        z.append("GROUP BY " + ", ".join(group))
        z.append("ORDER BY " + ", ".join(str(i + 1) for i in range(len(group))))
    sql = "\n".join(z)
    return {"sql": sql, "params": params, "spalten": spalten, "kontrolle": kontrolle, "r_filter": r_filter,
            "joins": [r["rolle"] for r in rollen if r["rolle"] in genutzt]}


def abfrage(dashboard_id: str, widget_id: str, fakt_id: str, auswahl: dict,
            offset: int = 0, limit: int = 100, ausfuehren: bool = True) -> dict:
    dash, defi, ids = _widget_fakten(dashboard_id, widget_id)
    if fakt_id not in ids:
        raise StarError(400, f"Fakt '{fakt_id}' gehört nicht zu diesem Widget")
    fakt = defi["fakten"][fakt_id]
    q = baue(defi, fakt, auswahl or {})
    out = {"sql": q["sql"], "sql_mit_werten": sql_analyse.mit_werten(q["sql"], q["params"]),
           "spalten": q["spalten"], "joins": q["joins"]}
    if not ausfuehren:
        return out

    digest = hashlib.sha1(f"{q['sql']}|{json.dumps(q['params'], default=str)}".encode()).hexdigest()
    key = f"dash::{dashboard_id}::stern::{digest}"
    def _laden():
        t0 = time.monotonic()
        res = td_readonly.query(q["sql"], q["params"], MAX_GRUPPEN, art="daten")
        res["laufzeit_ms"] = int((time.monotonic() - t0) * 1000)
        return res
    try:
        res, cache = td_readonly.cached(key, _laden, CACHE_TTL)
    except td_readonly.ReadOnlyViolation as e:
        raise StarError(500, str(e))
    except Exception as e:
        logger.warning("Star-Explorer %s/%s: %s", dashboard_id, widget_id, str(e).splitlines()[0])
        raise StarError(502, f"Abfrage fehlgeschlagen: {str(e).splitlines()[0]}")

    limit = max(1, min(int(limit), MAX_SEITE))
    offset = max(0, int(offset))
    zeilen = res["rows"][offset:offset + limit]
    grenze = ds._min_zelle(dash)
    maskiert = 0
    if grenze:
        idx_kontrolle = q["kontrolle"]
        idx_kz = [i for i, s in enumerate(q["spalten"]) if s["art"] in ("kennzahl", "kontrolle")]
        idx_zaehl = [i for i, s in enumerate(q["spalten"]) if s.get("agg") in ZAEHLEND]
        neu = []
        for r in zeilen:
            r = list(r)
            klein = isinstance(r[idx_kontrolle], (int, float)) and 0 < r[idx_kontrolle] < grenze
            for i in idx_kz:
                if klein or (i in idx_zaehl and isinstance(r[i], (int, float)) and 0 < r[i] < grenze):
                    r[i] = None
                    maskiert += 1
            neu.append(r)
        zeilen = neu
    out.update({
        "zeilen": zeilen, "offset": offset, "gesamt": len(res["rows"]),
        "abgeschnitten": res["truncated"], "maskiert": maskiert, "min_zelle": grenze,
        "cache": cache, "laufzeit_ms": res.get("laufzeit_ms"),
    })
    return out


def r_code(dashboard_id: str, widget_id: str, fakt_id: str, auswahl: dict) -> dict:
    """R-Gerüst zur aktuellen Auswahl: dieselbe Vorlage wie bei den übrigen Widgets
    (widget.R: DEF-Block mit Umgebungen DEV/INT/PRD, Excel-Export wie QL1).
    Datenbanknamen als ${VAR}, Filterwerte als ${FILTER:id} – das Skript setzt sie
    aus dem DEF-Block ein."""
    from app.services import r_skelett
    dash, defi, ids = _widget_fakten(dashboard_id, widget_id)
    if fakt_id not in ids:
        raise StarError(400, f"Fakt '{fakt_id}' gehört nicht zu diesem Widget")
    fakt = defi["fakten"][fakt_id]
    q = baue(defi, fakt, auswahl or {}, r_vorlage=True)
    grenze = ds._min_zelle(dash)
    widget = {
        "id": f"{widget_id}_{fakt_id}", "typ": "table",   # Excel: <dashboard>_<widget>_<fakt>_<Datum>…
        "titel": f"Star-Explorer {fakt.get('titel', fakt_id)}",
        "erlaeuterung": (f"Abfrage aus dem Star-Explorer auf dem Fakt {fakt.get('titel', fakt_id)}. "
                         + (fakt.get("beschreibung") or "")),
        "hinweise": [f"Im Dashboard werden Gruppen unter {grenze} Faktzeilen maskiert; dieses Skript "
                     f"liefert die ungekürzten Werte. Vor der Weitergabe kleine Gruppen ausblenden."] if grenze else [],
    }
    umg = ds._root() / "umgebungen.yml"
    r_umg = (ds._load_yaml(umg).get("r_umgebungen") or {}) if umg.exists() else {}
    fdefs = {f["id"]: {"id": f["id"], "titel": f["titel"], "typ": f["typ"]} for f in q["r_filter"]}
    werte_ = {f["id"]: f["wert"] for f in q["r_filter"]}
    code = r_skelett.erzeuge(dash, widget, q["sql"], werte_, fdefs, r_umg, ds.variables, ds._root(), "")
    return {"r_code": code, "dateiname": f"{dashboard_id}_{fakt_id}.R"}


def voller_stern_sql(dashboard_id: str, widget_id: str) -> str:
    """Je Fakt des Widgets ein SELECT über den vollständigen Stern (alle Dimensionen) –
    Grundlage für Datenmodell, Joins und Herkunft im Info-Panel."""
    _, defi, ids = _widget_fakten(dashboard_id, widget_id)
    teile = []
    for fid in ids:
        f = defi["fakten"][fid]
        z = [f"-- Fakt {f.get('titel', fid)}: vollständiger Stern", "SELECT COUNT(*)", f"FROM {f['view']} f"]
        for r in _rollen(defi, f):
            z.append(f"LEFT JOIN {r['dim']['view']} {r['alias']}  -- {r['titel']}")
            z.append(f"    ON {r['alias']}.{r['dim']['schluessel']} = f.{r['spalte']}")
        teile.append("\n".join(z))
    return ";\n\n".join(teile)


def werte(dashboard_id: str, widget_id: str, fakt_id: str, rolle: str, attr: str) -> dict:
    """Werte eines Attributs mit auswahl: true (für die Filter-Auswahlliste)."""
    dash, defi, ids = _widget_fakten(dashboard_id, widget_id)
    if fakt_id not in ids:
        raise StarError(400, f"Fakt '{fakt_id}' gehört nicht zu diesem Widget")
    fakt = defi["fakten"][fakt_id]
    a, alias, _, r = _finde(fakt, _rollen(defi, fakt), rolle, attr)
    if not a.get("auswahl"):
        raise StarError(400, f"Attribut {attr} hat keine Auswahlliste")
    view = r["dim"]["view"] if r else fakt["view"]
    expr = _ausdruck(a, "x")
    sql = f"SELECT DISTINCT {expr} AS WERT FROM {view} x WHERE {expr} IS NOT NULL ORDER BY 1"
    key = f"dash::{dashboard_id}::stern::werte::{view}::{expr}"
    try:
        res, _ = td_readonly.cached(key, lambda: td_readonly.query(sql, [], MAX_WERTE, art="daten"), WERTE_TTL)
    except Exception as e:
        raise StarError(502, f"Werte nicht lesbar: {str(e).splitlines()[0]}")
    return {"werte": [row[0] for row in res["rows"]], "abgeschnitten": res["truncated"]}
