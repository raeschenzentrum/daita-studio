"""
R-Codegerüst zu einem Dashboard-Widget (Info-Panel).

Der Rahmen steht in R-Vorlagen (cfg/r_vorlagen/widget.R, katalog.R; ein Einsatz
kann sie in <Dashboard-Ablage>/r_vorlagen/ ersetzen). Dieses Modul bereitet nur
die Werte auf (DEF-Block, SQL, Kommentare, Plot-Vorschlag) und setzt sie ein.

Erzeugt ein lauffähiges R-Skript nach den Skriptregeln der Einsätze:
- EIN Definitionsblock (DEF) oben ist die einzige Anpassstelle,
- Umgebungen DEV / INT / PRD mit je DB-Verbindung und Datenbanknamen,
- keine Umgebungsvariablen, keine interaktiven Eingaben,
- keine Zugangsdaten im Code (Platzhalter "TODO", das Skript bricht mit
  Hinweis auf die DEF-Stelle ab, solange einer gesetzt ist),
- das SQL steht als Vorlage im Skript: ${NAME} = Datenbank aus DEF,
  ${FILTER:id} = Wert aus DEF$filter; das ausgeführte SQL wird ausgegeben.

Welche Studio-Umgebung zu DEV/INT/PRD gehört, steht optional in
umgebungen.yml der Dashboard-Ablage:

    r_umgebungen:
      DEV: umgebung_a                  # ID aus cfg/environments.yml
      INT:                             # oder direkt (ohne Studio-Umgebung):
        host: db-int.example.org
        logmech: KRB5                  # Kerberos statt user/password
        variablen: {DB_ZUGRIFF: KUNDE_INT_CON_ACCESS}

Ohne Angabe wird die aktive Umgebung als DEV eingetragen.
"""

import datetime as _dt
import re
from pathlib import Path
from typing import Any, Optional

from app import config as cfg

R_UMGEBUNGEN = ("DEV", "INT", "PRD")
_PH = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([A-Za-z0-9_-]+))?\}")


def _r_str(s: Any) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _r_wert(v: Any, typ: Optional[str]) -> str:
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return f"{v}L"
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, _dt.date):
        return f'as.Date("{v.isoformat()}")'
    return _r_str(v)


def _kommentar(text: str, breite: int = 76) -> list[str]:
    zeilen, akt = [], ""
    for wort in str(text).split():
        if len(akt) + len(wort) + 1 > breite:
            zeilen.append("# " + akt)
            akt = wort
        else:
            akt = f"{akt} {wort}".strip()
    if akt:
        zeilen.append("# " + akt)
    return zeilen


def _umgebungs_zuordnung(r_umg: dict) -> dict:
    zuordnung = {k: v for k, v in (r_umg or {}).items() if k in R_UMGEBUNGEN}
    if not zuordnung:
        zuordnung = {"DEV": cfg.get_active_env_id()}
    return zuordnung


def _variablen_fuer(env_id: Optional[str], namen: list[str], variablen_fn) -> dict:
    """Datenbank-Variablen einer Studio-Umgebung (über deren Meta-Verbindung)."""
    if not env_id or env_id not in cfg.ENVIRONMENTS:
        return {}
    token = cfg._active_env_id_var.set(env_id)
    try:
        werte = variablen_fn()
    except Exception:
        werte = {}
    finally:
        cfg._active_env_id_var.reset(token)
    return {n: werte[n] for n in namen if n in werte}


def _ggplot_vorschlag(widget: dict, spalten: list[str]) -> list[str]:
    typ, o = widget.get("typ"), widget.get("optionen") or {}
    x, y, serie = o.get("x"), o.get("y"), o.get("serie")
    zeilen: list[str] = []
    if typ == "bar" and x and y and not isinstance(y, list):
        pos = '"stack"' if o.get("gestapelt") else '"dodge"'
        fill = f", fill = {serie}" if serie else ""
        zeilen += ["# library(ggplot2)",
                   f"# ggplot(daten, aes(x = {x}, y = {y}{fill})) +",
                   f"#   geom_col(position = {pos})" + (" +" if o.get("horizontal") else ""),
                   ]
        if o.get("horizontal"):
            zeilen.append("#   coord_flip()")
    elif typ == "line" and x and y:
        if isinstance(y, list):
            zeilen += ["# library(ggplot2); library(tidyr)",
                       f"# daten %>% pivot_longer(c({', '.join(y)}), names_to = \"KENNZAHL\", values_to = \"WERT\") %>%",
                       f"#   ggplot(aes(x = {x}, y = WERT, colour = KENNZAHL)) + geom_line()"]
        else:
            farbe = f", colour = {serie}" if serie else ""
            zeilen += ["# library(ggplot2)",
                       f"# ggplot(daten, aes(x = {x}, y = {y}{farbe})) + geom_line()"]
    elif typ == "boxplot" and x and len(o.get("werte") or []) == 5:
        u, q1, m, q3, ob = o["werte"]
        zeilen += ["# library(ggplot2)",
                   f"# ggplot(daten, aes(x = factor({x}), ymin = {u}, lower = {q1}, middle = {m},",
                   f"#                   upper = {q3}, ymax = {ob})) +",
                   "#   geom_boxplot(stat = \"identity\")"]
    elif typ == "kpi" and o.get("wert"):
        zeilen += [f"# daten${o['wert']}[1]"]
    if zeilen:
        zeilen.insert(0, f"# Darstellung wie im Dashboard (Widget-Typ \"{typ}\"):")
    return zeilen


def _umgebungen_def(namen: list[str], zuordnung: dict, variablen_fn) -> str:
    """R-Einträge DEV/INT/PRD für DEF$umgebungen."""
    eintraege = []
    for r_env in R_UMGEBUNGEN:
        eintrag = zuordnung.get(r_env)
        if isinstance(eintrag, dict):          # direkte Angaben aus umgebungen.yml
            env_id, env = None, eintrag
            werte = {n: v for n, v in (eintrag.get("variablen") or {}).items() if n in namen}
            kommentar = "   # aus umgebungen.yml (r_umgebungen)"
        else:
            env_id = eintrag
            env = cfg.ENVIRONMENTS.get(env_id, {}) if env_id else {}
            werte = _variablen_fuer(env_id, namen, variablen_fn) if env_id else {}
            kommentar = f"   # Studio-Umgebung {env_id}" if env_id else "   # TODO: Host und Datenbanken eintragen"
        host = env.get("host") or "TODO"
        if env.get("logmech"):
            db = f"list(host = {_r_str(host)}, logmech = {_r_str(env['logmech'])})"
        else:
            db = f"list(host = {_r_str(host)}, user = \"TODO\", password = \"TODO\")"
        dbs = ",\n".join(f"        {n} = {_r_str(werte.get(n, 'TODO'))}" for n in namen) or "        # keine"
        eintraege.append(
            f"    {r_env} = list({kommentar}\n"
            f"      db = {db},\n"
            f"      datenbanken = list(\n{dbs}\n      )\n"
            f"    )")
    return ",\n".join(eintraege)


# ---------------------------------------------------------------------------
# Vorlagen
# ---------------------------------------------------------------------------

_VORLAGE_PH = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
_ESC = "\x00DOLLAR\x00"


def _vorlage(name: str, ablage: Optional[Path]) -> str:
    """R-Vorlage: zuerst <Dashboard-Ablage>/r_vorlagen/<name>.R, sonst cfg/r_vorlagen/<name>.R."""
    for basis in ([ablage / "r_vorlagen"] if ablage else []) + [Path(cfg.PATHS["cfg"]) / "r_vorlagen"]:
        p = basis / f"{name}.R"
        if p.exists():
            return p.read_text(encoding="utf-8")
    raise FileNotFoundError(f"R-Vorlage {name}.R fehlt (cfg/r_vorlagen/)")


def _fuelle(vorlage: str, werte: dict) -> str:
    """${NAME} in einem Durchgang ersetzen (eingesetzte Werte werden nicht erneut
    ersetzt); $${…} ergibt ein wörtliches ${…}; unbekannte Platzhalter = Fehler."""
    text = vorlage.replace("$${", _ESC)
    fehlend = []

    def repl(m):
        if m.group(1) in werte:
            return str(werte[m.group(1)])
        fehlend.append(m.group(1))
        return m.group(0)

    text = _VORLAGE_PH.sub(repl, text)
    if fehlend:
        raise ValueError(f"Unbekannte Platzhalter in der R-Vorlage: {', '.join(sorted(set(fehlend)))}")
    return text.replace(_ESC, "${")


def _herkunft(dashboard: dict, widget: dict) -> str:
    return (f"Dashboard \"{dashboard.get('titel', dashboard['id'])}\" ({dashboard['id']}), "
            f"Widget \"{widget['id']}\", erzeugt {_dt.date.today().isoformat()}.")


def _erlaeuterung_kommentar(erlaeuterung: Optional[str], hinweise: list) -> str:
    z: list[str] = []
    if erlaeuterung:
        z += ["#"] + _kommentar(erlaeuterung)
    for h in hinweise or []:
        z += ["#"] + _kommentar("HINWEIS: " + h)
    return "".join(f"{x}\n" for x in z)


def _def_filter(filter_ids: list[str], filterwerte: dict, filter_defs: dict) -> str:
    if not filter_ids:
        return "  filter = list()"
    werte = []
    for k, fid in enumerate(filter_ids):
        fdef = filter_defs.get(fid, {})
        komma = "," if k < len(filter_ids) - 1 else ""   # Komma vor dem Kommentar
        werte.append((f"    {fid} = {_r_wert(filterwerte.get(fid), fdef.get('typ'))}{komma}",
                      fdef.get("titel") or fid))
    breite = max(len(code) for code, _ in werte)
    zeilen = ["  ## -- Filter (Werte wie im Dashboard beim Erzeugen) ---------------------------",
              "  filter = list("]
    zeilen += [f"{code.ljust(breite)}   # {titel}" for code, titel in werte]
    zeilen.append("  )")
    return "\n".join(zeilen)


def _aktiv(zuordnung: dict) -> str:
    return next((k for k, v in zuordnung.items() if v == cfg.get_active_env_id()), "DEV")


# ---------------------------------------------------------------------------
# Öffentliche Funktionen
# ---------------------------------------------------------------------------

def erzeuge(dashboard: dict, widget: dict, vorlage: str, filterwerte: dict,
            filter_defs: dict, r_umg: dict, variablen_fn, ablage: Optional[Path] = None) -> str:
    """R-Skript zu einem Widget mit SQL-Datei (Vorlage widget.R)."""
    namen = sorted({m.group(1) for m in _PH.finditer(vorlage) if m.group(2) is None})
    filter_ids: list[str] = []
    for m in _PH.finditer(vorlage):
        if m.group(1) == "FILTER" and m.group(2) and m.group(2) not in filter_ids:
            filter_ids.append(m.group(2))
    zuordnung = _umgebungs_zuordnung(r_umg)
    plot = _ggplot_vorschlag(widget, [])
    return _fuelle(_vorlage("widget", ablage), {
        "TITEL": widget.get("titel") or widget.get("id"),
        "HERKUNFT": _herkunft(dashboard, widget),
        "SQL_DATEI_KOMMENTAR": f"# SQL-Vorlage: {widget['sql']} (Dashboard-Ablage)\n" if widget.get("sql") else "",
        "ERLAEUTERUNG_KOMMENTAR": _erlaeuterung_kommentar(widget.get("erlaeuterung"), widget.get("hinweise")),
        "UMGEBUNG_AKTIV": _aktiv(zuordnung),
        "DEF_UMGEBUNGEN": _umgebungen_def(namen, zuordnung, variablen_fn),
        "DEF_FILTER": _def_filter(filter_ids, filterwerte, filter_defs),
        "SQL_VORLAGE": vorlage.rstrip(),
        "PLOT_VORSCHLAG": "\n".join(plot) if plot else "# (kein Darstellungsvorschlag für diesen Widget-Typ)",
        "DATUM": _dt.date.today().isoformat(),
    })


def erzeuge_katalog(dashboard: dict, widget: dict, objekte: list[str], erlaeuterung: str,
                    r_umg: dict, variablen_fn, ablage: Optional[Path] = None) -> str:
    """R-Skript für Übersichts-Widgets (Vorlage katalog.R): je Katalog-Objekt Existenz
    und Zeilenzahl – dieselbe Statusprüfung wie die Übersichtsseite."""
    namen = sorted({m.group(1) for o in objekte for m in _PH.finditer(o) if m.group(2) is None})
    zuordnung = _umgebungs_zuordnung(r_umg)
    return _fuelle(_vorlage("katalog", ablage), {
        "TITEL": dashboard.get("titel", dashboard["id"]),
        "HERKUNFT": _herkunft(dashboard, widget),
        "ERLAEUTERUNG_KOMMENTAR": _erlaeuterung_kommentar(erlaeuterung, []),
        "UMGEBUNG_AKTIV": _aktiv(zuordnung),
        "DEF_UMGEBUNGEN": _umgebungen_def(namen, zuordnung, variablen_fn),
        "OBJEKTE": ",\n".join(f"    {_r_str(o)}" for o in objekte),
        "DATUM": _dt.date.today().isoformat(),
    })
