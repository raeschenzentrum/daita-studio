# Job-Detail & ETL-Wizard – Analyse & Konzept

> Status: Analyse / Konzept (noch nicht implementiert)
> Referenz: Screenshot `daita-studio/docs/screenshots/job-detail-metadaita.png`
> BACKLOG-Task: **F2**

---

## 1. Ist-Zustand (daita-studio heute)

### `job-detail.js` (Komponente C4)

| Feature | Vorhanden | Fehlt |
|---------|-----------|-------|
| Job-Header (Name, Source→Target) | ✅ | |
| Tab „Info" (Metadaten) | ✅ | |
| Tab „Steps" – Liste | ✅ | |
| Tab „Ausführen" + Polling | ✅ | |
| Tab „History" | ✅ | |
| Step aufklappen → Step-Detail-Panel | ❌ | **Vollständiges Detail-Panel** |
| Step-Detail: Step-ID, Name, Reihenfolge, Kategorie | ❌ | |
| Step-Detail: Ausführungstyp (SQL Template / SQL Inline) | ❌ | |
| Step-Detail: Template-Pfad mit Bearbeiten-Button | ❌ | |
| Step-Detail: „Mit Parametern anzeigen"-Button | ❌ | |
| Step-Detail: Einstellungen (Aktiv, Kritisch, Skip, Rollback) | ❌ | |
| Step-Detail: Parameter-Sektion (Key-Value + Neu-Button) | ❌ | |
| Step CRUD: Step hinzufügen, bearbeiten, löschen | ❌ | |
| Job-Toolbar: SQL Export | ❌ | |
| Job-Toolbar: Als Template speichern | ❌ | |
| Job-Toolbar: Template Import | ❌ | |
| Job-Toolbar: Im Dashboard | ❌ | |

### `etl-wizard.js` (Komponente C6)

| Feature | Vorhanden | Fehlt |
|---------|-----------|-------|
| Template wählen | ✅ | |
| Zieltabellenname / Job-Name | ✅ | |
| Spaltenauswahl (ColumnSelector) | ✅ | |
| Zusammenfassung Schritt 3 | ✅ | |
| Technische Spalten nur als Badge-Preview anzeigen | ✅ (Badge) | |
| Technische Spalten wirklich in META_COLUMN anlegen | ❌ | **Backend legt sie an, Frontend zeigt sie nicht** |
| SK-Erstellung erklären / anzeigen | ❌ | Key-Tabelle wird still erzeugt |
| Surrogate Key-Spaltenname konfigurieren | ❌ | |
| Business Key-Spalten explizit als PK markieren | ❌ | |
| Parameter-Review vor dem Speichern | ❌ | Alle generierten Werte sichtbar machen |

---

## 2. Was das Backend bereits kann (metadaita Template-Service)

Die **gesamte Komplexität** liegt im Backend (`template_service.py`).
Das Frontend hat diese Logik bisher nur rudimentär abgebildet.

### Beim `create_job_from_template`-Aufruf passiert:

1. **Job anlegen** in `META_ETL_JOB` mit PK/Hash/ValidFrom/ValidTo/IsCurrent-Spalten
2. **Steps kopieren** aus `META_ETL_JOB_STEP_TEMPLATE` → `META_ETL_JOB_STEP`
3. **Parameter automatisch generieren** aus Tabellenname + Config (`parameter_rules.yml`):
   - `SOURCE_TABLE`, `TARGET_TABLE`, `SOURCE_DATABASE`, `TARGET_DATABASE`
   - `KEY_TABLE`, `KEY_DATABASE`
   - `NATURAL_KEY_EXPRESSION` (zusammengesetzt aus PK-Spalten)
   - `STAGING_TABLE`, `NEW_RECORDS_TABLE`, `CHANGED_RECORDS_TABLE`
   - `SK_COLUMN` (z.B. `IDENTITAET_SK`)
   - `HASH_COLUMNS`, `SELECT_COLUMNS`, `INSERT_COLUMNS`
4. **Key-Tabelle erstellen** (`KEY_IDENTITAET`) wenn nicht vorhanden
5. **Zieltabelle erstellen** in META_TABLE wenn nicht vorhanden, inklusive:
   - Source-Spalten aus META_COLUMN
   - SCD2-Technische Spalten aus `parameter_rules.yml`:
     - `{CORE_NAME}_SK` (Surrogate Key)
     - `VALID_FROM`, `VALID_TO`, `IS_CURRENT`
     - `RECORD_HASH`
     - `CREATED_TIMESTAMP`, `LAST_UPDATED_TIMESTAMP`
     - `CREATED_BY`, `LAST_UPDATED_BY`

Das Frontend zeigt davon **nichts** — der User sieht nur das Endergebnis.

---

## 3. Was der User sehen will (Screenshot)

Das Screenshot zeigt die Job-Verwaltung aus der alten metadaita-Oberfläche:

```
[Job-Header: LOAD_UZMS01_TAAA_IDENTITAET_HISTORY   SUCCESS]
[MASTER_DATA_SCD2 | Source → Target | 9 Steps]
[▶ Starten]  [SQL Export]  [Als Template]  [Template Import]  [Im Dashboard]

┌─ STEPS (9) ──────────────┬─ Step Informationen ───────────────────────────┐
│ 1. Delete Target Table   │  Step ID:      30034                           │
│ 4. Create Staging Table  │  Name:         Insert New Records              │
│ 5. Generate Surrogate K. │  Reihenfolge:  10                              │
│ 7. Identify New Records  │  Kategorie:    SCD_TYPE2_INSERT                │
│ 8. Identify Changed Rec. │  Gehört zu:    LOAD_UZMS01_TAAA_IDENTITAET_H. │
│ 9. Close Old Versions    ├─ Ausführung ───────────────────────────────────┤
│►10. Insert New Records ◄ │  Ausführung:  📄 SQL Template                  │
│11. Insert Changed Vers.  │  Template:    scd_type2/insert_new_versions... │
│12. Calculate Statistics  │  [Template bearbeiten]  [Mit Parametern anz.] │
└──────────────────────────├─ Einstellungen ─────────────────────────────── ┤
                           │  Aktiv:             ✅ Ja                      │
                           │  Kritisch:          🔴 Ja (Abbruch)            │
                           │  Skip wenn leer:    Nein                       │
                           │  Rollback bei Fehler: ✅ Ja                    │
                           ├─ Parameter ──────────────────────────── [+Neu] ┤
                           │  …                                             │
                           └────────────────────────────────────────────────┘
```

**Kernprinzip:** Links Step-Liste (klickbar), rechts Split-Ansicht mit Step-Detail.

---

## 4. Konzept: job-detail.js – Erweiterung

### 4.1 Layout: Master-Detail innerhalb der Komponente

```
.jd-root
  .jd-header          ← Job-Name, Source→Target, Run-Status-Badge
  .jd-toolbar         ← ▶ Starten | SQL Export | Als Template | Im Dashboard
  .jd-content
    .jd-steps-panel   ← Links: Step-Liste (Nummern + Kategorie-Badge)
    .jd-step-detail   ← Rechts: Ausgeklapptes Step-Detail
```

Statt Tabs `Info | Steps | Run | History` →  
**Info und Steps nebeneinander** (Master-Detail), Run/History als separate Tabs.

### 4.2 Step-Liste (links)

- Nummerierte Liste (step_order)
- Step-Name + Kategorie-Badge (farbcodiert nach Kategorie)
- Klick → Rechts-Panel füllt sich
- Aktiver Step hervorgehoben
- `+ Step hinzufügen`-Button am Ende

### 4.3 Step-Detail-Panel (rechts)

#### Sektion: Step Informationen (read-only)
```
Step ID:      {step_id}
Name:         {step_name}
Reihenfolge: {step_order}
Kategorie:    {step_category}
Gehört zu:    {job_name}
```

#### Sektion: Ausführung (read-only + Actions)
```
Ausführung:  SQL Template  (oder: SQL Inline)
Template:    {sql_template_path}
[Template bearbeiten]   [Mit Parametern anzeigen]
```
- **Template bearbeiten** → öffnet Template-Editor (Side-Panel oder Modal)
- **Mit Parametern anzeigen** → Template-SQL mit eingesetzten Werten rendern (Preview)

#### Sektion: Einstellungen (editierbar)
```
Aktiv:              [Y/N Toggle]
Kritisch:           [Y/N Toggle]  → bei N: weiter trotz Fehler
Skip wenn leer:     [Y/N Toggle]  → Step überspringen wenn Quelltabelle leer
Rollback bei Fehler:[Y/N Toggle]
```
→ Speichern per `PATCH /api/jobs/{job_id}/steps/{step_id}`

#### Sektion: Parameter (editierbare Key-Value-Liste)
```
KEY_TABLE:          KEY_IDENTITAET        [✎]
SOURCE_TABLE:       TAAA_IDENTITAET       [✎]
TARGET_TABLE:       TAAA_IDENTITAET_H..   [✎]
STAGING_TABLE:      temp_taaa_identita..  [✎]
SK_COLUMN:          IDENTITAET_SK         [✎]
…
                                         [+ Neu]  [💾 Speichern]
```
→ Speichern per `PATCH /api/jobs/{job_id}/steps/{step_id}` mit Body `{parameters: {...}}`

### 4.4 Job-Toolbar (oben)

| Button | Farbe | Aktion |
|--------|-------|--------|
| ▶ Starten | grün | → Tab wechseln zu Run |
| SQL Export | blau-grau | → GET /api/jobs/{id}/sql-export → Download |
| Als Template | lila | → POST /api/templates/from-job/{id} |
| Template Import | lila | → Template-Step-Import-Dialog |
| Im Dashboard | grau | → `/index.html` oder Dashboard-Link |

---

## 5. Konzept: etl-wizard.js – Fehlende Transparenz

### 5.1 Problem

Der ETL-Wizard gibt dem User **keinen Einblick** in was beim Speichern passiert:
- Welche Steps werden erstellt?
- Welche Parameter werden berechnet?
- Welche technischen Spalten kommen dazu?
- Wird eine Key-Tabelle erstellt?

### 5.2 Schritt 3 erweitern: „Was wird erstellt?"

Schritt 3 (Zusammenfassung) soll zeigen:

```
📋 Template:     MASTER_DATA_SCD2
🗂 Steps (9):   DELETE_TARGET | STAGING | SK_GENERATION | SCD_TYPE2_NEW | ...
⚙ Technische Spalten (SCD2):
   IDENTITAET_SK    VALID_FROM    VALID_TO    IS_CURRENT
   RECORD_HASH      CREATED_TIMESTAMP    LAST_UPDATED_TIMESTAMP

🔑 Key-Tabelle:   KEY_IDENTITAET  (wird automatisch erstellt)

📊 Berechnete Parameter:
   SOURCE_TABLE:     TAAA_IDENTITAET
   TARGET_TABLE:     TAAA_IDENTITAET_HISTORY
   SK_COLUMN:        IDENTITAET_SK
   STAGING_TABLE:    temp_taaa_identitaet_staging
   KEY_TABLE:        KEY_IDENTITAET
   BUSINESS_KEY:     IDENTITAET_ID
   HASH_COLUMNS:     IDENTITAET_ID, VORNAME, NACHNAME, ...
```

→ Backend-Endpunkt: `POST /api/templates/{id}/preview` (dry-run ohne DB-Schreiben)

### 5.3 Business Key explizit wählen

Im Step 2 (Spaltenauswahl, ColumnSelector) muss der User den **Business Key** (PK) explizit markieren können.  
Aktuell: PK-Auswahl vorhanden, aber unklar welche Auswirkung sie hat.  
Soll klar beschriftet sein: **„Business Key (Primärschlüssel für SCD2)"**

---

## 6. Modulübergreifende Nutzung

`job-detail.js` muss in **beiden Modulen** funktionieren:

| Modul | Container | Verwendung |
|-------|-----------|-----------|
| `flow.html` | `.flow-side` (rechts, 420px) | Job-Detail beim Klick auf ⚙ Job |
| `jobs.html` | `#jobs-detail-panel` (Haupt-Bereich, breit) | Job-Detail bei Auswahl in Job-Liste |

**Unterschiede:**
- In `flow.html`: weniger Breite → Step-Detail blendet sich aus wenn zu schmal, oder nur Step-Liste zeigen
- In `jobs.html`: volle Breite → Master-Detail nebeneinander

Lösung: Responsive innerhalb der Komponente via `ResizeObserver` oder CSS:
```css
.jd-content { display: flex; gap: 0; }
.jd-steps-panel { width: 260px; flex-shrink: 0; }
.jd-step-detail { flex: 1; min-width: 0; }
@container (max-width: 500px) {
  .jd-step-detail { display: none; }   /* In flow.html: nur Liste */
}
```

---

## 7. Backend: Neue API-Endpunkte benötigt

| Endpunkt | Methode | Beschreibung |
|----------|---------|--------------|
| `/api/jobs/{id}/steps/{step_id}` | PATCH | Step-Einstellungen + Parameter speichern |
| `/api/jobs/{id}/steps` | POST | Neuen Step hinzufügen |
| `/api/jobs/{id}/steps/{step_id}` | DELETE | Step löschen |
| `/api/jobs/{id}/sql-export` | GET | Job SQL als Download |
| `/api/templates/from-job/{id}` | POST | Job als Template speichern |
| `/api/templates/{id}/preview` | POST | Dry-run: Parameter + Steps + techn. Spalten berechnen |
| `/api/jobs/{id}/steps/{step_id}/preview` | POST | Template + Parameter → fertiges SQL |

Die meisten davon existieren im `metadaita`-Backend bereits (`job_management.py`, `template_service.py`) und müssen nur als Router in `daita-studio/backend/app/api/jobs.py` exponiert werden.

---

## 8. Implementierungs-Reihenfolge

**Phase 1 – Sichtbarkeit (kein neues Backend nötig)**
1. `job-detail.js`: Step-Liste → Step-Detail-Panel (read-only) mit allen Feldern
2. `job-detail.js`: Einstellungen editierbar (PATCH auf bestehenden Step-Endpunkt)
3. `job-detail.js`: Parameter-Anzeige (Key-Value aus `step.parameters` JSON)

**Phase 2 – Interaktion**
4. `job-detail.js`: Parameter editieren + speichern
5. `job-detail.js`: „Mit Parametern anzeigen" → Template-Preview
6. `job-detail.js`: Job-Toolbar (Starten, SQL Export, Als Template)

**Phase 3 – Wizard-Transparenz**
7. `etl-wizard.js`: Schritt 3 erweitern um berechnete Parameter + Steps + techn. Spalten
8. Backend: `/api/templates/{id}/preview` implementieren

**Phase 4 – Step CRUD**
9. Step hinzufügen / löschen
10. Template Import

---

## 9. Abhängigkeiten zu bestehenden Dateien

| Datei | Was ist zu tun |
|-------|---------------|
| `frontend/components/job-detail.js` | Master-Detail-Layout, Step-Detail-Panel |
| `frontend/components/etl-wizard.js` | Schritt 3 erweitern, Business-Key-Labeling |
| `backend/app/api/jobs.py` | Neue Endpunkte (Step PATCH, Step POST, SQL Export) |
| `backend/app/services/job_management.py` | `update_step()` um alle Felder erweitern |
| `backend/app/api/templates.py` | `/preview`-Endpunkt |
