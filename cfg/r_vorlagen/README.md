# R-Vorlagen für das Info-Panel der Dashboards

Rahmen der R-Gerüste, die das Info-Panel je Widget erzeugt
(`backend/app/services/r_skelett.py`). Python bereitet nur die Werte auf und
setzt sie hier ein; den Rahmen pflegt man als normale R-Datei.

| Datei | Für |
|---|---|
| `widget.R` | Widgets mit SQL-Datei |
| `katalog.R` | Übersichts-Widgets (`daten: katalog`): Statusprüfung der Katalog-Objekte |

Ein Einsatz kann eine Vorlage ersetzen: gleichnamige Datei in
`<Dashboard-Ablage>/r_vorlagen/` (z. B. eigene Pakete, Excel-Export).

**Platzhalter** `${NAME}` (nur Großbuchstaben und `_`); `$${…}` ergibt ein
wörtliches `${…}`. Eingesetzte Werte werden nicht erneut ersetzt, unbekannte
Platzhalter brechen mit Fehler ab.

| Platzhalter | Inhalt |
|---|---|
| `${TITEL}` | Titel des Widgets bzw. Dashboards |
| `${HERKUNFT}` | Dashboard, Widget, Erzeugungsdatum |
| `${SQL_DATEI_KOMMENTAR}` | Kommentarzeile mit der SQL-Datei (oder leer) |
| `${ERLAEUTERUNG_KOMMENTAR}` | Erläuterung und Hinweise als Kommentarzeilen (oder leer) |
| `${UMGEBUNG_AKTIV}` | DEV / INT / PRD der aktiven Studio-Umgebung |
| `${DEF_UMGEBUNGEN}` | Einträge DEV, INT, PRD für `DEF$umgebungen` |
| `${DEF_FILTER}` | `filter = list(…)` mit den aktuellen Filterwerten (nur `widget.R`) |
| `${SQL_VORLAGE}` | SQL-Datei des Widgets mit Platzhaltern (nur `widget.R`) |
| `${PLOT_VORSCHLAG}` | auskommentierter ggplot2-Vorschlag passend zum Widget-Typ (nur `widget.R`) |
| `${OBJEKTE}` | Objektliste aus dem Katalog (nur `katalog.R`) |
| `${DATUM}` | Erzeugungsdatum |
