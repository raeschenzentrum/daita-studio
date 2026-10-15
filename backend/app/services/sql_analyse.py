"""
SQL-Analyse für das Info-Panel der Dashboards.

- erlaeuterung(sql)   Kommentarblock am Anfang einer SQL-Datei als Text
- objekte(sql)        gelesene Objekte (DB.OBJEKT nach FROM/JOIN) mit Alias
- joins(sql, objs)    Join-Bedingungen „a.X = b.Y“ als Objekt-/Spaltenpaare
- art(name)           Fakt / Dimension / Objekt nach Namenskonvention
- herkunft(objekte)   Kette der View-Definitionen bis zu den Tabellen
                      (DBC.TablesV / DBC.TableTextV über die Meta-Verbindung)
- mit_werten(sql, p)  SQL mit eingesetzten Bind-Parametern – NUR zur Anzeige

Die Analyse ist bewusst einfach (reguläre Ausdrücke, keine SQL-Grammatik):
Sie soll beim Lesen helfen, nicht das SQL validieren.
"""

import datetime as _dt
import re
from typing import Optional

from app.services import td_readonly

_IDENT = r"[A-Za-z0-9_$#]+"
_OBJ_RE = re.compile(
    rf"\b(FROM|JOIN)\s+({_IDENT})\.({_IDENT})(?:\s+(?:AS\s+)?(?!ON\b|WHERE\b|LEFT\b|RIGHT\b|INNER\b|FULL\b|CROSS\b|JOIN\b|GROUP\b|ORDER\b|UNION\b|QUALIFY\b)({_IDENT}))?",
    re.I,
)
_JOIN_RE = re.compile(rf"\b({_IDENT})\.({_IDENT})\s*=\s*({_IDENT})\.({_IDENT})")
_KOMMENTAR_RE = re.compile(r"--[^\r\n]*|/\*.*?\*/", re.S)   # Teradata-View-Texte trennen Zeilen mit \r

# Namenskonvention (kundenneutral, Kimball-üblich)
_FAKT_RE = re.compile(r"^(V_)?(FACT|FCT|F)_", re.I)
_DIM_RE = re.compile(r"^(V_)?(DIM|D)_", re.I)

MAX_TIEFE = 8


def erlaeuterung(sql: str) -> Optional[str]:
    """Zusammenhängende Kommentarzeilen (--) am Anfang der Datei als Fließtext."""
    zeilen = []
    for z in sql.splitlines():  # erkennt \n, \r\n und \r
        s = z.strip()
        if s.startswith("--"):
            zeilen.append(s[2:].strip())
        elif not s and not zeilen:
            continue
        else:
            break
    text = " ".join(z for z in zeilen if z)
    return text or None


def art(name: str) -> str:
    if _FAKT_RE.match(name):
        return "Fakt"
    if _DIM_RE.match(name):
        return "Dimension"
    return "Objekt"


def objekte(sql: str) -> list[dict]:
    """[{objekt, db, name, alias, art}] in Reihenfolge des ersten Auftretens."""
    ohne = _KOMMENTAR_RE.sub(" ", sql)
    out: dict = {}
    for m in _OBJ_RE.finditer(ohne):
        # FROM innerhalb einer Funktion (EXTRACT(YEAR FROM x.D), TRIM(BOTH FROM …)) überspringen
        if m.group(1).upper() == "FROM" and re.search(r"\(\s*\w+\s*$", ohne[:m.start()]):
            continue
        db, name, alias = m.group(2), m.group(3), m.group(4)
        key = f"{db}.{name}".upper()
        e = out.setdefault(key, {"objekt": key, "db": db.upper(), "name": name.upper(),
                                 "aliase": [], "art": art(name)})
        if alias and alias.lower() not in e["aliase"]:
            e["aliase"].append(alias.lower())
    return list(out.values())


def joins(sql: str, objs: list[dict]) -> list[dict]:
    """Join-Paare über Aliase: [{links, links_spalte, rechts, rechts_spalte}]."""
    alias = {a: o["objekt"] for o in objs for a in o["aliase"]}
    ohne = _KOMMENTAR_RE.sub(" ", sql)
    out, gesehen = [], set()
    for m in _JOIN_RE.finditer(ohne):
        a1, c1, a2, c2 = m.group(1).lower(), m.group(2).upper(), m.group(3).lower(), m.group(4).upper()
        if a1 in alias and a2 in alias and alias[a1] != alias[a2]:
            k = tuple(sorted([(alias[a1], c1), (alias[a2], c2)]))
            if k in gesehen:
                continue
            gesehen.add(k)
            out.append({"links": alias[a1], "links_spalte": c1, "rechts": alias[a2], "rechts_spalte": c2})
    return out


def _view_text(conn, db: str, name: str) -> tuple[Optional[str], Optional[str]]:
    """(TableKind, vollständiger View-Text) über die Meta-Verbindung."""
    r = td_readonly.query(
        "SELECT TableKind, RequestText FROM DBC.TablesV WHERE DatabaseName = ? AND TableName = ?",
        [db, name], 1, conn)["rows"]
    if not r:
        return None, None
    kind, text = (r[0][0] or "").strip(), r[0][1]
    if kind == "V" and (text is None or len(text) >= 12500):
        teile = td_readonly.query(
            "SELECT RequestText FROM DBC.TableTextV WHERE DatabaseName = ? AND TableName = ? ORDER BY LineNo",
            [db, name], 10000, conn)["rows"]
        if teile:
            text = "".join(t[0] or "" for t in teile)
    return kind, text


def herkunft(objs: list[str]) -> list[dict]:
    """Baum der Herkunft je Objekt: {objekt, art, quellen: [...]}; Views werden
    über ihre Definition aufgelöst, Tabellen sind Blätter. Mehrfach erreichte
    Objekte werden nur einmal aufgelöst (danach als Verweis 'siehe oben')."""
    def _load():
        cache: dict = {}
        with td_readonly.connection("meta") as conn:
            def knoten(obj: str, tiefe: int, pfad: tuple) -> dict:
                db, name = obj.split(".", 1)
                if obj in pfad or tiefe > MAX_TIEFE:
                    return {"objekt": obj, "art": "…", "quellen": [], "abgeschnitten": True}
                if obj in cache:
                    return {"objekt": obj, "art": cache[obj]["art"], "quellen": [], "verweis": True}
                kind, text = _view_text(conn, db, name)
                eintrag = {"objekt": obj,
                           "art": {"V": "View", "T": "Tabelle", "O": "Tabelle", None: "unbekannt"}.get(kind, kind),
                           "quellen": []}
                cache[obj] = eintrag
                if kind == "V" and text:
                    for q in objekte(text):
                        if q["objekt"] != obj:
                            eintrag["quellen"].append(knoten(q["objekt"], tiefe + 1, pfad + (obj,)))
                return eintrag
            return [knoten(o, 0, ()) for o in objs]

    key = "dashboards::herkunft::" + "|".join(sorted(objs))
    daten, _ = td_readonly.cached(key, _load, 1800)
    return daten


def _literal(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, _dt.datetime):
        return f"TIMESTAMP '{v.isoformat(sep=' ')}'"
    if isinstance(v, _dt.date):
        return f"DATE '{v.isoformat()}'"
    return "'" + str(v).replace("'", "''") + "'"


def mit_werten(sql: str, params: list) -> str:
    """Setzt Bind-Parameter (?) außerhalb von Zeichenketten als Literale ein – nur Anzeige."""
    out, i, in_str = [], 0, False
    for ch in sql:
        if ch == "'":
            in_str = not in_str
        if ch == "?" and not in_str and i < len(params):
            out.append(_literal(params[i]))
            i += 1
        else:
            out.append(ch)
    return "".join(out)
