# ${TITEL}: Statusprüfung der Katalog-Objekte ----
#
# R-Gerüst aus daita-studio: ${HERKUNFT}
${ERLAEUTERUNG_KOMMENTAR}#
# Je Objekt aus katalog.yml: existiert es, Art (Tabelle/View), Zeilenzahl.
# ALLE Einstellungen stehen im Definitionsblock (1) – keine Umgebungsvariablen,
# keine interaktiven Eingaben. Zugangsdaten als "TODO" eintragen (oder logmech = "KRB5").

suppressPackageStartupMessages({
  library(DBI)
  library(dplyr)
})

## ===========================================================================
## 1) DEFINITIONEN – die einzige Anpassstelle
## ===========================================================================

DEF <- list(

  umgebung = "${UMGEBUNG_AKTIV}",   # "DEV" | "INT" | "PRD" – HIER umstellen

  ## -- Umgebungen: DB-Verbindung und Datenbanknamen ---------------------------
  umgebungen = list(
${DEF_UMGEBUNGEN}
  ),

  ## -- Objekte aus katalog.yml ($${NAME} = Datenbank aus der Umgebung) --------
  objekte = c(
${OBJEKTE}
  )
)

## ===========================================================================
## 2) FUNKTIONEN
## ===========================================================================

resolve_umgebung <- function(def) {
  u <- def$umgebungen[[def$umgebung]]
  if (is.null(u)) stop("DEF$umgebung = '", def$umgebung, "' ist nicht in DEF$umgebungen definiert.")
  offen <- c(names(Filter(function(x) identical(x, "TODO") || identical(x, ""), u$db)),
             names(Filter(function(x) identical(x, "TODO"), u$datenbanken)))
  if (length(offen) > 0) stop("In DEF$umgebungen$", def$umgebung, " noch ausfüllen: ",
                              paste(offen, collapse = ", "))
  u
}

objekt_name <- function(o, u) {
  for (n in names(u$datenbanken)) o <- gsub(paste0("${", n, "}"), u$datenbanken[[n]], o, fixed = TRUE)
  o
}

status_eines <- function(con, objekt) {
  teile <- strsplit(objekt, ".", fixed = TRUE)[[1]]
  art <- dbGetQuery(con, sprintf(
    "SELECT TableKind FROM DBC.TablesV WHERE DatabaseName = '%s' AND TableName = '%s'",
    teile[1], teile[2]))
  if (nrow(art) == 0) return(tibble(OBJEKT = objekt, EXISTIERT = FALSE, ART = NA_character_, ZEILEN = NA_real_))
  zeilen <- tryCatch(
    dbGetQuery(con, sprintf("LOCKING ROW FOR ACCESS SELECT COUNT(*) AS N FROM %s", objekt))$N,
    error = function(e) NA_real_)   # z. B. kein Leserecht (Fehler 3523)
  tibble(OBJEKT = objekt, EXISTIERT = TRUE,
         ART = ifelse(trimws(art$TableKind[1]) == "V", "View", "Tabelle"), ZEILEN = as.numeric(zeilen))
}

verbinden <- function(db) {
  do.call(dbConnect, c(list(teradatasql::TeradataDriver()), db))
}

## ===========================================================================
## 3) MAIN
## ===========================================================================

main <- function(def) {
  u <- resolve_umgebung(def)
  message("Umgebung: ", def$umgebung, " | Host: ", u$db$host)
  con <- verbinden(u$db)
  on.exit(dbDisconnect(con), add = TRUE)
  bind_rows(lapply(def$objekte, function(o) status_eines(con, objekt_name(o, u))))
}

status <- main(DEF)
print(status, n = Inf)

## ===========================================================================
## 4) AB HIER WEITER
## ===========================================================================

# z. B. fehlende oder leere Objekte:
# status %>% filter(!EXISTIERT | ZEILEN == 0)
