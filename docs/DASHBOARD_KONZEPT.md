# Dashboard-Konzept

> Status: Schritte 1–4 umgesetzt (2026-10-15); erste Kundendashboards im Kunden-Workspace
> Stand: 2026-10-15
> Ziel: Ein modulares Dashboard-System als eigener Tab in daita-studio. Die Dashboards werden deklarativ konfiguriert; Inhalte, Datenbanknamen und SQL kommen aus dem Kunden-Workspace.

Dieses Dokument beschreibt nur das kundenneutrale Framework. Welche Dashboards ein Einsatz konkret hat und wie sie auf dessen Datenmodell abgebildet werden, steht im Kunden-Workspace.

---

## 1. Ausgangslage im Code

| Thema | Stand | Folge für das Konzept |
|---|---|---|
| Frontend | Vanilla JS mit Web Components, kein Build. Jeder Tab ist eine eigene HTML-Seite mit `<studio-nav>`; die Menüeinträge stehen in `NAV_ITEMS` in `frontend/components/nav-header.js` | neue Seite plus ein Eintrag in `NAV_ITEMS` |
| Ältere Dashboard-Seiten | `frontend/etl-dashboard.js` und `frontend/metadata-dashboard.js` arbeiten mit globalen Variablen, `innerHTML`, `onclick` und rohem `fetch` | **nicht** als Muster verwenden; stattdessen BACKLOG A1–A3: eine Komponente je Funktion, Events mit Präfix `studio:`, Zugriffe nur über `frontend/components/api.js` |
| Charts | keine Chart-Bibliothek vorhanden; Zielserver sind air-gapped (`docs/AIRGAP_DEPLOYMENT_PROMPT.md`), Bibliotheken dürfen aber als Datei mitgeliefert werden | Apache ECharts als Vendor-Datei (Abschnitt 2, „Chart-Bibliothek“) |
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
| `frontend/components/widgets/widget-echarts.js` | gemeinsame Basis aller Diagramm-Widgets: Instanz anlegen, Theme, Resize, Datenübergabe als `dataset`, PNG-Export |
| `frontend/components/widgets/widget-bar.js` | Balken (gruppiert, gestapelt), ECharts |
| `frontend/components/widgets/widget-line.js` | Zeitreihe mit Zoom über die Zeitachse, ECharts |
| `frontend/components/widgets/widget-pie.js` | Anteile (Ring), ECharts |
| `frontend/components/widgets/widget-heatmap.js` | Matrix zweier Dimensionen, z. B. Monat × Kategorie, ECharts |
| `frontend/components/widgets/widget-boxplot.js` | Verteilung je Kategorie aus vorgerechneten Kennwerten (z. B. Perzentile), ECharts |
| `frontend/components/widgets/widget-sankey.js` | Flüsse zwischen Zuständen, ECharts |
| `frontend/components/widgets/widget-map.js` | Choroplethenkarte aus einer lokal abgelegten GeoJSON-Datei, ECharts |
| `frontend/components/widgets/widget-katalog.js` | gemeinsame Basis der Übersicht: Status aus Plan und Ist, Abdeckung, Legende, Linien, Side-Panel |
| `frontend/components/widgets/widget-area-map.js` | Übersichtskarte der Bereiche und Stern eines Bereichs (`area-map`, `star-map`; siehe Abschnitt 5) |
| `frontend/components/widgets/widget-subject-map.js` | Bereiche mit ihren Entitäten als Kästen (siehe Abschnitt 5) |

### Regeln

- Komponenten im Stil von `frontend/components/job-list.js`: IIFE, Klasse plus Custom Element.
- Kommunikation über Events: `studio:dashboard-filter-changed`, `studio:dashboard-refresh`, `studio:dashboard-drilldown` (Detail: Ziel-Dashboard, Bereich, Element).
- Detailansichten als Side-Panel, keine Modale (`docs/FLOW_UX_KONZEPT.md`).
- Farben nur über die CSS-Variablen aus `frontend/style.css`; die Status-Farben (vorhanden, teilweise, fehlt) als eigene Variablen dort ergänzen.
- Ein Widget-Typ kennt nur `{columns, rows, meta}`. Die Shell und die Definitionen hängen nicht von ECharts ab; die Bibliothek steckt nur in `widget-echarts.js` und den Diagramm-Widgets.

### Chart-Bibliothek

| Punkt | Festlegung |
|---|---|
| Bibliothek | Apache ECharts, eine Datei `echarts.min.js` (ca. 1 MB), Apache-2.0, keine Abhängigkeiten |
| Ablage | `frontend/vendor/echarts/echarts.min.js` mit `LICENSE` und `VERSION`; feste Version, kein CDN. Eintrag in `docs/AIRGAP_DEPLOYMENT_PROMPT.md` |
| Einbindung | klassisches `<script>` in `frontend/dashboards.html`, globales `echarts` |
| Renderer | `svg` als Standard (scharf beim Drucken und Export); `canvas` je Widget wählbar bei vielen Punkten |
| Theme | `widget-echarts.js` registriert ein Theme `studio` aus den CSS-Variablen von `frontend/style.css` (Farben, Schrift); Status-Farben ebenfalls von dort |
| Daten | Ergebnis der API als `dataset` (`source: rows`, `dimensions: columns`); Achsen und Serien per `encode` aus den Widget-Optionen |
| Feinsteuerung | `optionen.echarts` im YAML wird unverändert in die ECharts-Option gemischt; nur Daten, keine Funktionen (kein JS aus Konfiguration) |
| Karten | GeoJSON-Dateien liegen im Kunden-Workspace unter `dashboards/geo/` und werden über `GET /api/dashboards/geo/{name}` ausgeliefert, dann mit `echarts.registerMap` angemeldet |
| Export | Toolbox `saveAsImage` (PNG) je Diagramm |

Die Übersichtsseite (Abschnitt 5) nutzt ECharts nicht: Kästen mit Attributlisten sind als HTML genauer zu setzen; die Verbindungslinien sind ein SVG-Overlay.

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
| `GET /api/dashboards/catalog/status` | Viewer | je `quelle` im Katalog: existiert, Art, Zeilenzahl |
| `GET /api/dashboards/{id}` | Viewer | Definition ohne SQL: Layout, Widgets, Filter |
| `GET /api/dashboards/{id}/widgets/{wid}/data` | Viewer | `{columns, rows, meta: {datenstand, zeilen, cache}}`; Filterwerte als Query-Parameter |
| `GET /api/dashboards/{id}/widgets/{wid}/info` | Viewer | Info-Panel: Erläuterung, Hinweise, Fakten/Dimensionen mit Joins, Herkunft bis zu den Tabellen, SQL (Abschnitt 5a); `_zeilen=0` ohne Zeilenzahlen |
| `GET /api/dashboards/geo/{name}` | Viewer | GeoJSON für Karten-Widgets aus `dashboards/geo/` |
| `GET /api/dashboards/{id}/status` | Viewer | je referenziertem DB-Objekt: existiert, Zeilenzahl, Datenstand |
| `POST /api/dashboards/{id}/refresh` | Editor | Cache dieses Dashboards leeren |

### Sicherheit

- Der Client schickt nie SQL, nur Werte von Filtern, die in der Definition freigegeben sind.
- Filterwerte gehen als Bind-Parameter (`?`) in die Abfrage.
- Ausgeführt werden nur SELECT-Statements, mit `LOCKING ROW FOR ACCESS` und Zeilenlimit.
- Das Dashboard zeigt Aggregate. Kleine Zellen werden unterdrückt, wenn der Katalog eine Mindestzahl vorgibt (`min_zelle`).
- Ein Bereich kann ein Schutzniveau tragen; der Service prüft es gegen die Rolle des Users. Die Zuordnung Schutzniveau → Rolle steht in `cfg/config.yml`.
- Eigener Lese-User je Umgebung: `dashboards_db: {user, password, host?}` am Eintrag in `cfg/environments.yml`. Widget-SQL und Datenstand laufen über diese Verbindung (z. B. ein User mit Konsumenten-Leserolle auf der ACCESS-Datenbank); Metadaten und Platzhalter (`META_LAYER`, `DBC`) weiter über die Verbindung der Umgebung. Für den Objektstatus zählt das Framework zuerst über die Umgebungs-Verbindung und bei fehlendem Recht (3523) über den Lese-User. Ohne `dashboards_db` liest alles über die Verbindung der Umgebung.

### Platzhalter

| Platzhalter | Auflösung |
|---|---|
| `${META_SCHEMA}` | Meta-Schema der aktiven Umgebung |
| `${DB_<LAYER_CODE>}` | Datenbank des Layers aus `META_LAYER.layer_code` / `META_DATABASE`, z. B. `${DB_RAW}`, `${DB_CONS}` (je Layer die erste Datenbank) |
| `${<NAME>}` | eigene Variable aus `umgebungen.yml` (Abschnitt 4) |
| `${FILTER:<id>}` | Bind-Parameter des Filters (wird zu `?`); nur Filter, die das Widget unter `filter:` freigibt |

Syntax wie in `backend/app/services/template_engine.py`; die Ersetzung macht `backend/app/services/dashboard_service.py` selbst, weil Filter als Bind-Parameter laufen. Ein nicht auflösbarer Platzhalter ist ein Fehler. Dieselbe Definition läuft damit in jeder Umgebung.

Ausgeführt wird über `backend/app/services/td_readonly.py`: genau ein Statement, nur `SELECT`/`WITH` (optional `LOCKING … FOR ACCESS` davor), Zeilenlimit (Default 5000, je Widget `optionen.max_zeilen`), Cache je Umgebung über SQL-Text und Parameter (Widgets mit gleicher Abfrage teilen sich ein Ergebnis; TTL je Dashboard `cache_ttl`, Default 300 s).

## 4. Konfiguration

Die Ablage wird je Umgebung gewählt: `dashboards:` am Eintrag in `cfg/environments.yml` (lokale Datei, nicht im Repo; relativ zu `install_root` oder absolut, z. B. `'../<kunde>-lakehouse/dashboards'`). Ohne Angabe gilt `paths.dashboards` aus `cfg/config.yml` (neutrales Beispiel). So bleibt der Pfad zum Kunden-Workspace aus dem Framework-Repo heraus.

```
dashboards/
  umgebungen.yml       # optional: eigene Variablen je Umgebung
  katalog.yml          # optional: Bereiche, Elemente, Plan-Status, Verweise auf DB-Objekte
  <id>.yml             # je Dashboard eine Datei
  sql/<datei>.sql      # Widget-SQL mit Platzhaltern
  geo/<name>.json      # GeoJSON für Karten
```

### Variablen (`umgebungen.yml`)

Für Datenbanken, die nicht in `META_DATABASE` stehen (z. B. View- oder Access-Datenbanken eines Layers). `default` gilt immer, der Abschnitt mit der Umgebungs-ID (`cfg/environments.yml`) überschreibt. Werte dürfen die eingebauten Platzhalter verwenden.

```yaml
variablen:
  default:
    DB_ZUGRIFF: ${DB_CONS}
  umgebung_a:
    DB_ZUGRIFF: KUNDE_A_CON_ACCESS
```

daita-studio liefert ein neutrales Beispiel unter `cfg/dashboards_beispiel/` mit, das nur das Meta-Schema liest (Dashboard „ETL-Betrieb“ auf `META_ETL_JOB_RUN`). Damit lässt sich das Framework ohne Kundendaten testen.

### Katalog (`katalog.yml`)

Der Katalog beschreibt, was es geben soll und woraus es gespeist wird. Er kennt zwei Arten von Bereichen:

- `art: mart` für Consumable-Bereiche mit Fakten, Dimensionen, Kennzahlen und Produkten.
- `art: subject_area` für Reusable-Bereiche mit Entitäten.

```yaml
titel_consumable: Data-Mart-Bereiche (Consumable)   # Überschrift Reiter Consumable
titel_reusable: Business-Objekt-Modell (Reusable)   # Überschrift Reiter Reusable
min_zelle: 5

conformed_dimensionen:
  - id: zeit
    titel: Zeit
    quelle: ${DB_ZUGRIFF}.V_DIM_DATUM
    attribute: [Datum, Jahr, Quartal, Monat]

bereiche:
  - id: A
    art: mart
    nr: 1
    titel: Bereich A
    prioritaet: hoch
    schutzniveau: oeffentlich
    produkte_anzahl: 3             # geplante Produkte insgesamt (auch wenn nicht alle benannt)
    luecke: "Notiz zum Bereich"
    fakten:
      - id: fakt_a
        titel: Fakt A
        schluessel: [ZeitSK, DimXSK]
        dimensionen: [zeit, dim_x]   # IDs aus conformed_dimensionen oder dimensionen des Bereichs
        kennzahlen:
          - {id: anzahl, titel: Anzahl, status: ableitbar}
          - {id: quote, titel: Quote, status: fehlt, luecke: "Gruppierung fehlt"}
    dimensionen:
      - {id: dim_x, titel: Dim X, quelle: ${DB_ZUGRIFF}.V_DIM_X, attribute: [DimXSK, Code, Text]}
    umsetzung:                     # heutige physische Objekte des Bereichs
      - {titel: V_FACT_A, quelle: ${DB_ZUGRIFF}.V_FACT_A}
    produkte:
      - {id: "A.1", titel: Produkt 1, pilot: true, dashboard: bereich_a}

  - id: S1
    art: subject_area
    titel: Subject Area 1
    entitaeten:
      - {id: e1, titel: Entität 1, quelle: ${DB_REUS}.E1, kern: true}
      - {id: e2, titel: Entität 2, status: fehlt}
      - {id: e3, titel: Entität 3, quelle: ${DB_REUS}.E3, zusatz: true}   # umgesetzt, nicht in der Vorlage

beziehungen:
  - {von: e1, nach: e3, kard: "1:n"}
```

- `status` im YAML ist der **Plan**: `vorhanden`, `ableitbar`, `teilweise`, `fehlt`.
- Der **Ist-Stand** kommt live aus der Datenbank (`/catalog/status`, eine Verbindung für alle Objekte, Cache je Umgebung):

  | Ist-Stand der `quelle` | angezeigter Status |
  |---|---|
  | existiert nicht | `fehlt` |
  | existiert, 0 Zeilen | `leer` |
  | existiert, Zeilen > 0 | Plan-Status (Default `vorhanden`) |
  | existiert, kein SELECT-Recht für den Studio-User | Plan-Status, Hinweis „kein Lesezugriff“, ohne Zeilenzahl |
  | ohne `quelle` | Plan-Status (Default `fehlt`) |

- Abdeckung eines Bereichs: Anteil seiner Kennzahlen mit `vorhanden`/`ableitbar` (`teilweise` zählt halb); ohne Kennzahlen seine eigenen Dimensionen. Conformed Dimensions zählen nicht mit.
- Status wird immer mit Form und Text gezeigt (● vorhanden, ◉ ableitbar, ◐ teilweise, ○ leer, ✕ fehlt), nie nur über Farbe.

### Dashboard (`<id>.yml`)

Die ID ist der Dateiname. Vollständiges Beispiel: `cfg/dashboards_beispiel/etl_betrieb.yml`.

```yaml
titel: Bereich A
beschreibung: Kurzer Text unter dem Titel
gruppe: Statistik
reihenfolge: 10                  # Sortierung der Reiter
cache_ttl: 300                   # Sekunden
datenstand: sql/a_datenstand.sql # optional: erste Spalte der ersten Zeile
min_zelle: 5                     # optional, sonst aus katalog.yml
objekte:                         # optional: Objekte für /status
  - ${DB_ZUGRIFF}.V_FACT_A
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
    optionen:
      x: JAHR
      y: ANZAHL
      serie: KATEGORIE
      serien:                            # optional: Reihenfolge, Beschriftung, Farbe je Serienwert
        - {wert: K1, titel: Kategorie 1, farbe: viz-series-1}
        - {wert: K9, titel: Fehler, farbe: status-critical}
      zelle_spalten: [ANZAHL]            # Werte < min_zelle werden ausgeblendet
      echarts: {legend: {top: bottom}}   # optional, wird in die ECharts-Option gemischt
```

**Filtertypen:** `jahr` (Default auch `aktuell`, `aktuell-1`), `zahl` (`min`, `max`), `datum` (Default auch `heute`), `auswahl` (`werte: [{wert, titel}]`), `text` (max. 200 Zeichen). Der Zustand steht im URL-Hash (`#d=<id>&<filter>=<wert>`), Links lassen sich also teilen.

**Widget-Optionen (umgesetzt):**

| Typ | Optionen |
|---|---|
| `kpi` | `wert`, `format` (`zahl`, `prozent`, `dauer_s`), `vergleich`, `vergleich_titel`, `status` (`{warning, serious, critical}` – ab Schwelle Symbol und Text) |
| `table` | `spalten`, `titel` (`{SPALTE: Text}`), `format` (`{SPALTE: …}`), `max_anzeige` |
| `bar` | `x`, `y` (Spalte oder Liste), `serie`, `serien`, `gestapelt`, `horizontal`, `format`, `renderer`, `echarts` |
| `line` | `x`, `y`, `serie`, `serien`, `flaeche`, `zoom` (Default ab 60 Punkten), `format`, `renderer`, `echarts` |
| `boxplot` | `x`, `werte` (fünf Spalten: unten, Q1, Median, Q3, oben – vom SQL gerechnet), `anzahl`, `einheit`, `beschriftung`, `format`, `echarts` |

Jedes Diagramm hat eine Umschaltung auf die Tabellenansicht derselben Daten (Barrierefreiheit, Kontrast) und einen PNG-Export. Ab 9 Serien werden die kleinsten zu „Übrige“ zusammengefasst; die Farbreihenfolge ist fest (`--viz-series-1` … `--viz-series-8` in `frontend/style.css`, CVD-geprüft).

## 5. Übersichtsseite

Die Startseite des Tabs ist eine Übersicht, die der Katalog vollständig erzeugt. Sie ist so aufgebaut wie die übliche Architekturgrafik „Data-Mart-Bereiche plus Business-Objekt-Modell“ und hat zwei Reiter.

### Reiter „Consumable“ (Widget-Typ `area-map`; `star-map` zeigt nur den Stern)

| Zone | Inhalt |
|---|---|
| Kopfzeile | eine Kachel je Bereich `art: mart` in der Reihenfolge `nr`: Nummer, Titel, Anzahl Produkte, Priorität, Schutzniveau. Die Rahmenfarbe zeigt den Abdeckungsgrad (vorhanden / teilweise / fehlt) |
| linke Spalte | Conformed Dimensionen mit ihren Attributen und ihrem Status |
| Mitte | Stern des gewählten Bereichs: Fakt in der Mitte mit Schlüsseln und Kennzahlen, Dimensionen darum, Linien zu den Conformed Dimensionen. Jedes Element trägt Status (Symbol und Text), umgesetztes Objekt und Zeilenzahl |
| darunter | „Umsetzung heute“ (Objekte aus `umsetzung`) und die Datenprodukte mit Status, Pilot-Kennzeichen und Link aufs Dashboard |
| Fußzeile | kompakte Kästen der übrigen Bereiche (Fakt, Dimensionen, Kennzahlen, Anzahl Produkte, Schutzniveau) |

Klick auf eine Kachel wechselt den Stern; Klick auf ein Produkt mit `dashboard:` öffnet dieses Dashboard. Lücken öffnen ein Side-Panel mit dem Text aus `luecke`.

### Reiter „Reusable“ (`widget-subject-map`)

- Ein Kasten je Bereich `art: subject_area`, darin die Entitäten mit Status, umgesetzter Tabelle und Zeilenzahl; oben die Summe (laut Vorlage / umgesetzt / fehlen).
- Entitäten mit `kern: true` sind hervorgehoben.
- Beziehungen zwischen Entitäten stehen im Katalog unter `beziehungen: [{von, nach, kard}]` und werden als Linien gezeichnet.

### Einbindung

Die Reiter sind zwei Dashboards mit je einem Widget ohne SQL:

```yaml
titel: Übersicht Data Marts
gruppe: Übersicht
reihenfolge: 1
widgets:
  - id: marts
    titel: ""            # leer: Kartenkopf ausblenden
    typ: area-map        # bzw. subject-map, star-map (optionen.bereich)
    daten: katalog       # liefert {katalog, status, dashboards} statt SQL-Ergebnis
    pos: {x: 0, y: 0, b: 12, h: auto}   # h: auto = Höhe nach Inhalt
    optionen: {bereich: m1}             # zuerst gewählter Bereich
```

- Der gewählte Bereich steht im URL-Hash (`bereich=`); ein Produkt mit `dashboard:` verlinkt auf dieses Dashboard, sobald es existiert.
- Klick auf ein Element öffnet ein Side-Panel mit Status, Quelle, Ist-Stand, Lücke und Attributen.
- Unter 1100 px Breite stapeln sich die Spalten, die Verbindungslinien entfallen.

## 5a. Info-Panel je Widget

Jede Widget-Kachel hat ein Info-Symbol (ⓘ). Es öffnet rechts ein Seitenpanel (kein Modal; `frontend/components/dashboard-info.js`, Schließen mit × oder Escape):

| Abschnitt | Inhalt | Quelle |
|---|---|---|
| Erläuterung | was das Widget zeigt, Definition der Kennzahl | `erlaeuterung:` am Widget; sonst der Kommentarblock (`--`) am Anfang der SQL-Datei |
| Hinweise | Vorbehalte, farbig hervorgehoben | `hinweise:` (Liste); sonst die `luecke` des Katalog-Elements aus `katalog:` |
| Im Katalog | Titel und Plan-Status des verknüpften Elements | `katalog:` als Punktpfad aus IDs, z. B. `bereich.fakt.kennzahl` |
| Datenmodell | gelesene Objekte als Fakt/Dimension/Objekt mit Zeilenzahl, Join-Spalten | Analyse des gerenderten SQL (`backend/app/services/sql_analyse.py`): Objekte nach `FROM`/`JOIN`, Art nach Namenskonvention (`V_FACT_*`/`FACT_*`, `V_DIM_*`/`DIM_*`), Joins aus `alias.SPALTE = alias.SPALTE` |
| Herkunft | Baum von der gelesenen View bis zu den Tabellen; mehrfach erreichte Objekte einmal aufgelöst („siehe oben“) | View-Definitionen aus `DBC.TablesV.RequestText` (lange Texte: `DBC.TableTextV`), über die Verbindung der Umgebung, nicht über `dashboards_db`; Cache 30 min |
| SQL | umschaltbar: mit eingesetzten Filterwerten / Vorlage mit Platzhaltern; Kopieren | gerendertes SQL; die Werte sind nur zur Anzeige eingesetzt, ausgeführt wird weiter mit Bind-Parametern |
| Letzter Lauf | Datenstand, Zeilen, Laufzeit, Cache | Rückgabedaten des Widgets |

- Das SQL ist für alle Rollen sichtbar. Der Client kann weiterhin kein SQL senden.
- Zeilenzahlen großer Views können Sekunden dauern: Das Panel lädt erst ohne (`_zeilen=0`) und setzt die Zahlen nach.
- Die Analyse ist bewusst einfach (reguläre Ausdrücke): `FROM` in Funktionen (`EXTRACT(YEAR FROM …)`) wird übersprungen; Teradata-View-Texte trennen Zeilen mit `\r`.
- Übersichts-Widgets (`daten: katalog`) haben kein SQL; das Panel nennt dann den Katalog als Quelle (die Übersichtsseiten blenden den Kartenkopf und damit das Symbol aus).

```yaml
  - id: quoten
    typ: line
    titel: Quote je Jahr
    erlaeuterung: "Quote = A / (A + B + C), je Jahr in Prozent."
    hinweise:
      - "Gruppen sind ein Vorschlag, fachlich zu bestätigen."
    katalog: bereich_a.fakt_a.quote
    sql: sql/quoten.sql
```

## 6. Umsetzungsschritte

1. ✅ Read-only-Helfer, Router, Service, Platzhalter und Cache.
2. ✅ ECharts als Vendor-Datei, Shell, Registry, Widgets `kpi`, `table`, `bar`, `line`; Test mit dem neutralen Beispiel „ETL-Betrieb“. Weitere Diagrammtypen (`pie`, `heatmap`, `sankey`, `map`) nach Bedarf; `boxplot` ist mit den Pilot-Dashboards dazugekommen.
3. ✅ Übersichtsseite: `area-map`, `star-map`, `subject-map` (`frontend/components/widgets/widget-katalog.js` als gemeinsame Basis).
4. ✅ Kundendashboards im Kunden-Workspace (erste: Pilot-Dashboards eines Einsatzes).
5. ✅ Info-Panel je Widget (Abschnitt 5a).

## 7. Offene Punkte

- Dark Mode: Die Studio-Oberfläche hat keinen; die Diagrammfarben sind nur für hellen Hintergrund geprüft.
- `meta_service.py` und `td_readonly.py` haben gleichartige Verbindungs- und Cache-Helfer; zusammenführen.
- Weitere Diagrammtypen (`pie`, `heatmap`, `sankey`, `map`) nach Bedarf der Kundendashboards.
- Teradata erlaubt `PERCENTILE_CONT` nicht in Unterabfragen: Perzentile je Kennzahl in eigener Widget-Abfrage rechnen.

- Eigener Read-only-User je Umgebung für das Dashboard.
- Zuordnung Schutzniveau → Rolle.
- Ob Definitionen später auch über die GUI bearbeitet werden (wie `diagrams.py`) oder nur als Dateien gepflegt werden.
