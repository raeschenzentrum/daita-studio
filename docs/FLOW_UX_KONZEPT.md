# Flow & Job-UX Konzept

> Status: Konzept / In Arbeit
> Ziel: Einheitlicher Workflow für Job-Erstellung und -Verwaltung in daita-studio

---

## Grundprinzipien UI

### ❌ Keine modalen Dialoge für Verwaltungsaufgaben

Modale Dialoge (Overlays, die den Rest der UI blockieren) sind **verboten** für Verwaltungsaufgaben.

**Stattdessen: Bottom-Panel oder Side-Panel je nach Platzbedarf**

| Aufgabe | Panel | Begründung |
|---------|-------|------------|
| Tabellen- / Spaltenverwaltung | **Bottom-Panel** | Spalten-Grid braucht horizontalen Platz (Name, Typ, Länge, PK, FK, PI …) — Side-Panel zu schmal. So bereits in daita-modeler gelöst. |
| Job-Verwaltung / Steps / History | **Side-Panel (rechts)** | Listeninhalt, kommt mit ~420px aus. Bereits so in `flow.html` umgesetzt. |
| Parameter bearbeiten | Inline im Step-Bereich | Aufklappbarer Abschnitt innerhalb des Side-Panels |
| Template-Preview | Inline / Bottom-Panel | Code-Block, braucht Breite |

**Bottom-Panel Verhalten (wie in daita-modeler):**
- Schiebt sich von unten hoch (animiert), überlagert nichts
- Eigene Tabs: `Spalten | Indizes | FKs | DDL`
- Schließbar per ✕
- Höhe: ~50% Viewport, resize-fähig

**Ausnahmen erlaubt** (kurze, destruktive oder einmalige Aktionen):
- Bestätigungs-Dialog vor Löschen (kleines Inline-Banner oder `confirm()`)
- ETL-Wizard bei **Ersterstellung** eines Jobs (mehrstufiger Workflow, braucht Fokus)

---

## Kontext: Wo passiert was?

### `flow.html` – Pipeline-Übersicht & Job-Erstellung

Die Flow-Seite ist der **primäre Einstiegspunkt** für den ETL-Workflow.

**Workflow:**
1. User klickt auf einen Layer (z. B. RAW → DISC)
2. Tabellenansicht öffnet sich darunter
3. Pro Tabelle gibt es zwei Zustände:

| Zustand | Anzeige | Aktion bei Klick |
|---------|---------|-----------------|
| Tabelle hat **noch keinen** ETL-Job | Pfeil/Button rechts **rot** | → Job-Erstellung öffnen (siehe unten) |
| Tabelle hat **bereits** einen ETL-Job | Pfeil/Button rechts **grün** | → Job-Verwaltung öffnen |

> Dieses Verhalten funktioniert in der alten Anwendung `metadaita` bereits gut und soll 1:1 übernommen werden.

---

### Detailfall: Job-Erstellung – Zieltabelle vorhanden oder nicht?

**Entscheidung: Option 1 + explizite Buttons (Option 3)**

#### Fall A: Zieltabelle existiert bereits
→ ETL-Wizard direkt öffnen, Zieltabelle vorbelegt

#### Fall B: Zieltabelle existiert noch **nicht**

Der ETL-Wizard erkennt selbst, dass keine Zieltabelle vorhanden ist, und zeigt automatisch einen vorgelagerten Schritt:

```
[Schritt 0: Zieltabelle anlegen]  →  [Schritt 1: Job konfigurieren]  →  [Speichern]
```

- Schritt 0 schlägt Tabellenname vor (z. B. Quelltabelle + `_HISTORY`, `_DISC` etc.)
- Spaltenstruktur kann aus Quelltabelle übernommen / angepasst werden
- Nach Anlage direkt weiter zu Schritt 1 — kein Kontextverlust

**Zusätzlich** sind in der Tabellenzeile explizite Buttons sichtbar:

```
[Tabellenname]   [⊕ Zieltabelle]   [⬡ Modeler]   [+ ETL]
                  ↑ nur wenn ZT fehlt
```

| Button | Sichtbar wenn | Aktion |
|--------|--------------|--------|
| **⊕ Zieltabelle** | Zieltabelle fehlt | → Tabellen-Subform (Erstellung), danach optional ETL-Wizard |
| **⬡ Modeler** | immer | → `modeler.html?table_id=X` |
| **+ ETL** (rot) | kein Job vorhanden | → ETL-Wizard (mit Auto-Erkennung ob ZT fehlt) |
| **⚙ Job** (grün) | Job vorhanden | → Job-Verwaltung (Subform) |

---

### `jobs.html` – Job-Verwaltung

- Jobs werden hier **verwaltet**, nicht primär erstellt
- Übersicht aller Jobs, Status, History, Steps
- Detailansicht: Steps mit Template + Parameter-Anzeige (wie in metadaita)
- Ausführen + History

---

## Job-Verwaltung: Steps, Templates & Parameter

### Step-Ansicht (wie in metadaita)

Jeder Job hat Steps. Pro Step wird angezeigt:
- Step-Nummer, Step-Typ
- Zugehöriges Template (aus `etl/sql_templates/`)
- Parameter des Steps (Key-Value aus JSON-Datei)
- Template-SQL mit eingesetzten Parametern (Vorschau / Preview)

### Template-Architektur (Architekturentscheidung)

| Aspekt | Alt (bisher) | Neu |
|--------|-------------|-----|
| Template-SQL | In DB-Tabelle oder pro Job dupliziert | Liegt **fix** in `etl/sql_templates/{TemplateJobName}/{TemplateStepName}.sql` |
| Parameter | Als JSON-Spalte in der Step-Tabelle (DB) | Als **JSON-Datei** pro Step pro Job in `etl/jobs/{job_id}/{step_id}.json` |
| Neues SQL gebraucht | Parametrierung anpassen | → **Neues Template** anlegen |

**Regeln:**
- Templates in `etl/sql_templates/` sind **unveränderlich** (fix, keine Kopien pro Job)
- Ein Step referenziert ein Template per relativem Pfad `{TemplateJobName}/{TemplateStepName}.sql`
- Kein Template wird pro Job in die DB kopiert
- Parameter-Werte für den spezifischen Step eines spezifischen Jobs liegen in einer JSON-Datei

**Ordnerstruktur:**

```
etl/
├── sql_templates/
│   ├── RAW_TO_DISC_SCD2/
│   │   ├── delete/delete_target_table.sql
│   │   ├── staging/create_staging_table.sql
│   │   ├── keys/generate_surrogate_keys_from_staging.sql
│   │   ├── scd_type2/identify_new_records.sql
│   │   ├── scd_type2/identify_changed_records.sql
│   │   ├── scd_type2/close_old_versions.sql
│   │   ├── scd_type2/insert_new_versions_with_sk.sql
│   │   └── common/calculate_statistics.sql
│   ├── DISC_TO_REUS_SCD2/
│   │   └── ...
│   └── common/                  ← template-übergreifend geteilte SQLs
│       └── ...
│
└── jobs/
    └── {job_id}/
        └── {step_id}.json
```

> **Hinweis aktueller Stand:** Der tatsächliche Pfad auf Disk ist `ddl/sql_templates/` (historisch bedingt).
> Zielstruktur laut Spezifikation ist `etl/sql_templates/`. Umbenennung = F4-Voraussetzung.

**Beispiel JSON-Parameterdatei** (`etl/jobs/42/101.json`):
```json
{
  "SOURCE_TABLE":  "UZMS01_TAAA_PERSON",
  "TARGET_TABLE":  "UZMS01_TAAA_PERSON_HISTORY",
  "SK_COLUMN":     "PERSON_SK",
  "BUSINESS_KEY":  "PERSON_ID"
}
```

Template-SQL enthält Platzhalter: `${SOURCE_TABLE}`, `${SK_COLUMN}` etc.
Bei Ausführung: Parameter aus JSON-Datei in Template einsetzen → fertiges SQL.

---

## Subforms (wiederverwendbare Komponenten)

Alle modalen Dialoge / Panels als **wiederverwendbare Subforms**, aufrufbar von mehreren Seiten.

### Bereits vorhanden
| Komponente | Datei | Status |
|------------|-------|--------|
| ETL-Wizard (Job-Erstellung) | `components/etl-wizard.js` | ✅ vorhanden |
| Job-Detail | `components/job-detail.js` | ✅ vorhanden |
| Table-Editor (Tabellenverwaltung) | `components/table-editor.js` | ✅ vorhanden |

### Geplant / anzupassen
| Subform | Zweck | Aufgerufen von |
|---------|-------|---------------|
| **ETL-Wizard** | Job erstellen; Schritt 0 wenn ZT fehlt | flow.html, modeler.html |
| **Job-Detail** | Job verwalten, Steps, Parameter, Ausführen | flow.html, jobs.html |
| **Tabellen-Subform** | ZT erstellen (wenn nicht vorhanden) / verwalten | flow.html, modeler.html |
| **Modeler** | ERD-Ansicht | flow.html, jobs.html |

---

## Offene Punkte / TODOs

- [ ] ETL-Wizard: Schritt 0 "Zieltabelle anlegen" wenn ZT nicht vorhanden
- [ ] Tabellenzeile in flow.html: Buttons `⊕ Zieltabelle`, `⬡ Modeler`, `+ ETL` / `⚙ Job`
- [ ] Roter/grüner Pfeil-Status in Tabellenzeile (wie in metadaita)
- [ ] Job-Detail: Step-Ansicht mit Template-Referenz + Parameter aus JSON-Datei
- [ ] Parameter-Speicherung: Von DB-JSON auf dateibasiert umstellen (`etl/jobs/{job_id}/{step_id}.json`)
- [ ] Ordner `ddl/sql_templates/` → `etl/sql_templates/` umbenennen (F4-F)
- [ ] Modeler-Button: Von Job-Zeile in Tabellen-Zeile verschieben (flow.html)
