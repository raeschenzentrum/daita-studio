"""
R-Codegerüst zu einem Dashboard-Widget (Info-Panel).

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


def erzeuge(dashboard: dict, widget: dict, vorlage: str, filterwerte: dict,
            filter_defs: dict, r_umg: dict, variablen_fn) -> str:
    """R-Skript als Text."""
    namen = sorted({m.group(1) for m in _PH.finditer(vorlage) if m.group(2) is None})
    filter_ids = []
    for m in _PH.finditer(vorlage):
        if m.group(1) == "FILTER" and m.group(2) and m.group(2) not in filter_ids:
            filter_ids.append(m.group(2))

    zuordnung = _umgebungs_zuordnung(r_umg)
    aktiv = next((k for k, v in zuordnung.items() if v == cfg.get_active_env_id()), "DEV")

    titel = widget.get("titel") or widget.get("id")
    z: list[str] = []
    z.append(f"# {titel} ----")
    z.append("#")
    z.append(f"# R-Gerüst aus daita-studio: Dashboard \"{dashboard.get('titel', dashboard['id'])}\" "
             f"({dashboard['id']}), Widget \"{widget['id']}\", erzeugt {_dt.date.today().isoformat()}.")
    if widget.get("sql"):
        z.append(f"# SQL-Vorlage: {widget['sql']} (Dashboard-Ablage)")
    if widget.get("erlaeuterung"):
        z.append("#")
        z += _kommentar(widget["erlaeuterung"])
    for h in widget.get("hinweise") or []:
        z.append("#")
        z += _kommentar("HINWEIS: " + h)
    z += ["#",
          "# ALLE Einstellungen stehen im Definitionsblock (1) – keine Umgebungsvariablen,",
          "# keine interaktiven Eingaben. Zugangsdaten stehen nicht im Code: Einträge \"TODO\"",
          "# vor dem ersten Lauf ersetzen (oder bei Kerberos logmech = \"KRB5\" nutzen).",
          "",
          "suppressPackageStartupMessages({",
          "  library(DBI)",
          "  library(dplyr)",
          "})",
          "",
          "options(scipen = 999)",
          "",
          "## ===========================================================================",
          "## 1) DEFINITIONEN – die einzige Anpassstelle",
          "## ===========================================================================",
          "",
          "DEF <- list(",
          "",
          f"  umgebung = {_r_str(aktiv)},   # \"DEV\" | \"INT\" | \"PRD\" – HIER umstellen",
          "",
          "  ## -- Umgebungen: DB-Verbindung und Datenbanknamen ---------------------------",
          "  umgebungen = list("]
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
    z.append(",\n".join(eintraege))
    z += ["  ),", ""]
    if filter_ids:
        z.append("  ## -- Filter (Werte wie im Dashboard beim Erzeugen) ---------------------------")
        z.append("  filter = list(")
        for k, fid in enumerate(filter_ids):
            fdef = filter_defs.get(fid, {})
            komma = "," if k < len(filter_ids) - 1 else ""   # Komma vor dem Kommentar
            z.append(f"    {fid} = {_r_wert(filterwerte.get(fid), fdef.get('typ'))}{komma}   # {fdef.get('titel') or fid}")
        z.append("  )")
    else:
        z.append("  filter = list()")
    z += [")",
          "",
          "## ===========================================================================",
          "## 2) SQL-VORLAGE – ${NAME} = DEF$umgebungen$<UMGEBUNG>$datenbanken$NAME,",
          "##    ${FILTER:id} = DEF$filter$id",
          "## ===========================================================================",
          "",
          "SQL_VORLAGE <- r\"---[",
          vorlage.rstrip(),
          "]---\"",
          "",
          "## ===========================================================================",
          "## 3) FUNKTIONEN",
          "## ===========================================================================",
          "",
          "# Wert als SQL-Literal (nur für die Filter aus DEF)",
          "sql_literal <- function(v) {",
          "  if (inherits(v, \"Date\")) return(sprintf(\"DATE '%s'\", format(v, \"%Y-%m-%d\")))",
          "  if (is.numeric(v)) return(as.character(v))",
          "  paste0(\"'\", gsub(\"'\", \"''\", as.character(v), fixed = TRUE), \"'\")",
          "}",
          "",
          "# Umgebung prüfen: kein \"TODO\" mehr, sonst Abbruch mit Hinweis auf die DEF-Stelle",
          "resolve_umgebung <- function(def) {",
          "  u <- def$umgebungen[[def$umgebung]]",
          "  if (is.null(u)) stop(\"DEF$umgebung = '\", def$umgebung, \"' ist nicht in DEF$umgebungen definiert.\")",
          "  offen <- c(",
          "    names(Filter(function(x) identical(x, \"TODO\") || identical(x, \"\"), u$db)),",
          "    names(Filter(function(x) identical(x, \"TODO\"), u$datenbanken))",
          "  )",
          "  if (length(offen) > 0) {",
          "    stop(\"In DEF$umgebungen$\", def$umgebung, \" noch ausfüllen: \", paste(offen, collapse = \", \"),",
          "         \" (Kerberos: user/password entfernen und logmech = \\\"KRB5\\\" setzen).\")",
          "  }",
          "  u",
          "}",
          "",
          "# SQL aus der Vorlage: Datenbanknamen und Filterwerte einsetzen",
          "build_sql <- function(def, u) {",
          "  sql <- SQL_VORLAGE",
          "  for (n in names(u$datenbanken)) {",
          "    sql <- gsub(paste0(\"${\", n, \"}\"), u$datenbanken[[n]], sql, fixed = TRUE)",
          "  }",
          "  for (f in names(def$filter)) {",
          "    sql <- gsub(paste0(\"${FILTER:\", f, \"}\"), sql_literal(def$filter[[f]]), sql, fixed = TRUE)",
          "  }",
          "  rest <- regmatches(sql, gregexpr(\"\\\\$\\\\{[^}]+\\\\}\", sql))[[1]]",
          "  if (length(rest) > 0) stop(\"Platzhalter ohne Wert in DEF: \", paste(unique(rest), collapse = \", \"))",
          "  sql",
          "}",
          "",
          "verbinden <- function(db) {",
          "  do.call(dbConnect, c(list(teradatasql::TeradataDriver()), db))",
          "}",
          "",
          "## ===========================================================================",
          "## 4) MAIN",
          "## ===========================================================================",
          "",
          "main <- function(def) {",
          "  u   <- resolve_umgebung(def)",
          "  sql <- build_sql(def, u)",
          "  message(\"Umgebung: \", def$umgebung, \" | Host: \", u$db$host)",
          "  message(\"SQL:\\n\", sql)",
          "",
          "  con <- verbinden(u$db)",
          "  on.exit(dbDisconnect(con), add = TRUE)",
          "  daten <- as_tibble(dbGetQuery(con, sql))",
          "  # teradatasql liefert bei leerem Ergebnis ein data.frame ohne Spalten",
          "  if (ncol(daten) == 0) message(\"Abfrage lieferte 0 Zeilen.\")",
          "  message(\"Zeilen: \", nrow(daten))",
          "  daten",
          "}",
          "",
          "daten <- main(DEF)",
          "print(daten)",
          "",
          "## ===========================================================================",
          "## 5) AB HIER WEITER – Auswertung, Darstellung, Export",
          "## ===========================================================================",
          ""]
    z += _ggplot_vorschlag(widget, [])
    return "\n".join(z) + "\n"
