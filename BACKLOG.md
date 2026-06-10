# daita-studio – Backlog

> Task-Tracking und Architektur-Referenz.
> Details zur Umsetzung: `docs/CHANGELOG.md`

---

## Architektur-Entscheidungen (Fundament)

### A1 – Shared Components (kein Code zweimal)

Jede Funktionalität existiert genau **einmal** als eigenständige JS-Komponente in `frontend/components/`.
Pages sind nur Shells – sie binden Komponenten ein, haben selbst keine Logik.

```
frontend/
├── components/
│   ├── api.js              ← zentraler API-Client (alle fetch()-Aufrufe hier)
│   ├── nav-header.js       ← gemeinsamer Navigation-Header
│   ├── job-detail.js       ← Job-Detail + Steps + Run-Button
│   ├── job-list.js         ← Job-Liste mit Filter + Suche
│   ├── table-editor.js     ← Spalten/Index/FK-Editor (beste Version: aus daita-modeler)
│   ├── column-selector.js  ← Spalten-Auswahl mit PK/Hash/Load-Checkboxen
│   └── etl-wizard.js       ← ETL + Zieltabelle anlegen (ein Schritt)
├── flow.html
├── modeler.html
├── jobs.html
├── lineage.html   (P2)
├── sources.html   (P2)
└── index.html
```

### A2 – Komponenten-Kommunikation via Custom Events

Komponenten sind vollständig entkoppelt. Kein direkter Aufruf zwischen Komponenten.

```javascript
// ETLWizard feuert nach erfolgreichem Anlegen:
document.dispatchEvent(new CustomEvent('studio:job-created', { detail: { jobId } }))
document.dispatchEvent(new CustomEvent('studio:table-created', { detail: { tableId } }))

// Flow/Jobs lauschen darauf und laden neu:
document.addEventListener('studio:job-created', () => flow.reload())
```

**Alle Studio-Events tragen das Präfix `studio:`**

### A3 – Zentraler API-Client

Kein direktes `fetch()` in Pages oder Komponenten – ausschließlich über `api.js`.

```javascript
// api.js exportiert:
api.jobs.list(), api.jobs.get(id), api.jobs.create(data), api.jobs.run(id)
api.tables.list(layerId), api.tables.get(id), api.tables.columns(id)
api.templates.list(), api.templates.apply(id, data)
api.layers.list(), api.layers.tables(id)
api.diagrams.list(), api.diagrams.save(name, data), api.diagrams.load(name)
api.fk.list(tableId), api.fk.create(data), api.fk.delete(id)
api.areas.list(), api.areas.create(data)
api.meta.import.candidates(db), api.meta.import.table(db, table)
```

### A4 – ETL + Zieltabelle: Ein Wizard, ein Schritt

Beim Erstellen eines ETL-Jobs wird die Zieltabelle **gleichzeitig** in META_TABLE/META_COLUMN angelegt.
Kein separater Schritt, kein Context-Switch. Die Zieltabelle erhält Status `DDL_PENDING` bis das DDL ausgeführt wird.

Dieser Wizard (`etl-wizard.js`) ist dieselbe Komponente in Flow und im Jobs-Modul.

### A5 – Backend: Ein Service, alle Module

Kein separater daita-modeler-Server. Alle APIs laufen auf Port **8015**.
Die daita-modeler-Services werden als neue Router in das bestehende daita-studio-Backend integriert.

---

## Milestone-Übersicht

| MS | Typ | Inhalt | Voraussetzung | Status |
|----|-----|--------|---------------|--------|
| **P0** | Infra | Basis-Migration metadaita → daita-studio | – | ✅ Erledigt |
| **B1** | Backend | Modeler-APIs: Meta, Import, Diagramme, FK, Areas | P0 | ✅ Erledigt |
| **B2** | Backend | Unified: Table-Create API (ETL + Zieltabelle in einem) | P0 | ✅ Erledigt |
| **C1** | Component | `api.js` – zentraler API-Client | P0 | ✅ Erledigt |
| **C2** | Component | `nav-header.js` – gemeinsamer Header | C1 | ✅ Erledigt |
| **C3** | Component | `table-editor.js` – Spalten/Index/FK-Editor | B1 + C1 | ✅ Erledigt |
| **C4** | Component | `job-detail.js` – Job-Detail + Steps + Run-Button | C1 | ✅ Erledigt |
| **C5** | Component | `column-selector.js` – Spalten-Auswahl PK/Hash/Load | C1 | ✅ Erledigt |
| **C6** | Component | `etl-wizard.js` – ETL + Zieltabelle anlegen (1 Wizard) | B2 + C3 + C5 | ✅ Erledigt |
| **C7** | Component | `job-list.js` – Job-Liste mit Filter/Suche | C1 + C4 | ✅ Erledigt |
| **M1** | Modul | `flow.html` – Layer-Übersicht + ETL-Status + Wizard | C2 + C4 + C6 | ✅ Erledigt |
| **M2** | Modul | `modeler.html` – ERD-Canvas + Properties (table-editor) | B1 + C2 + C3 | ✅ Erledigt |
| **M3** | Modul | `jobs.html` – Job-Verwaltung + Templates + History | C2 + C6 + C7 | ✅ Erledigt |
| **M4** | Modul | `index.html` – Startseite mit 6 Kacheln | C2 + M1..M3 | ✅ Erledigt |
| **M5** | Modul | `lineage.html` – Column Lineage | C2 | 📝 Offen (P2) |
| **M6** | Modul | `sources.html` – Source-Systeme | C2 | 📝 Offen (P2) |

---

## 📝 Offen

---

### F1 – Feature: Flow UX – Job-Erstellung, Steps & Template-Architektur

**Konzept:** `docs/FLOW_UX_KONZEPT.md`

Sammelt mehrere zusammenhängende UX- und Architektur-Änderungen rund um Flow, Job-Erstellung und Step-Verwaltung.

#### Teilaufgaben

**F1-A – Tabellenzeile in `flow.html`: neue Buttons**
- `⊕ Zieltabelle` (nur sichtbar wenn Zieltabelle fehlt) → Tabellen-Subform (Erstellung)
- `⬡ Modeler` (immer) → `modeler.html?table_id=X`
- `+ ETL` (rot, kein Job) → ETL-Wizard
- `⚙ Job` (grün, Job vorhanden) → Job-Verwaltung (Subform)
- Modeler-Button aus der Job-Zeile entfernen (liegt jetzt in Tabellenzeile)

**F1-B – ETL-Wizard: Schritt 0 "Zieltabelle anlegen"**
- Wizard prüft ob Zieltabelle vorhanden
- Falls nicht: vorgelagerter Schritt mit vorgeschlagenem Zieltabellenname
- Nach Anlage: direkt weiter zu Schritt 1 (kein Kontextverlust)
- Expliziter `⊕ Zieltabelle`-Button in Tabellenzeile als alternative Einstieg

**F1-C – Job-Detail: Step-Ansicht mit Template + Parameter**
- Pro Step: Template-Name + Link zum SQL
- Parameter-Anzeige als Key-Value (aus JSON-Datei)
- Preview: Template-SQL mit eingesetzten Parametern

**F1-D – Architektur: Parameter von DB-JSON auf Datei-basiert**
- Templates bleiben fix in `sql/template_sqls/` (unveränderlich, keine Kopien)
- Parameter pro Step pro Job als JSON-Datei: `params/jobs/<JOBNAME>/step_NN_TYP.json`
- Backend: Lesen/Schreiben der Parameterdateien statt DB-Spalte
- Dateinamenschema festlegen

**Voraussetzungen:** M1, M3, C4, C6

**Status:** 📝 Offen

---

### F2 – Feature: Job-Detail Master-Detail + Wizard-Transparenz

**Konzept:** `docs/JOB_DETAIL_KONZEPT.md`

Ergänzt `job-detail.js` um das vollständige Step-Detail-Panel wie in metadaita (Screenshot),
und macht den ETL-Wizard transparenter bzgl. was beim Speichern tatsächlich passiert.

#### Teilaufgaben

**F2-A – job-detail.js: Master-Detail-Layout**
- Links: Step-Liste (klickbar, Kategorie-Badge, step_order)
- Rechts: Step-Detail-Panel (read-only)
- Responsive: In schmalem Container (flow.html) nur Step-Liste

**F2-B – job-detail.js: Step-Detail-Panel (vollständig)**
- Sektion „Step Informationen": ID, Name, Reihenfolge, Kategorie, Gehört zu Job
- Sektion „Ausführung": SQL Template / Inline, Template-Pfad, Buttons „Template bearbeiten" + „Mit Parametern anzeigen"
- Sektion „Einstellungen": Aktiv, Kritisch, Skip wenn leer, Rollback bei Fehler (editierbar, Y/N Toggle)
- Sektion „Parameter": Key-Value-Liste (aus `step.parameters` JSON), editierbar, Speichern, + Neu

**F2-C – job-detail.js: Job-Toolbar**
- ▶ Starten (grün, prominent wie im Screenshot)
- SQL Export → Download
- Als Template → POST /api/templates/from-job/{id}
- Template Import
- Im Dashboard

**F2-D – etl-wizard.js: Schritt 3 „Was wird erstellt?"**
- Berechnete Parameter anzeigen (SOURCE_TABLE, TARGET_TABLE, SK_COLUMN, STAGING_TABLE, KEY_TABLE, …)
- Steps-Preview: welche Steps werden angelegt (Kategorie-Badges)
- Technische Spalten explizit aufzählen (nicht nur Badge, sondern mit Datentypen)
- Key-Tabellen-Erstellung nennen
- Backend: `/api/templates/{id}/preview` (dry-run)

**F2-E – Backend: Neue Endpunkte**
- `PATCH /api/jobs/{id}/steps/{step_id}` – Step Einstellungen + Parameter
- `POST /api/jobs/{id}/steps` – Step hinzufügen
- `DELETE /api/jobs/{id}/steps/{step_id}` – Step löschen
- `GET /api/jobs/{id}/sql-export` – SQL-Export Download
- `POST /api/templates/from-job/{id}` – Job als Template speichern
- `POST /api/templates/{id}/preview` – Dry-run Parameter + Steps + technische Spalten
- `POST /api/jobs/{id}/steps/{step_id}/preview` – Template + Parameter → fertiges SQL

**Voraussetzungen:** C4, C6, `metadaita` job_management.py als Referenz

**Status:** 📝 Offen

---

### F3 – Feature: Template-Versionierung / SQL-Fix als neues Template

Wenn ein Template-SQL korrigiert werden muss (Bug-Fix, neue Logik), soll der User:
1. Das bestehende Template kopieren (neuer Name / neues Verzeichnis)
2. Das SQL im Editor anpassen
3. Die betroffenen Jobs auf das neue Template umstellen

**Teilaufgaben:**
- F3-A: „Template kopieren" Button im Template-Editor Modal (`POST /etl/templates/copy`)
- F3-B: Step-Detail: Template-Pfad inline editierbar (neues Template zuweisen)
- F3-C: Übersicht welche Jobs/Steps ein Template verwenden (`GET /etl/templates/{path}/usages`)

**Status:** 📝 Offen

---

### F4 – Feature: Step-Parameter als JSON-File statt DB-Spalte

Aktuell werden Step-Parameter als JSON-String in `META_ETL_JOB_STEP.STEP_PARAMETERS` gespeichert.

**Ziel:** Parameter als Datei auf dem Filesystem:
```
etl/jobs/{job_id}/{step_id}.json
```

**Teilaufgaben:**
- F4-A: Backend `job_management.py`: Parameter-Lesen aus JSON-File (Fallback: DB-Spalte)
- F4-B: Backend `job_management.py`: Parameter-Schreiben in JSON-File (kein DB-Update mehr)
- F4-C: Backend: Migrationsskript bestehende DB-Parameter → JSON-Files exportieren
- F4-D: `PATHS["etl_jobs"]` in `config.py` eintragen (`etl/jobs/`)
- F4-E: Frontend `job-detail.js`: keine Änderung nötig (API bleibt gleich)
- F4-F: Ordner `ddl/sql_templates/` → `etl/sql_templates/` umbenennen + `PATHS["sql_templates"]` in `config.py` anpassen + `TEMPLATE_BASE_DIR` in `etl.py` prüfen

**Hinweis:** DB-Spalte kann nach Migration leer bleiben oder als Fallback erhalten bleiben.

**Status:** 📝 Offen

---

### F5 – Feature: Job-Folder DDLs + Löschen mit Objekt-Auswahl

**Kontext:** Ein ETL-Job legt beim Erstellen mehrere DB-Objekte an (Zieltabelle, SK-Tabelle).
Diese DDLs sollen im Job-Folder abgelegt werden, und beim Löschen des Jobs soll der User
explizit steuern können, welche Objekte wirklich entfernt werden.

#### F5-A – DDLs im Job-Folder ablegen

Beim `create_job_from_template` werden folgende DDL-Artefakte in `etl/jobs/{job_id}/` geschrieben:

```
etl/jobs/{job_id}/
├── create_target_table.ddl     ← CREATE TABLE Zieltabelle (generiert)
├── create_sk_table.ddl         ← CREATE TABLE SK-Tabelle (generiert, falls neu)
└── cleanup/
    ├── drop_target_table.sql   ← DROP TABLE Zieltabelle
    └── drop_sk_table.sql       ← DROP TABLE SK-Tabelle
```

**Teilaufgaben:**
- F5-A1: Backend `template_service.py`: DDL-Generierung für Zieltabelle + SK-Tabelle beim Job-Erstellen
- F5-A2: Backend: DDL-Dateien in `etl/jobs/{job_id}/` schreiben (nach DB-Commit)
- F5-A3: Backend: Cleanup-SQLs (`DROP TABLE`) ebenfalls im Job-Folder speichern
- F5-A4: `PATHS["etl_jobs"]` sicherstellen (Teilaufgabe von F4-D)

#### F5-B – Job löschen mit Objekt-Auswahl

Beim Klick auf „🗑 Löschen" in der Job-Toolbar erscheint **kein einfaches `confirm()`**,
sondern ein Panel mit allen betroffenen Objekten und Häkchen:

```
┌─ Job löschen: LOAD_UZMS01_TAAA_PERSON_HISTORY ─────────────────┐
│ Folgende Objekte werden gelöscht:                               │
│                                                                 │
│  ☑  ETL-Job               LOAD_UZMS01_TAAA_PERSON_HISTORY      │
│  ☑  Job-Steps (9)         alle Steps + Parameter               │
│  ☑  Job-Folder            etl/jobs/42/ (DDLs + Parameter)      │
│                                                                 │
│  ─── Datenbankobjekte (optional) ────────────────────────────── │
│  ☐  Zieltabelle           UZMS01_TAAA_PERSON_HISTORY           │
│  ☐  SK-Tabelle            KEY_PERSON                           │
│  ☐  META_TABLE Eintrag    Zieltabelle aus META_TABLE entfernen  │
│  ☐  META_COLUMN Einträge  Spalten aus META_COLUMN entfernen     │
│                                                                 │
│  ⚠ Datenbankobjekte sind standardmäßig NICHT ausgewählt.       │
│                                                                 │
│  [Abbrechen]                          [🗑 Ausgewähltes löschen] │
└─────────────────────────────────────────────────────────────────┘
```

**Regeln:**
- Job-Metadaten (Job, Steps, Parameter-JSONs) sind **immer** ausgewählt (nicht deselektierbar)
- Datenbankobjekte (Zieltabelle, SK-Tabelle, META_TABLE, META_COLUMN) sind **standardmäßig abgewählt**
- Wenn Datenbankobjekte gewählt: generiertes `DROP TABLE` SQL wird aus `cleanup/` geladen und angezeigt

**Teilaufgaben:**
- F5-B1: Backend `GET /api/jobs/{id}/delete-preview` → liefert Liste aller betroffenen Objekte
- F5-B2: Backend `DELETE /api/jobs/{id}` → erweiterter Body `{ drop_target_table, drop_sk_table, drop_meta_table, drop_meta_columns }`
- F5-B3: Frontend `job-detail.js`: Löschen-Button öffnet Objekt-Auswahl-Panel statt `confirm()`
- F5-B4: Panel zeigt generiertes DROP-SQL als Vorschau wenn DB-Objekte ausgewählt

**Voraussetzungen:** F4-D (etl_jobs Pfad), F5-A (DDLs im Job-Folder)

**Status:** 📝 Offen

---

### B1 – Backend: Modeler-APIs integrieren ✅

**Umgesetzt am:** 2026-06-08

- `backend/app/services/meta_service.py` – vollständig aus daita-modeler migriert
- `backend/app/services/import_service.py` – vollständig aus daita-modeler migriert
- `backend/app/api/modeler.py` – alle META-Endpunkte (prefix `/api/modeler`)
- `backend/app/api/diagrams.py` – Layout speichern/laden (prefix `/api/diagrams`)
- `backend/app/api/import_td.py` – DBC-Import (prefix `/api/import`)
- `backend/app/config.py` – `DB_CONFIG`, `META_SCHEMA`, `META_TABLES` ergänzt
- `backend/app/main.py` – alle 3 neuen Router registriert, Titel auf daita-studio

**Getestet:**
```bash
GET /api/modeler/layers        → 6 Layer ✅
GET /api/modeler/tables?layer_id=2 → 15 Tabellen ✅
GET /api/modeler/fk            → 10 FKs ✅
GET /api/diagrams              → [] ✅
GET /api/import/candidates?db=MDP01_RAW_LAYER → 14 Kandidaten ✅
GET /docs                      → 200 ✅
```

**Quelle:** `daita-modeler/backend/app/` (MetaService, ImportService, DiagramService)
**Ziel:** Neue Router in `daita-studio/backend/app/api/`

**Neue Endpunkte:**

| Methode | Endpoint | Beschreibung |
|---------|----------|-------------|
| GET | `/api/meta/layers` | Layer aus META_LAYER |
| GET | `/api/meta/databases` | Datenbanken aus META_DATABASE |
| GET | `/api/meta/tables` | Alle Tabellen aus META_TABLE |
| GET | `/api/meta/tables?layer={id}` | Tabellen gefiltert nach Layer |
| GET | `/api/meta/columns?table_id={id}` | Spalten aus META_COLUMN |
| GET | `/api/meta/indexes?table_id={id}` | Indizes aus META_INDEX |
| POST | `/api/meta/tables/{id}/columns` | Spalte anlegen |
| PUT | `/api/meta/columns/{id}` | Spalte bearbeiten |
| DELETE | `/api/meta/columns/{id}` | Spalte löschen |
| GET | `/api/fk?table_id={id}` | Logische FKs für Tabelle |
| POST | `/api/fk` | FK anlegen |
| DELETE | `/api/fk/{id}` | FK löschen |
| GET | `/api/areas` | Subject Areas |
| POST | `/api/areas` | Subject Area anlegen |
| GET | `/api/diagrams` | Diagramm-Layout-Liste |
| GET | `/api/diagrams/{name}` | Layout laden |
| POST | `/api/diagrams/{name}` | Layout speichern |
| DELETE | `/api/diagrams/{name}` | Layout löschen |
| GET | `/api/import/candidates?db={db}` | DBC-Tabellen noch nicht in META |
| POST | `/api/import/table` | Tabelle aus DBC nach META importieren |

**Neue Dateien:**
- `backend/app/api/modeler.py` – Meta, Index, Spalten-CRUD
- `backend/app/api/fk.py` – FK-Verwaltung
- `backend/app/api/areas.py` – Subject Areas
- `backend/app/api/diagrams.py` – Diagramm-Layouts
- `backend/app/api/import_td.py` – DBC-Import
- `backend/app/services/meta_service.py` – aus daita-modeler
- `backend/app/services/import_service.py` – aus daita-modeler

**Test:**
```bash
curl http://10.3.0.245:8015/api/meta/layers          # Layer-Liste
curl http://10.3.0.245:8015/api/import/candidates?db=MDP01_RAW_LAYER  # Kandidaten
curl http://10.3.0.245:8015/api/diagrams              # leere Liste []
```

---

### B2 – Backend: Table-Create API (ETL + Zieltabelle)

**Anforderung:**  
Wenn ein ETL-Job aus Template erstellt wird und die Zieltabelle noch nicht existiert,
wird sie **im selben API-Call** in META_TABLE + META_COLUMN angelegt.

**Erweiterung in `template_service.py`:**
- Wenn `target_table_id` nicht übergeben → `create_target_table_from_source()` aufrufen
- Erstellt META_TABLE-Eintrag (mit `ddl_status = 'PENDING'`)
- Erstellt META_COLUMN-Einträge (Source-Spalten + SCD2-Technische-Spalten aus `parameter_rules.yml`)
- Gibt `target_table_id` zurück, Job-Erstellung läuft weiter wie bisher

**Neues Feld in META_TABLE:**
```sql
ALTER TABLE MDP01_META.META_TABLE ADD ddl_status VARCHAR(20) DEFAULT 'OK';
-- Werte: 'OK' | 'PENDING' | 'ERROR'
```

**DDL-Flow:**
1. Job + Zieltabelle anlegen → `ddl_status = 'PENDING'`
2. ETLWizard zeigt „⚠️ DDL ausstehend" Badge
3. User klickt „DDL ausführen" → DDL generiert + ausgeführt → `ddl_status = 'OK'`

**Test:**
```bash
# Job erstellen ohne vorhandene Zieltabelle:
curl -X POST http://10.3.0.245:8015/api/templates/jobs/1/apply \
  -d '{"source_table_id": 5, "job_name": "LOAD_TEST", "create_target": true, ...}'
# Ergebnis: {"job_id": 42, "target_table_id": 99, "ddl_status": "PENDING"}
```

---

### C1 – Component: `api.js`

**Datei:** `frontend/components/api.js`

Zentraler API-Client. Alle Komponenten und Pages importieren nur dieses Modul.
Kein direktes `fetch()` außerhalb von `api.js`.

```javascript
const BASE = window.STUDIO_CONFIG.backend_url

export const api = {
  jobs:      { list, get, create, update, delete, run, history },
  steps:     { list, get, update, updateParams },
  templates: { list, get, apply, saveFromJob, delete },
  layers:    { list, tables },
  tables:    { list, get, columns, indexes, create, updateDdlStatus },
  columns:   { list, create, update, delete },
  indexes:   { list, create, delete },
  fk:        { list, create, delete },
  areas:     { list, create, update, delete },
  diagrams:  { list, load, save, delete },
  import:    { candidates, importTable },
  meta:      { syncColumns, compareColumns },
  ddl:       { generate, execute },
}
```

Einheitliche Fehlerbehandlung: alle API-Calls werfen `ApiError` mit `status` + `message`.

---

### C2 – Component: `nav-header.js`

**Datei:** `frontend/components/nav-header.js`

Gemeinsame Navigation für alle Pages. Eingebunden via:
```javascript
NavHeader.render(document.getElementById('app-header'), { active: 'flow' })
```

**Aussehen:**
```
╔══════════════════════════════════════════════════════════════════════╗
║  🎨 daita-studio  │  🔷 Flow  │  🗂 Modeler  │  ⚙️ Jobs  │  🔗 Lineage  │  🖥 Sources  ║
╚══════════════════════════════════════════════════════════════════════╝
```

Aktiver Tab hervorgehoben (weißer Hintergrund auf lila). Dark/Light/System Toggle rechts.

---

### C3 – Component: `table-editor.js`

**Datei:** `frontend/components/table-editor.js`
**Quelle:** Beste Implementierung aus `daita-modeler` (DM9/DM10 – vollständiger Spalten-Editor mit Charset, Casespecific, Nullable, Index-Zuordnung, DBC↔META-Diff)

```javascript
TableEditor.render(container, {
  tableId: 42,          // null = neue Tabelle
  mode: 'panel',        // 'panel' | 'modal'
  readonly: false,
  onSave: (tableId) => { ... }
})
```

**Tabs innerhalb des Editors:**
- **Spalten** – Name, Typ, Länge, PK, Hash, Nullable, Charset, Casespecific
- **Indizes** – PI / UPI / SI mit Spalten-Zuordnung
- **FKs** – Logische FK-Beziehungen
- **DBC-Diff** – Vergleich DBC.ColumnsV ↔ META_COLUMN + Sync-Button
- **DDL** – generieren, bearbeiten, ausführen

---

### C4 – Component: `job-detail.js`

**Datei:** `frontend/components/job-detail.js`

```javascript
JobDetail.render(container, {
  jobId: 42,
  mode: 'inline',    // 'inline' | 'panel' | 'modal'
  showRunButton: true
})
```

**Inhalt:**
- Job-Name, Template, Source → Target
- Steps-Liste mit Status-Icons
- Letzter Run: Zeitstempel, Dauer, Rows
- Buttons: [▶ Ausführen] [✏️ Parameter] [📋 Als Template] [→ Im Jobs-Modul]
- Feuert `studio:job-executed` nach erfolgreichem Run

---

### C5 – Component: `column-selector.js`

**Datei:** `frontend/components/column-selector.js`

```javascript
ColumnSelector.render(container, {
  tableId: 5,          // Source-Tabelle
  onChange: (selection) => { ... }
  // selection = { pk_columns, hash_columns, select_columns }
})
```

**Aussehen:**
```
Spalte              Typ           [PK] [Hash] [Laden]
────────────────────────────────────────────────────
AUFENTHALT_ID    INTEGER          ☑    ☑      ☑
PERSON_ID        INTEGER          ☐    ☑      ☑
EINREISE_DATUM   DATE             ☐    ☑      ☑
CREATED_AT       TIMESTAMP        ☐    ☐      ☐
────────────────────────────────────────────────────
[☑ Alle laden]  [Nur PK als Hash]
```

---

### C6 – Component: `etl-wizard.js`

**Datei:** `frontend/components/etl-wizard.js`

Der zentrale Wizard: ETL-Job + Zieltabelle anlegen in einem Schritt.
Dieselbe Komponente in Flow und Jobs-Modul.

```javascript
ETLWizard.render(container, {
  sourceTableId: 5,     // vorausgewählt (aus Flow-Kontext)
  mode: 'modal',        // 'modal' | 'inline'
  onSuccess: null       // null = Custom Event 'studio:job-created' reicht
})
```

**Wizard-Schritte:**
```
[1] Template + Namen
    Template:    [RAW to DISC SCD2 ▼]
    Job-Name:    [LOAD_AUFENTHALT_TO_HISTORY]  ← auto-generiert, editierbar
    Zieltabelle: [AUFENTHALT_HISTORY]          ← auto-generiert, editierbar
    
[2] Spalten auswählen  (= column-selector.js)
    + Preview der technischen SCD2-Spalten die hinzukommen
    
[3] Zusammenfassung + Anlegen
    ✅ Zieltabelle AUFENTHALT_HISTORY wird in META angelegt
    ✅ ETL-Job LOAD_AUFENTHALT_TO_HISTORY wird erstellt
    ⚠️  DDL muss noch ausgeführt werden
    [Abbrechen]  [✅ Anlegen]
```

Nach Erfolg:
```javascript
document.dispatchEvent(new CustomEvent('studio:job-created', { detail: { jobId, targetTableId } }))
```

---

### C7 – Component: `job-list.js`

**Datei:** `frontend/components/job-list.js`

```javascript
JobList.render(container, {
  filter: { layerId: null, hasJob: null },
  onSelect: (jobId) => JobDetail.render(detailContainer, { jobId })
})
```

Liste mit: Job-Name, Source→Target, letzter Status, letzter Run-Zeitpunkt.
Filter: Layer, Status (OK/Error/Nie gelaufen).

---

### M1 – Modul: `flow.html`

**Frage:** Was passiert gerade in meinem DWH?

**Layout:**
```
╔══════════════════════════════════════════════════════════════╗
║  nav-header (active: flow)                                   ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  ┌── RAW ──────────────────┐  ──►  ┌── DISC ─────────────┐  ║
║  │  zas_einkommen     ✅   │       │  EINKOMMEN_HISTORY ✅│  ║
║  │  taaa_person       ✅   │       │  PERSON_HISTORY    ✅│  ║
║  │  zas_aufenthalt    ✅   │       │  [+ ETL erstellen]   │  ║
║  └─────────────────────────┘       └─────────────────────┘  ║
║                                                              ║
║  ═══════════ Detail (inline, job-detail.js) ══════════════   ║
║  📋 zas_einkommen → EINKOMMEN_HISTORY                        ║
║  [▶ Ausführen]  [✏️ Parameter]  [📋 Als Template]           ║
╚══════════════════════════════════════════════════════════════╝
```

**Verhalten:**
- Layer anklicken → Tabellen-Liste klappt auf (inline)
- Verbindungs-Pfeil anklicken → Jobs dieser Verbindung (inline)
- Tabelle MIT Job → `JobDetail.render()` inline darunter
- Tabelle OHNE Job / `[+ ETL erstellen]` → `ETLWizard.render()` als Modal
- Nach `studio:job-created` → Layer-Ansicht lädt neu

**Abhängigkeiten:** C2 + C4 + C6

---

### M2 – Modul: `modeler.html`

**Frage:** Wie ist mein Datenmodell aufgebaut?

**Layout:** Aus `daita-modeler/frontend/index.html` übernommen – bewährt, funktioniert.
Änderungen:
- App-eigener Header entfernt → `nav-header.js` (C2) eingebunden
- Properties-Panel rechts: `table-editor.js` (C3) statt eigenem Code
- Bei Tabellen mit ETL-Job: kleines Badge + Link → Flow

**Ablauf:**
- Tabellen-Node Doppelklick → `TableEditor.render()` im Properties-Panel
- Import-Panel: `api.import.candidates()` + `api.import.importTable()`
- Diagramm Speichern/Laden: `api.diagrams.*`
- Bottom-Panel: DBC↔META Diff (aus daita-modeler übernehmen)

**Abhängigkeiten:** B1 + C2 + C3

---

### M3 – Modul: `jobs.html`

**Frage:** Welche ETL-Jobs existieren, wie verwalte ich sie?

**Layout:**
```
╔══════════════════════════════════════════════════════════════╗
║  nav-header (active: jobs)                                   ║
╠══════════════════════════════════════════════════════════════╣
║  [Jobs]  [Templates]  [History]                              ║
╠═════════════════════════╦════════════════════════════════════╣
║  job-list.js            ║  job-detail.js (mode: 'panel')     ║
║                         ║                                    ║
║  🔍 Suche...            ║  (Job ausgewählt)                  ║
║  [+ Neuer Job]          ║                                    ║
╚═════════════════════════╩════════════════════════════════════╝
```

**Tabs:**
- **Jobs** – `job-list.js` + `job-detail.js`
- **Templates** – Template-Liste + Detail (Steps anzeigen, löschen)
- **History** – Ausführungs-History, Logs

**[+ Neuer Job]** → `ETLWizard.render()` als Modal (selbe Komponente wie Flow)

**Abhängigkeiten:** C2 + C4 + C6 + C7

---

### M4 – Modul: `index.html` (Startseite)

6-Kacheln-Übersicht. Jede Kachel zeigt Modul-Name, Kurzbeschreibung und Quickstats.

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ 🔷 Flow     │  │ 🗂 Modeler  │  │ ⚙️ Jobs     │
│ 4 Layer     │  │ 42 Tabellen │  │ 18 Jobs     │
│ 18 Jobs     │  │ 7 Diagrams  │  │ 3 Templates │
└─────────────┘  └─────────────┘  └─────────────┘
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ 🔍 Metadata │  │ 🔗 Lineage  │  │ 🖥 Sources  │
│ (→ Modeler) │  │ P2          │  │ P2          │
└─────────────┘  └─────────────┘  └─────────────┘
```

**Abhängigkeiten:** C2 + M1 + M2 + M3

---

### M5 – Modul: `lineage.html` *(P2)*

Column-Level Lineage Visualisierung.
Backend-Service bereits in metadaita vorhanden, noch nicht produktionsreif.

**Abhängigkeiten:** C2

---

### M6 – Modul: `sources.html` *(P2)*

Source-System-Verwaltung (MSSQL, ODBC).
Backend-Service bereits in metadaita vorhanden, noch nicht produktionsreif.

**Abhängigkeiten:** C2

---

## 🔄 In Bearbeitung

<!-- aktuell nichts -->

---

## ✅ Erledigt

### P0 – Basis-Migration metadaita → daita-studio ✅

**Umgesetzt am:** 2026-06-08

- Verzeichnisstruktur angelegt
- Alle Backend-Services, APIs, Models aus metadaita migriert
- `config.py`: relativer Pfad (kein hardcoded Install-Pfad mehr)
- `cfg/config.yml`: Ports 8015 (Backend) / 9015 (Frontend)
- `frontend/config.js`: API-URL auf Port 8015
- `bin/start.sh`: daita-studio Branding
- `pyproject.toml`: Name `daita-studio`
- `.gitignore`: `database.yml` + `connections.json` ausgeschlossen
- `git init` + `git remote add origin git@github.com:raeschenzentrum/daita-studio.git`
- Test: Backend startet ✅, Health-Endpoint antwortet ✅
- Erster Commit: `1cfcb1f`

---

## Abhängigkeitsgraph

```
P0 (✅)
 ├── B1 ──────────────────────────────────────────────► M2
 ├── B2 ──────────────────────────────────────► C6
 ├── C1 ──► C2 ──────────────────────────────► M1, M2, M3, M4
 │    ├──► C3 (braucht B1) ──────────────────► M2
 │    ├──► C4 ──────────────────────────────► M1, M3
 │    ├──► C5 ──────────────────────────────► C6
 │    └──► C7 (braucht C4) ─────────────────► M3
 └── C6 (braucht B2 + C3 + C5) ────────────► M1, M3

Empfohlene Reihenfolge:
P0 → B1 → B2 → C1 → C2 → C3 → C4 → C5 → C6 → C7 → M1 → M2 → M3 → M4
```

---

## GUI-Design-Referenz

**Farbschema:** `#667eea → #764ba2` (lila Gradient, aus metadaita übernommen)
**Dark/Light/System Toggle:** aus daita-modeler übernehmen
**Schrift:** System-Font-Stack (kein externer Font-Load)
**Icons:** Unicode Emoji (kein Icon-Font nötig)
**CSS-Variablen:**
```css
--primary:   #667eea
--secondary: #764ba2
--success:   #28a745
--warning:   #ffc107
--danger:    #dc3545
--bg:        #f8f9fa  (light) / #1a1a2e  (dark)
--card-bg:   #ffffff  (light) / #16213e  (dark)
--border:    #e9ecef  (light) / #2a2a4a  (dark)
```
