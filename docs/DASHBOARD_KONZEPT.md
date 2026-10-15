# Dashboard-Konzept

> Status: Konzept (noch nicht umgesetzt)
> Stand: 2026-10-15
> Ziel: Ein modulares Dashboard-System als eigener Tab in daita-studio. Die Dashboards werden deklarativ konfiguriert; Inhalte, Datenbanknamen und SQL kommen aus dem Kunden-Workspace.

Dieses Dokument beschreibt nur das kundenneutrale Framework. Welche Dashboards ein Einsatz konkret hat und wie sie auf dessen Datenmodell abgebildet werden, steht im Kunden-Workspace.

---

## 1. Ausgangslage im Code

| Thema | Stand | Folge für das Konzept |
|---|---|---|
| Frontend | Vanilla JS mit Web Components, kein Build. Jeder Tab ist eine eigene HTML-Seite mit `<studio-nav>`; die Menüeinträge stehen in `NAV_ITEMS` in `frontend/components/nav-header.js` | neue Seite plus ein Eintrag in `NAV_ITEMS` |
| Ältere Dashboard-Seiten | `frontend/etl-dashboard.js` und `frontend/metadata-dashboard.js` arbeiten mit globalen Variablen, `innerHTML`, `onclick` und rohem `fetch` | **nicht** als Muster verwenden; stattdessen BACKLOG A1–A3: eine Komponente je Funktion, Events mit Präfix `studio:`, Zugriffe nur über `frontend/components/api.js` |
| Charts | keine Chart-Bibliothek vorhanden; Zielserver sind air-gapped (`docs/AIRGAP_DEPLOYMENT_PROMPT.md`) | eigene SVG-Widgets nach dem Muster von `frontend/components/lineage-graph.js` |
| Backend | FastAPI; Router in `backend/app/api/`, je Router `module_guard("<modul>")`; Rechte-Matrix `auth.modules` in `cfg/config.yml` | neuer Router mit eigenem Modul `dashboards` |
| DB-Zugriff | kein gemeinsamer Query-Service. `backend/app/services/meta_service.py` hat `_query()` und `_cached()` (TTL, Schlüssel je Umgebung) | daraus einen gemeinsamen Read-only-Helfer herausziehen |
| Umgebungen | `cfg/environments.yml` beschreibt Meta-Schemas; die Datenbanken der Layer stehen in `META_LAYER` und `META_DATABASE` | Datenbanknamen in Definitionen nur als Platzhalter, aufgelöst über die aktive Umgebung |
| Deklarative Ablage | `backend/app/api/diagrams.py` speichert JSON-Dateien unter `paths.diagrams` | gleiches Muster für Dashboard-Definitionen unter `paths.dashboards` |

## 2. Frontend

### Dateien

| Datei | Aufgabe |
|---|---|
| `frontend/dashboards.html` | Hülle: `<studio-nav active="dashboards">` und `<studio-dashboard-shell>` |
| `frontend/components/nav-header.js` | Eintrag `dashboards` in `NAV_ITEMS` |
| `frontend/components/api.js` | Namensraum `api.dashboards`: `list()`, `get(id)`, `data(id, widgetId, filter)`, `status(id)`, `catalog()`, `refresh(id)` |
| `frontend/components/dashboard-shell.js` | Dashboard-Auswahl, Filterleiste, Raster der Widgets, Anzeige des Datenstands; kennt keine Widget-Typen |
| `frontend/components/dashboard-widgets.js` | Registry: `studioWidgets.register(typ, { render(el, daten, optionen) })` |
| `frontend/components/widgets/widget-kpi.js` | Kennzahl mit Vergleichswert |
| `frontend/components/widgets/widget-table.js` | Tabelle mit Sortierung |
| `frontend/components/widgets/widget-bar.js` | Balken (gruppiert, gestapelt) als SVG |
| `frontend/components/widgets/widget-line.js` | Zeitreihe als SVG |
| `frontend/components/widgets/widget-area-map.js` | Übersichtskarte der Bereiche (siehe Abschnitt 5) |
| `frontend/components/widgets/widget-star-map.js` | Stern eines Bereichs: Fakt in der Mitte, Dimensionen darum (siehe Abschnitt 5) |
| `frontend/components/widgets/widget-subject-map.js` | Bereiche mit ihren Entitäten als Kästen (siehe Abschnitt 5) |

### Regeln

- Komponenten im Stil von `frontend/components/job-list.js`: IIFE, Klasse plus Custom Element.
- Kommunikation über Events: `studio:dashboard-filter-changed`, `studio:dashboard-refresh`, `studio:dashboard-drilldown` (Detail: Ziel-Dashboard, Bereich, Element).
- Detailansichten als Side-Panel, keine Modale (`docs/FLOW_UX_KONZEPT.md`).
- Farben nur über die CSS-Variablen aus `frontend/style.css`; die Status-Farben (vorhanden, teilweise, fehlt) als eigene Variablen dort ergänzen.
- Ein Widget-Typ kennt nur `{columns, rows, meta}`. Eine spätere Chart-Bibliothek aus `frontend/vendor/` lässt sich je Typ austauschen, ohne Shell oder Definitionen zu ändern.

## 3. Backend

### Router und Service

| Element | Inhalt |
|---|---|
| `backend/app/api/dashboards.py` | Präfix `/api/dashboards`, `dependencies=[Depends(module_guard("dashboards"))]` |
| `backend/app/services/dashboard_service.py` | lädt Katalog und Definitionen, löst Platzhalter auf, rendert SQL, führt aus, cacht |
| gemeinsamer Read-only-Helfer | aus `meta_service._query()` und `_cached()`; eigene Verbindung je Umgebung |
| `cfg/config.yml` | `paths.dashboards` (Pfad in den Kunden-Workspace) und Modul `dashboards` in `auth.modules` |

### Endpunkte

| Endpunkt | Rolle | Inhalt |
|---|---|---|
| `GET /api/dashboards` | Viewer | Liste: id, Titel, Gruppe, Reihenfolge |
| `GET /api/dashboards/catalog` | Viewer | Katalog der Bereiche und Elemente (ohne SQL) |
| `GET /api/dashboards/{id}` | Viewer | Definition ohne SQL: Layout, Widgets, Filter |
| `GET /api/dashboards/{id}/widgets/{wid}/data` | Viewer | `{columns, rows, meta: {datenstand, zeilen, cache}}`; Filterwerte als Query-Parameter |
| `GET /api/dashboards/{id}/status` | Viewer | je referenziertem DB-Objekt: existiert, Zeilenzahl, Datenstand |
| `POST /api/dashboards/{id}/refresh` | Editor | Cache dieses Dashboards leeren |

### Sicherheit

- Der Client schickt nie SQL, nur Werte von Filtern, die in der Definition freigegeben sind.
- Filterwerte gehen als Bind-Parameter (`?`) in die Abfrage.
- Ausgeführt werden nur SELECT-Statements, mit `LOCKING ROW FOR ACCESS` und Zeilenlimit.
- Das Dashboard zeigt Aggregate. Kleine Zellen werden unterdrückt, wenn der Katalog eine Mindestzahl vorgibt (`min_zelle`).
- Ein Bereich kann ein Schutzniveau tragen; der Service prüft es gegen die Rolle des Users. Die Zuordnung Schutzniveau → Rolle steht in `cfg/config.yml`.
- Langfristig liest das Dashboard mit einem eigenen Read-only-User je Umgebung. Bis dahin nutzt es die Verbindung der aktiven Umgebung.

### Platzhalter

| Platzhalter | Auflösung |
|---|---|
| `${DB:<layer>}` | Datenbank des Layers der aktiven Umgebung aus `META_LAYER` / `META_DATABASE` |
| `${META_SCHEMA}` | Meta-Schema der aktiven Umgebung |
| `${FILTER:<name>}` | Bind-Parameter des Filters (wird zu `?`) |

Gerendert wird mit `backend/app/services/template_engine.py`. Dieselbe Definition läuft damit in jeder Umgebung.

## 4. Konfiguration

Ablage unter `paths.dashboards` im Kunden-Workspace:

```
dashboards/
  katalog.yml          # Bereiche, Elemente, Plan-Status, Verweise auf DB-Objekte
  uebersicht.yml       # Dashboard-Definitionen, je Datei eines
  <id>.yml
  sql/<datei>.sql      # Widget-SQL mit Platzhaltern
```

daita-studio liefert ein neutrales Beispiel unter `cfg/dashboards_beispiel/` mit, das nur das Meta-Schema liest (Dashboard „ETL-Betrieb“ auf `META_ETL_JOB_RUN`). Damit lässt sich das Framework ohne Kundendaten testen.

### Katalog (`katalog.yml`)

Der Katalog beschreibt, was es geben soll und woraus es gespeist wird. Er kennt zwei Arten von Bereichen:

- `art: mart` für Consumable-Bereiche mit Fakten, Dimensionen, Kennzahlen und Produkten.
- `art: subject_area` für Reusable-Bereiche mit Entitäten.

```yaml
schutzniveaus: [oeffentlich, sn1, sn2]
min_zelle: 5

conformed_dimensionen:
  - id: zeit
    titel: Zeit
    quelle: ${DB:consumable_access}.V_DIM_DATUM
    attribute: [Datum, Jahr, Quartal, Monat]

bereiche:
  - id: A
    art: mart
    nr: 1
    titel: Bereich A
    prioritaet: hoch
    schutzniveau: oeffentlich
    fakten:
      - id: fakt_a
        titel: Fakt A
        quelle: ${DB:consumable_access}.V_FACT_A
        dimensionen: [zeit, dim_x]
        kennzahlen:
          - {id: anzahl, titel: Anzahl, status: ableitbar}
          - {id: quote, titel: Quote, status: fehlt, luecke: "Gruppierung fehlt"}
    dimensionen:
      - {id: dim_x, titel: Dim X, quelle: ${DB:consumable_access}.V_DIM_X}
    produkte:
      - {id: "A.1", titel: Produkt 1, pilot: true, dashboard: bereich_a}

  - id: S1
    art: subject_area
    titel: Subject Area 1
    entitaeten:
      - {id: e1, titel: Entität 1, quelle: ${DB:reusable_base}.E1, kern: true}
      - {id: e2, titel: Entität 2, status: fehlt}
```

- `status` im YAML ist der **Plan** (`vorhanden`, `ableitbar`, `fehlt`).
- Der **Ist-Stand** kommt live aus der Datenbank: Ein Element mit `quelle` gilt als vorhanden, wenn das Objekt existiert und Zeilen hat.
- Weichen Plan und Ist ab, zeigt das Widget beides.

### Dashboard (`<id>.yml`)

```yaml
id: bereich_a
titel: Bereich A
gruppe: Statistik
filter:
  - {id: jahr_von, typ: jahr, default: 2015}
  - {id: jahr_bis, typ: jahr, default: aktuell}
widgets:
  - id: kpi_anzahl
    typ: kpi
    sql: sql/a_anzahl.sql
    pos: {x: 0, y: 0, b: 3, h: 1}
  - id: anzahl_je_jahr
    typ: bar
    sql: sql/a_je_jahr.sql
    filter: [jahr_von, jahr_bis]
    pos: {x: 0, y: 1, b: 12, h: 3}
    optionen: {x: JAHR, y: ANZAHL, serie: KATEGORIE}
```

## 5. Übersichtsseite

Die Startseite des Tabs ist eine Übersicht, die der Katalog vollständig erzeugt. Sie ist so aufgebaut wie die übliche Architekturgrafik „Data-Mart-Bereiche plus Business-Objekt-Modell“ und hat zwei Reiter.

### Reiter „Consumable“ (`widget-area-map` und `widget-star-map`)

| Zone | Inhalt |
|---|---|
| Kopfzeile | eine Kachel je Bereich `art: mart` in der Reihenfolge `nr`: Nummer, Titel, Anzahl Produkte, Priorität, Schutzniveau. Die Rahmenfarbe zeigt den Abdeckungsgrad (vorhanden / teilweise / fehlt) |
| linke Spalte | Conformed Dimensionen mit ihren Attributen und ihrem Status |
| Mitte | Stern des gewählten Bereichs: Fakt in der Mitte mit Schlüsseln und Kennzahlen, Dimensionen darum, Linien zu den Conformed Dimensionen. Jedes Element trägt einen Status-Punkt, die Zeilenzahl und die Quelle als Tooltip |
| darunter | Liste der Produkte des Bereichs mit Häkchen (Dashboard vorhanden) oder Lücke |
| Fußzeile | kompakte Kästen der übrigen Bereiche (Fakt, Dimensionen, Kennzahlen, Anzahl Produkte, Schutzniveau) |

Klick auf eine Kachel wechselt den Stern; Klick auf ein Produkt mit `dashboard:` öffnet dieses Dashboard. Lücken öffnen ein Side-Panel mit dem Text aus `luecke`.

### Reiter „Reusable“ (`widget-subject-map`)

- Ein Kasten je Bereich `art: subject_area`, darin die Entitäten mit Status-Punkt und Zeilenzahl.
- Entitäten mit `kern: true` sind hervorgehoben.
- Beziehungen zwischen Entitäten stehen im Katalog unter `beziehungen: [{von, nach, kard}]` und werden als Linien gezeichnet.

### Layout

- Automatisch als Raster: Kacheln in einer Reihe, Bereiche in Spalten. Positionen im YAML sind optional (`pos`).
- Die Seite liest nur Katalog und `/status`; sie braucht kein Widget-SQL.

## 6. Umsetzungsschritte

1. Read-only-Helfer, Router, Service, Platzhalter und Cache.
2. Shell, Registry, Widgets `kpi`, `table`, `bar`, `line`; Test mit dem neutralen Beispiel „ETL-Betrieb“.
3. Übersichtsseite: `area-map`, `star-map`, `subject-map` und `/status`.
4. Kundendashboards im Kunden-Workspace.

## 7. Offene Punkte

- Eigener Read-only-User je Umgebung für das Dashboard.
- Zuordnung Schutzniveau → Rolle.
- Ob Definitionen später auch über die GUI bearbeitet werden (wie `diagrams.py`) oder nur als Dateien gepflegt werden.
