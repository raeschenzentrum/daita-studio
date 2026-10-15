"""
Paketformat für das Deployment auf air-gapped Zielserver.

Ein Paket ist ein ZIP mit
    manifest.json            Kopf, Inhalt, Reihenfolge
    pruefsummen.sha256       sha256 je Datei (auch manifest.json)
    <teil>/...               Inhalt je Paketart

Konzept: daita-studio/docs/PAKET_DEPLOYMENT_KONZEPT.md
Python 3.6 kompatibel; braucht nur die Standardbibliothek.
"""
import base64
import datetime as _dt
import hashlib
import json
import re
import zipfile
from decimal import Decimal
from pathlib import Path

FORMAT = 1
MANIFEST = "manifest.json"
PRUEFSUMMEN = "pruefsummen.sha256"

# Reihenfolge der Teile beim Einspielen (Abhängigkeiten, Konzept Abschnitt 8)
REIHENFOLGE = ["software", "metaschema", "rechte", "strukturen", "vorlagen", "jobs", "dashboards"]


# ---------------------------------------------------------------------------
# Werte (typerhaltend, JSON-fähig; wie tools/meta_transfer/_meta_common.py)
# ---------------------------------------------------------------------------
def wert_aus_db(v):
    """DB-Wert -> JSON-Wert; Sondertypen als Marker-Dict."""
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, str):
        return v
    if isinstance(v, Decimal):
        return {"__dec__": str(v)}
    if isinstance(v, _dt.datetime):
        return {"__ts__": v.isoformat()}
    if isinstance(v, _dt.date):
        return {"__da__": v.isoformat()}
    if isinstance(v, _dt.time):
        return {"__ti__": v.isoformat()}
    if isinstance(v, (bytes, bytearray)):
        return {"__b64__": base64.b64encode(bytes(v)).decode("ascii")}
    return str(v)


def _zeit(text, mit_datum):
    for fmt in (("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S") if mit_datum else ("%H:%M:%S.%f", "%H:%M:%S")):
        try:
            return _dt.datetime.strptime(text, fmt)
        except ValueError:
            pass
    raise ValueError("Zeitwert nicht lesbar: {}".format(text))


def wert_fuer_db(v):
    """JSON-Wert -> Bindewert für teradatasql."""
    if isinstance(v, dict):
        if "__dec__" in v:
            return Decimal(v["__dec__"])
        if "__ts__" in v:
            return _zeit(v["__ts__"], True)
        if "__da__" in v:
            return _dt.datetime.strptime(v["__da__"], "%Y-%m-%d").date()
        if "__ti__" in v:
            return _zeit(v["__ti__"], False).time()
        if "__b64__" in v:
            return base64.b64decode(v["__b64__"])
    return v


def sha256(daten):
    if isinstance(daten, str):
        daten = daten.encode("utf-8")
    return hashlib.sha256(daten).hexdigest()


def sha256_datei(pfad):
    h = hashlib.sha256()
    with open(str(pfad), "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ndjson(zeilen):
    """Liste von Wertelisten -> NDJSON-Text (eine Zeile je Datensatz)."""
    return "".join(json.dumps(z, ensure_ascii=False, sort_keys=True) + "\n" for z in zeilen)


# ---------------------------------------------------------------------------
# Schreiben
# ---------------------------------------------------------------------------
class PaketSchreiber:
    """Sammelt Dateien in einem ZIP; abschliessen() schreibt Manifest und Prüfsummen."""

    def __init__(self, pfad):
        self.pfad = Path(pfad)
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self._zip = zipfile.ZipFile(str(self.pfad), "w", zipfile.ZIP_DEFLATED)
        self.summen = {}

    def text(self, name, inhalt):
        daten = inhalt.encode("utf-8")
        self._zip.writestr(name, daten)
        self.summen[name] = sha256(daten)
        return self.summen[name]

    def datei(self, name, quelle):
        self._zip.write(str(quelle), name)
        self.summen[name] = sha256_datei(quelle)
        return self.summen[name]

    def abschliessen(self, manifest):
        """Schreibt manifest.json und pruefsummen.sha256; gibt den Inhalts-Hash zurück."""
        manifest["inhalt_hash"] = sha256("".join(
            "{} {}\n".format(s, n) for n, s in sorted(self.summen.items())))
        self.text(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        self._zip.writestr(PRUEFSUMMEN, "".join(
            "{}  {}\n".format(s, n) for n, s in sorted(self.summen.items())))
        self._zip.close()
        return manifest["inhalt_hash"]


# ---------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------
class PaketFehler(Exception):
    pass


class Paket:
    """Liest ein Paket und prüft alle Prüfsummen beim Öffnen."""

    def __init__(self, pfad):
        self.pfad = Path(pfad)
        if not self.pfad.exists():
            raise PaketFehler("Paket nicht gefunden: {}".format(self.pfad))
        try:
            self._zip = zipfile.ZipFile(str(self.pfad))
            self._pruefen()
        except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as e:
            raise PaketFehler("Paket nicht lesbar ({}): {}".format(self.pfad.name, e))

    def _pruefen(self):
        namen = set(self._zip.namelist())
        if PRUEFSUMMEN not in namen or MANIFEST not in namen:
            raise PaketFehler("{} oder {} fehlt im Paket".format(MANIFEST, PRUEFSUMMEN))
        soll = {}
        for zeile in self._zip.read(PRUEFSUMMEN).decode("utf-8").splitlines():
            if zeile.strip():
                s, n = zeile.split("  ", 1)
                soll[n] = s
        fehler = []
        for n, s in soll.items():
            if n not in namen:
                fehler.append("fehlt: " + n)
            elif sha256(self._zip.read(n)) != s:
                fehler.append("Prüfsumme falsch: " + n)
        fremd = namen - set(soll) - {PRUEFSUMMEN}
        fehler += ["nicht in den Prüfsummen: " + n for n in sorted(fremd) if not n.endswith("/")]
        if fehler:
            raise PaketFehler("Paket beschädigt:\n  " + "\n  ".join(fehler))
        self.summen = soll
        self.manifest = json.loads(self._zip.read(MANIFEST).decode("utf-8"))
        if self.manifest.get("format") != FORMAT:
            raise PaketFehler("Paketformat {} wird nicht unterstützt (erwartet {})".format(
                self.manifest.get("format"), FORMAT))

    def teile(self):
        return [t for t in REIHENFOLGE if t in self.manifest.get("inhalt", {})]

    def text(self, name):
        return self._zip.read(name).decode("utf-8")

    def bytes(self, name):
        return self._zip.read(name)

    def zeilen(self, name):
        return [json.loads(z) for z in self.text(name).splitlines() if z.strip()]


# ---------------------------------------------------------------------------
# DDL-Text (SHOW TABLE / SHOW VIEW)
# ---------------------------------------------------------------------------
def _top_level_split(text, trenner=","):
    """Teilt an Trennzeichen auf Klammerebene 0, Literale und Bezeichner in Anführungszeichen bleiben ganz."""
    teile, tiefe, start, i, n = [], 0, 0, 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"":
            j = i + 1
            while j < n:
                if text[j] == c:
                    if j + 1 < n and text[j + 1] == c:
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
            continue
        if c == "(":
            tiefe += 1
        elif c == ")":
            tiefe -= 1
        elif c == trenner and tiefe == 0:
            teile.append(text[start:i])
            start = i + 1
        i += 1
    teile.append(text[start:])
    return teile


def _klammer_ende(text, start):
    """Index der schließenden Klammer zur öffnenden bei start."""
    tiefe, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c in "'\"":
            j = i + 1
            while j < n and text[j] != c:
                j += 1
            i = j + 1
            continue
        if c == "(":
            tiefe += 1
        elif c == ")":
            tiefe -= 1
            if tiefe == 0:
                return i
        i += 1
    raise ValueError("Klammer nicht geschlossen")


def norm(text):
    """Leerraum zusammenfassen, Großschreibung, ohne abschließendes Semikolon."""
    text = re.sub(r"\s+", " ", text.replace("\r", "\n")).strip()
    return text.rstrip(";").strip().upper()


_CONSTRAINT = ("CONSTRAINT", "PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "INDEX")


def tabelle_zerlegen(ddl):
    """SHOW TABLE -> {art, optionen, spalten: [(NAME, def)], constraints, index}.

    art: SET/MULTISET (+ VOLATILE/GLOBAL TEMPORARY), optionen: Tabellenoptionen
    (FALLBACK, JOURNAL, MAP ...; werden nur angezeigt, nicht verglichen).
    """
    ddl = ddl.replace("\r", "\n")
    auf = ddl.index("(")
    zu = _klammer_ende(ddl, auf)
    kopf, koerper, rest = ddl[:auf], ddl[auf + 1:zu], ddl[zu + 1:]
    m = re.match(r"\s*CREATE\s+(.*?)\s*TABLE\s+(\S+)\s*(.*)$", kopf, re.I | re.S)
    if not m:
        raise ValueError("kein CREATE TABLE: " + kopf[:80])
    spalten, constraints = [], []
    for teil in _top_level_split(koerper):
        teil = re.sub(r"\s+", " ", teil).strip()
        if not teil:
            continue
        erstes = teil.split(" ", 1)[0].upper()
        if erstes in _CONSTRAINT:
            constraints.append(teil.upper())
            continue
        mm = re.match(r'("(?:[^"]|"")+"|\S+)\s*(.*)$', teil)
        spalten.append((mm.group(1).strip('"').upper(), mm.group(2).strip()))
    return {
        "art": norm(m.group(1) or "SET"),
        "optionen": norm(m.group(3)).strip(", "),
        "spalten": spalten,
        "constraints": constraints,
        "index": norm(rest),
    }


def tabelle_signatur(ddl):
    """Vergleichswert einer Tabelle: Art, Spalten, Constraints, Index (ohne Optionen)."""
    t = tabelle_zerlegen(ddl)
    return sha256(json.dumps([t["art"], [(n, norm(d)) for n, d in t["spalten"]],
                              t["constraints"], t["index"]]))


def view_als_replace(ddl):
    """SHOW VIEW -> REPLACE VIEW ... (Kommentare vor dem Kopf bleiben)."""
    return re.sub(r"\b(CREATE|REPLACE)\s+VIEW\b", "REPLACE VIEW", ddl.replace("\r", "\n"), count=1, flags=re.I)


def view_signatur(ddl):
    return sha256(norm(view_als_replace(ddl)))
