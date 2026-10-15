# ${TITEL} ----
#
# R-Gerüst aus daita-studio: ${HERKUNFT}
${SQL_DATEI_KOMMENTAR}${ERLAEUTERUNG_KOMMENTAR}#
# ALLE Einstellungen stehen im Definitionsblock (1) – keine Umgebungsvariablen,
# keine interaktiven Eingaben. Zugangsdaten stehen nicht im Code: Einträge "TODO"
# vor dem ersten Lauf ersetzen (oder bei Kerberos logmech = "KRB5" nutzen).

suppressPackageStartupMessages({
  library(DBI)
  library(dplyr)
})

options(scipen = 999)

## ===========================================================================
## 1) DEFINITIONEN – die einzige Anpassstelle
## ===========================================================================

DEF <- list(

  umgebung = "${UMGEBUNG_AKTIV}",   # "DEV" | "INT" | "PRD" – HIER umstellen

  ## -- Umgebungen: DB-Verbindung und Datenbanknamen ---------------------------
  umgebungen = list(
${DEF_UMGEBUNGEN}
  ),

${DEF_FILTER}
)

## ===========================================================================
## 2) SQL-VORLAGE – $${NAME} = DEF$umgebungen$<UMGEBUNG>$datenbanken$NAME,
##    $${FILTER:id} = DEF$filter$id
## ===========================================================================

SQL_VORLAGE <- r"---[
${SQL_VORLAGE}
]---"

## ===========================================================================
## 3) FUNKTIONEN
## ===========================================================================

# Wert als SQL-Literal (nur für die Filter aus DEF)
sql_literal <- function(v) {
  if (inherits(v, "Date")) return(sprintf("DATE '%s'", format(v, "%Y-%m-%d")))
  if (is.numeric(v)) return(as.character(v))
  paste0("'", gsub("'", "''", as.character(v), fixed = TRUE), "'")
}

# Umgebung prüfen: kein "TODO" mehr, sonst Abbruch mit Hinweis auf die DEF-Stelle
resolve_umgebung <- function(def) {
  u <- def$umgebungen[[def$umgebung]]
  if (is.null(u)) stop("DEF$umgebung = '", def$umgebung, "' ist nicht in DEF$umgebungen definiert.")
  offen <- c(
    names(Filter(function(x) identical(x, "TODO") || identical(x, ""), u$db)),
    names(Filter(function(x) identical(x, "TODO"), u$datenbanken))
  )
  if (length(offen) > 0) {
    stop("In DEF$umgebungen$", def$umgebung, " noch ausfüllen: ", paste(offen, collapse = ", "),
         " (Kerberos: user/password entfernen und logmech = \"KRB5\" setzen).")
  }
  u
}

# SQL aus der Vorlage: Datenbanknamen und Filterwerte einsetzen
build_sql <- function(def, u) {
  sql <- SQL_VORLAGE
  for (n in names(u$datenbanken)) {
    sql <- gsub(paste0("${", n, "}"), u$datenbanken[[n]], sql, fixed = TRUE)
  }
  for (f in names(def$filter)) {
    sql <- gsub(paste0("${FILTER:", f, "}"), sql_literal(def$filter[[f]]), sql, fixed = TRUE)
  }
  rest <- regmatches(sql, gregexpr("\\$\\{[^}]+\\}", sql))[[1]]
  if (length(rest) > 0) stop("Platzhalter ohne Wert in DEF: ", paste(unique(rest), collapse = ", "))
  sql
}

verbinden <- function(db) {
  do.call(dbConnect, c(list(teradatasql::TeradataDriver()), db))
}

## ===========================================================================
## 4) MAIN
## ===========================================================================

main <- function(def) {
  u   <- resolve_umgebung(def)
  sql <- build_sql(def, u)
  message("Umgebung: ", def$umgebung, " | Host: ", u$db$host)
  message("SQL:\n", sql)

  con <- verbinden(u$db)
  on.exit(dbDisconnect(con), add = TRUE)
  daten <- as_tibble(dbGetQuery(con, sql))
  # teradatasql liefert bei leerem Ergebnis ein data.frame ohne Spalten
  if (ncol(daten) == 0) message("Abfrage lieferte 0 Zeilen.")
  message("Zeilen: ", nrow(daten))
  daten
}

daten <- main(DEF)
print(daten)

## ===========================================================================
## 5) AB HIER WEITER – Auswertung, Darstellung, Export
## ===========================================================================

${PLOT_VORSCHLAG}
