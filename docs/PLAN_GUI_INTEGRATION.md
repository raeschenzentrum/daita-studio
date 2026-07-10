# Plan: Layer-Bulk-Export wiederverwendbar machen & in daita-studio GUI einbauen

Ziel: Das einmalige Generieren der Layer-Load-Scripts (aktuell via
`generate_export.py` + manuell gezogene `_meta/*.json`) zu einer **wiederholbaren,
GUI-gesteuerten Funktion** in daita-studio ausbauen.

---

## 0. Vorab: „daita-modeler" vs. „daita-studio" – macht das einen Unterschied?

**Nein.** Die erzeugten Scripts hängen **nicht** vom daita-modeler ab.

Die Scripts werden ausschließlich aus daita-studio-Quellen gerendert:

| Baustein | Ort | Rolle |
|----------|-----|-------|
| `SQLTemplateEngine` | `daita-studio/backend/app/services/template_engine.py` | Rendering (`${PARAM}`-Substitution) |
| SQL-Templates | `daita-studio/etl/sql_templates/` | Vorlagen je Step-Kategorie |
| Job-/Step-Parameter | `daita-studio/etl/jobs/{job_id}/{step_id}.json` | konkrete Werte |
| Metadaten | Teradata `MDP01_META` (+ `dbc` für Views) | Jobs, Steps, FKs, View-DDL |

`daita-modeler` ist ein separates Modellierungs-Tool und erzeugt **keine**
Load-Scripts. Die Namensverwechslung früher hat also **keinen Einfluss** auf die
generierten Artefakte – sie wären mit jedem Namen identisch.

---

## 1. Ist-Zustand (Stand heute)

```
Einmal-Pipeline (manuell):
  MCP-Teradata  →  4 Result-JSONs  →  _consolidate.py  →  _meta/*.json
                                                              │
                          generate_export.py  ◀──────────────┘
                          (lädt Engine via importlib, rendert,
                           kommentiert DDL_CREATE aus, schreibt Dateien)
                                      │
                                      ▼
                       raw_to_disc/  disc_to_reus/  ddl/  views/
```

Schwächen für Wiederverwendung:
- `_meta/*.json` werden **manuell** via MCP gezogen → nicht reproduzierbar per Klick.
- Engine wird per `importlib` aus Dateipfad geladen (Workaround, kein Service).
- FK-Topologie & REUS-Reihenfolge teils hartkodiert.
- Kein UI-Einstieg; Ausführung nur über CLI.

> **Bereits behoben:** Pfade (`sql_templates`, `etl_jobs`, `export_layers`) und der
> Engine-Import laufen jetzt über die zentrale Backend-Config `config.PATHS`
> (`cfg/config.yml`) statt hartkodiert / `importlib`.

---

## 2. Zielbild

Ein **`LayerExportService`** im Backend, der live aus der DB liest und das gleiche
Ergebnis erzeugt – auslösbar per REST-Endpoint und GUI-Button „**Layer-Export**"
(Pendant zum bestehenden „SQL Export" je Einzeljob).

```
GUI „Layer-Export"  →  POST /api/export/layer  →  LayerExportService
                                                      │
        ┌─────────────────────────────────────────────┤
        │ 1) MetadataReader  (MDP01_META + dbc)        │
        │ 2) FkOrderResolver (Kahn-Topologie)          │
        │ 3) SQLTemplateEngine (bestehend)             │
        │ 4) StepActivationPolicy (DDL inaktiv etc.)   │
        │ 5) ArtifactWriter (Dateien + ZIP)            │
        └─────────────────────────────────────────────┘
                                                      │
                              ZIP-Download / Ordner im sql/-Export
```

---

## 3. Umsetzungs-Schritte (inkrementell, je testbar)

### Phase A – Backend-Kern (ohne GUI)
1. **`MetadataReader`** (`backend/app/services/`): kapselt die SQL-Queries, die
   bisher manuell via MCP liefen:
   - Jobs je Transition (`META_JOB` join `META_TABLE`/`META_LAYER`),
     Layer-IDs: **RAW=1, DISC=2, REUS=3, CONS=4** (nicht die alten Code-Kommentare!).
   - Steps je Job (`META_JOBSTEP`, inkl. `step_category`, `is_active`, Template-Pfad).
   - FKs (`META_FOREIGN_KEY`: child/parent table_id) – existieren **nur** für DISC.
   - View-DDL (`SELECT RequestText FROM dbc.TablesV WHERE … TableKind='V'`).
   → ersetzt `_meta/_consolidate.py` und die manuellen MCP-Calls.
2. **`FkOrderResolver`**: Kahn-Topologie über `META_FOREIGN_KEY`.
   Für REUS (keine FK-Metadaten): konfigurierbare Fallback-Reihenfolge oder
   Ableitung aus dem DISC-Pendant. → entfernt die Hartkodierung.
3. **`StepActivationPolicy`**: zentrale Regeln als Konfiguration:
   - `DDL_CREATE` → auskommentiert (inaktiv)
   - `DELETE_TARGET` → aktiv
   - `STAGING` (VOLATILE) → aktiv
   - optional: Flag „Staging auch inaktiv", „DELETE weglassen" (Delta-Modus).
4. **`LayerExportService`**: orchestriert 1–3 + nutzt die bestehende
   `SQLTemplateEngine` (jetzt sauber injiziert statt `importlib`).
5. **`ArtifactWriter`**: schreibt die nummerierten Dateien + optional ein ZIP.
6. **Pfade ausschliesslich aus `config.PATHS`** (Quelle: `cfg/config.yml`):
   `sql_templates`, `etl_jobs` und der neue Schluessel **`export_layers`**
   (`sql/export_layers`) kommen zentral aus der Backend-Config – **keine**
   hartkodierten Pfade (`Path(__file__).parent.parent / …`) und **keine**
   Redundanz mit anderen Modulen. Erfuellt das Projekt-Prinzip
   (copilot-instructions: Pfade zentral in `config.py`, nie hartkodiert).
   → bereits im Einmal-Skript `generate_export.py` umgesetzt.

### Phase B – REST-API
6. Endpoint **`POST /api/export/layer`** mit Parametern:
   ```json
   {
     "transition": "raw_to_disc | disc_to_reus | all",
     "include_ddl": true,
     "include_views": true,
     "mode": "initial_load | delta",
     "output": "zip | folder"
   }
   ```
   Antwort: ZIP-Stream oder Pfad + Manifest (Datei-Liste, FK-Reihenfolge).

### Phase C – GUI
7. Im daita-studio Frontend (analog „SQL Export"-Button):
   - neuer Button **„Layer-Export"** auf der Layer-/Übersichtsseite.
   - Dialog mit den API-Parametern (Transition, DDL/Views ja/nein, Modus).
   - Download-Trigger des ZIP; Fortschritts-/Ergebnisanzeige (Job-/Datei-Anzahl).
   - **Frontend nur GUI** – keine Logik (Projekt-Prinzip: Logik im Backend).

### Phase D – Qualität & Doku
8. Unit-Tests: `FkOrderResolver` (Topologie), `StepActivationPolicy` (Aktiv/Inaktiv),
   `MetadataReader` (gegen Mock/Fixture).
9. Integrationstest: Vergleich des neuen Live-Outputs mit den jetzt erzeugten
   Referenzdateien (Golden-Master).
10. Die bestehende `AUSFUEHRUNG.md` als Template ins ZIP aufnehmen (auto-generiert
    mit aktueller Job-Liste/Reihenfolge).

---

## 4. Mapping „alt → neu" (Migration)

| Heute (Einmal-Skript) | Künftig (Service) |
|------------------------|-------------------|
| Manuelle MCP-Queries | `MetadataReader` (nutzt bestehende DB-Connection aus `cfg/database.yml` via `etl_service._get_connection()`) |
| `_meta/_consolidate.py` | entfällt (Reader liefert direkt Objekte) |
| `_meta/*.json` | optionaler Cache/Debug-Dump, nicht mehr Pflicht |
| Hartkodierte REUS-Reihenfolge | `FkOrderResolver` + Config-Fallback |
| `importlib`-Load der Engine | regulärer Service-Import / DI |
| Hartkodierte Pfade (`Path(__file__)…`) | zentral aus `config.PATHS` / `cfg/config.yml` (Key `export_layers`) |
| `generate_export.py` (CLI) | `LayerExportService` + dünner CLI-Wrapper (bleibt nutzbar) |
| Aktiv/Inaktiv-Regeln im Code verstreut | `StepActivationPolicy` (eine Stelle) |

---

## 5. Offene Entscheidungen (vor Phase A klären)

1. ~~**DB-Zugang im Backend**~~ — **geklärt**: daita-studio besitzt bereits
   `cfg/database.yml` (Schema `MDP01_META`, Teradata-Connection). Die Datei ist
   per `.gitignore` ausgeschlossen (Credentials) und wird in `config.py` geladen.
   Der `LayerExportService` nutzt einfach die bestehende
   `etl_service._get_connection()` — keine neue Konfiguration nötig.
2. **REUS-Reihenfolge**: dauerhaft per Config pflegen, oder FK-Metadaten für REUS
   in `META_FOREIGN_KEY` nachziehen (saubere Lösung)?
3. **Delta-Modus**: Soll der Export-Dialog auch einen Inkrement-Modus (ohne
   `DELETE … ALL`) anbieten, oder bleibt es beim reinen Initial Load?
4. **Output-Ziel**: ZIP-Download im Browser, fixer Server-Ordner, oder beides?
