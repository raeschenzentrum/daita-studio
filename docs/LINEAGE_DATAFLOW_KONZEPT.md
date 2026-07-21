# Lineage- & Dataflow-Ansicht – Konzept & Umsetzungs-Prompt

> Status: **Implementiert** (Variante A) – ETL-**und** View-Kanten (View-DDL live via sqlglot). Persistenz `META_VIEW_LINEAGE` optional/offen.
> Modul: `daita-studio`
> Verwandte Konzepte: [JOB_DETAIL_KONZEPT.md](JOB_DETAIL_KONZEPT.md)
> Ziel: Nachvollziehbarer Datenfluss vom **Consumable Layer** zurück bis in den **Raw Layer**

---

## 0. Kurz-Prompt (für die spätere Umsetzung)

> Baue in `daita-studio` eine **Lineage-/Dataflow-Ansicht**, die den Datenfluss
> eines fachlichen Datenprodukts **rückwärts** vom Consumable Layer über
> Reusable → Discoverable → Raw sichtbar macht.
>
> Einstieg: Auswahl **eines beliebigen Objekts in einem beliebigen Layer**
> (Tabelle oder View). Von dort wird die Herkunftskette rückwärts (upstream)
> ermittelt und in **RAW links → CONS rechts** dargestellt; das gewählte Objekt
> steht rechts, seine Quellen fächern nach links auf.
>
> Zwei Herkunfts-Mechanismen müssen kombiniert werden:
> 1. **ETL-Jobs** (`META_ETL_JOB`: `source_table_id → target_table_id`) – für
>    die materialisierten Ladestrecken (RAW→DISC-Tabellen sowie REUS-Tabellen,
>    deren Job-Quelle eine **DISC-View** ist).
> 2. **View-Abhängigkeiten** (SQL-Parsing der View-Definition via
>    `lineage_service.py` / sqlglot) – für die **DISC-Views** (fachliche
>    Transformation) und die **Consumable-Views** (kein ETL, greifen direkt
>    auf DISC zu).
>
> Wiederverwenden: (a) die horizontale **Layer-Leiste** aus `flow.html`,
> (b) die **Tabellen-Box-Darstellung** aus dem Modeler,
> (c) das **Einzelauswahl-/Zurückblätter-Muster** über die Layer.
>
> Umsetzung als **eigene Seite** `lineage-flow.html` (bestehende `lineage.html`
> bleibt unangetastet).
>
> Constraint: Zielsystem offline, **kein npm / kein Build**, Vanilla-JS-Komponenten,
> Assets lokal servieren.

---

## 1. Fachliche Ausgangslage & Herausforderung

Die Layer-Kette lautet (aus `META_LAYER`, sortiert nach `layer_sequence`):

```
SRC → RAW → DISC → REUS → CONS
🗄️     📦     🔍      ♻️      📊
```

| Layer | Objekt-Typ | Woher kommt die Herkunft (Lineage)? |
|-------|------------|-------------------------------------|
| RAW   | Tabellen   | ETL-Job / Import aus SRC |
| DISC  | Tabellen **und Views** | Tabellen: ETL-Job (`META_ETL_JOB`) RAW→DISC. **Views** = fachliche Transformation, referenzieren DISC-/RAW-Objekte (nur in **View-SQL**) |
| REUS  | **Tabellen** (materialisiert) | ETL-Job, dessen **Quelle eine DISC-View** ist (`META_ETL_JOB.source_table_id` → DISC-View) |
| CONS  | **nur Views** (**kein ETL**) | View-SQL, die **direkt auf DISC** zugreift (die REUS-Views werden **nicht** genutzt) |

> **Wichtig (Layer-Modell, vom Fachbereich bestätigt):** Die fachlichen
> Transformations-**Views liegen im DISC-Layer**, nicht in REUS. REUS enthält
> die daraus **materialisierten Tabellen**. CONS enthält ausschließlich Views,
> die **direkt auf DISC** aufsetzen (REUS wird von CONS nicht referenziert).

### Kernproblem

`META_ETL_JOB` liefert Lineage nur für **materialisierte** Strecken
(`source_table_id → target_table_id`). Für **Views** existiert **keine Job-Zeile** –
die Quellobjekte stehen nur in der **View-Definition** (`RequestText` in
`dbc.TablesV`). Damit die Kette lückenlos ist, muss die Ansicht **beide Quellen**
vereinen (Beispiel-Kette rückwärts):

```
CONS-View  ──(View-SQL parsen)──▶ DISC-Objekt (Tabelle oder View)
REUS-Tab.  ──(META_ETL_JOB)─────▶ DISC-View        (Job-Quelle ist eine View!)
DISC-View  ──(View-SQL parsen)──▶ DISC-/RAW-Tabelle
DISC-Tab.  ──(META_ETL_JOB)─────▶ RAW-Tabelle
RAW-Tab.   ──(META_ETL_JOB/Import)▶ SRC
```

---

## 2. Was bereits existiert (wiederverwendbar)

### 2.1 Layer-Leiste (`flow.html`)
- Horizontale Pipeline: `.pipe-node` pro Layer, klickbar, `.active`-State.
- `LAYER_ICONS = { SRC:'🗄️', RAW:'📦', DISC:'🔍', REUS:'♻️', CONS:'📊' }`
- State: `_layers[]`, `_connectionJobs["srcId:dstId"]`, `_selectedLayer`.
- Datenquellen: `GET /api/etl/layers`, `GET /api/etl/jobs`.
- **Übernehmen:** exakt diese Layer-Leiste als Kopf der neuen Ansicht, aber als
  **Fortschritts-/Positionsanzeige** der aktuell aufgeblätterten Kette.

### 2.2 Tabellen-Box (Modeler)
- `modeler.html` + `vendor/modeler-canvas.js` (JointJS/Backbone).
- Zeichnet Tabellen als Box mit Spalten, PK/FK-Icons (🔑 🔗 ⊕),
  Ansichts-Modi `columns | keys | info`.
- **Übernehmen:** die Box-Darstellung eines Objekts (Name, Layer-Badge,
  Typ-Badge Tabelle/View, Schlüsselspalten) als **Knoten** im Lineage-Graph.
  Für die erste Ausbaustufe reicht eine **leichte HTML/SVG-Nachbildung**
  der Box (ohne die volle JointJS-Engine), um im Flow-Layout frei zu positionieren.

### 2.3 Einzelauswahl + Zurückblättern
- Muster aus `metadata-explorer.js` / `data-flow.html`:
  Layer wählen → Tabellenliste → Objekt wählen.
- **Übernehmen:** Start = **eine** CONS-Tabelle/View; „Zurück"-Schritt lädt
  die Quellobjekte des aktuell fokussierten Objekts (nächster Layer links).

### 2.4 SQL-Lineage-Parser (Backend)
- `backend/app/lineage_service.py` (sqlglot): `parse_sql()` liefert
  `source_tables[]` und Spalten-Mappings mit `transform_type`
  (`DIRECT_MAPPING | TYPE_CONVERSION | CONDITIONAL_LOGIC`).
- View-DDL beziehbar über `layer_export_service._fetch_view_ddl()` bzw.
  `SELECT RequestText FROM dbc.TablesV` (siehe `template_service.py`).
- **Übernehmen:** genau dieser Parser liefert die **View → Quellobjekt**-Kanten.

### 2.5 Meta-Datenmodell (`meta_service.py`)
- `get_layers()`, `get_tables(layer_id, db_name, search)`, `get_columns(table_id)`,
  `get_foreign_keys()`.
- `META_TABLE.table_kind` (Alias `table_type`) unterscheidet **Tabelle vs. View**.
- **Übernehmen:** Knoten-Metadaten (Name, Layer, Typ, Spalten) kommen von hier.

---

## 3. Darstellung – **gewählt: Variante A**

### Variante A — **Layer-Swimlanes mit gerichtetem Fluss (GEWÄHLT)**

Vertikale Spalten (Swimlanes) je Layer, feste Reihenfolge **RAW links → CONS rechts**
(Lesefluss, sortiert nach `META_LAYER.layer_sequence`). Das gewählte Startobjekt
steht am weitesten rechts; seine Quellen fächern nach **links** auf. Objekte als
Tabellen-Boxen in der jeweiligen Lane, Kanten = Herkunft.

```
   RAW             DISC             REUS            CONS
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│📦 RAW_KND│───▶│🔍 T_KUNDE│───▶│♻️ T_KUNDE│    │📊 V_KUNDE│
│          │    │  _DISC   │    │ _REUS    │    │  (View)  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
                ┌──────────┐         ▲                │
                │🔍 V_KUNDE│┈┈┈┈┈┈┈┈┈┘ (ETL-Quelle    │ (View-SQL:
                │ _AUFBER  │◀┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┘  greift direkt
                └──────────┘   ist DISC-View)     auf DISC zu)
   Kante ── ETL-Job (durchgezogen)   Kante ┈┈ View-Abhängigkeit (gestrichelt)
```

- **Kanten-Semantik unterscheiden:**
  - **durchgezogen** = materialisiert via `META_ETL_JOB` (klickbar → Job-Detail).
  - **gestrichelt** = View-Referenz (klickbar → View-SQL / Spalten-Mapping).
- **Fokus-Kette hervorheben:** nur die Herkunftskette des gewählten Objekts
  ist voll eingefärbt, Rest ausgegraut.
- **Kopf = Layer-Leiste** aus `flow.html` als Orientierung.
- Vorteil: fachlich intuitiv, Layer-Zugehörigkeit sofort sichtbar, passt zur
  bestehenden Layer-Metapher.

### Variante B / C (verworfen für Phase 1)

- **B – Miller-Columns-Drilldown:** als späterer Kompaktmodus für schmale
  Container denkbar, nicht Teil von Phase 1.
- **C – freier JointJS-Graph:** zu aufwendig, Layer-Ordnung schwer erzwingbar –
  **nicht** verfolgt.

---

## 4. Interaktionskonzept (Variante A)

1. **Einstieg:** Layer wählen → Objektliste (Tabellen **und** Views) → ein
   **beliebiges** Objekt wählen (nicht auf CONS beschränkt).
2. **Auto-Trace:** Backend liefert die komplette Herkunftskette (upstream) als
   Graph (`nodes`, `edges`) bis RAW/SRC.
3. **Darstellung:** Swimlanes je Layer (**RAW links → CONS rechts**), Startobjekt
   rechts, Fokus-Kette hervorgehoben.
4. **Drilldown Kante:**
   - ETL-Kante → bestehende `job-detail`-Komponente (Steps/Parameter).
   - View-Kante → Panel mit View-SQL (später: Spalten-Mapping aus `lineage_service`).
5. **Drilldown Knoten:** Klick auf Box → Spalten (aus `get_columns`), Layer, Typ.
6. **Zurück/Weiter blättern:** einzelne Ebene expandieren/kollabieren,
   falls Auto-Trace zu groß wird (Tiefenlimit).

---

## 5. Backend – benötigte Endpunkte

Ziel: **ein** Graph-Endpunkt, der beide Mechanismen zusammenführt.

| Endpunkt | Methode | Beschreibung |
|----------|---------|--------------|
| `/api/lineage/dataflow/{table_id}` | GET | Herkunftsgraph für ein Zielobjekt (rückwärts), Param `?depth=n`, `?direction=upstream` |
| `/api/lineage/object/{table_id}/sources` | GET | Direkte Quellen **einer** Ebene (für manuelles Aufblättern) |
| `/api/lineage/view/{table_id}/sql` | GET | View-Definition (`RequestText`) + geparste Quellobjekte/Spalten-Mappings |

### Graph-Ableitung (Serverlogik)

Für ein Zielobjekt `T`:

```
Quellen(T):
  wenn T ist Tabelle mit ETL-Job:
      → META_ETL_JOB WHERE target_table_id = T.table_id  ⇒ source_table_id (Kante: ETL)
  wenn T ist View (table_kind='V'):
      ddl = SELECT RequestText FROM dbc.TablesV (DB, T.table_name)
      parsed = lineage_service.parse_sql(ddl)
      für jede Quelle in parsed.source_tables:
          match auf META_TABLE (db_name + table_name) ⇒ source_table_id (Kante: VIEW)
  rekursiv weiter je Quelle, bis Layer=RAW/SRC oder depth erreicht
```

- **Namens-Auflösung:** geparste `schema.table` → `META_DATABASE.database_name` +
  `META_TABLE.table_name` → `table_id`. Nicht auflösbare Quellen als
  „externer/unbekannter" Knoten markieren (nicht verschlucken).
- **Zyklenschutz:** besuchte `table_id` merken.
- **View-DDL persistieren (Entscheidung Q4):** View-SQL wird **live** aus
  `dbc.TablesV.RequestText` gelesen, aber das **Parse-Ergebnis persistiert**, damit
  nicht bei jedem Aufruf neu geparst werden muss. Vorschlag: neue Meta-Tabelle
  `META_VIEW_LINEAGE` (siehe unten). Erneutes Parsen nur bei fehlendem Eintrag
  oder Invalidierung (z. B. `RequestText`-Hash geändert).

### Persistenz: `META_VIEW_LINEAGE` (Vorschlag, DDL noch abzustimmen)

| Spalte | Typ | Bedeutung |
|--------|-----|-----------|
| `view_table_id` | INT | FK → `META_TABLE.table_id` (die View) |
| `source_table_id` | INT | aufgelöste Quelle (FK → `META_TABLE`), NULL wenn extern |
| `source_raw_name` | VARCHAR | roher `schema.table` aus dem Parser (für externe/unauflösbare) |
| `request_text_hash` | VARCHAR | Hash der geparsten View-DDL (Invalidierung) |
| `parsed_at` | TIMESTAMP | Zeitpunkt des Parsings |

> DDL-Anlage ist eine DB-Änderung → wird **vor** Umsetzung separat freigegeben.

### Response-Schema (Vorschlag)

```jsonc
{
  "root_table_id": 501,
  "nodes": [
    {
      "table_id": 501,
      "table_name": "V_KUNDE",
      "db_name": "MDP01_CONS",
      "layer_id": 5, "layer_code": "CONS",
      "object_type": "V",            // 'T' | 'V'
      "is_external": false
    }
  ],
  "edges": [
    {
      "from_table_id": 401,          // Quelle (weiter links / upstream)
      "to_table_id": 501,            // Ziel
      "edge_type": "VIEW",           // 'ETL' | 'VIEW' | 'IMPORT' | 'UNKNOWN'
      "etl_job_id": null,            // gesetzt bei edge_type='ETL'
      "columns": [ /* optional Spalten-Mapping bei VIEW */ ]
    }
  ]
}
```

---

## 6. Frontend – Komponente

- **Neue Seite** `lineage-flow.html` (Entscheidung Q6 – eigene Seite; die
  bestehende `lineage.html` bleibt unangetastet).
- **Neue Komponente** `components/lineage-graph.js` (Vanilla-JS-IIFE, `window.LineageGraph`),
  gerendert als **SVG** (Kanten) + **HTML-Boxen** (Knoten, absolut positioniert
  je Layer-Spalte). Kein npm/Build.
- **Datenfluss:**
  1. `GET /api/etl/layers` → Layer-Leiste (aus `flow.html` übernehmen).
  2. Objekt wählen → `GET /api/lineage/dataflow/{table_id}`.
  3. Knoten in Swimlanes nach `layer_id`/`layer_sequence` (**RAW links**)
     einsortieren, Kanten als SVG-Pfade, Kantentyp per Strichstil
     (ETL durchgezogen / VIEW gestrichelt).
- **Wiederverwendung Modeler-Box:** kleine Renderfunktion `renderNodeBox(node)`
  im Stil der Modeler-Tabelle (Name, Layer-Badge, Typ-Badge, Schlüssel-Icons).
- **Drilldown:** ETL-Kante → `JobDetail`-Komponente; View-Kante → View-SQL-Panel.

---

## 7. Datenmodell-Bezug (Meta)

| Zweck | Tabelle / Quelle | Feld |
|-------|------------------|------|
| Layer + Reihenfolge | `META_LAYER` | `layer_id`, `layer_code`, `layer_sequence` |
| Objekt + Layer + Typ | `META_TABLE` | `table_id`, `table_name`, `layer_id`, `table_kind` (`T`/`V`) |
| DB-Name | `META_DATABASE` | `database_name` (via `database_id`) |
| Spalten | `META_COLUMN` | `column_name`, `column_type`, `is_technical_key` |
| ETL-Kante | `META_ETL_JOB` | `source_table_id`, `target_table_id` |
| View-Kante | `dbc.TablesV.RequestText` | View-DDL → `lineage_service.parse_sql()` |
| FK (optional) | `META_FOREIGN_KEY` | fachliche Beziehungen als Zusatzkanten |

---

## 8. Implementierungs-Reihenfolge

**Phase 1 – Rückwärts-Trace nur über ETL (schnelle Sichtbarkeit)**
1. Endpunkt `/api/lineage/dataflow/{table_id}` (nur `META_ETL_JOB`-Kanten).
2. `lineage-graph.js`: Swimlanes + Knoten-Boxen + ETL-Kanten.
3. Layer-Leiste aus `flow.html` als Kopf.

**Phase 2 – View-Abhängigkeiten ergänzen (Kernstück)**
4. View-DDL laden (`RequestText`) + `lineage_service.parse_sql()`.
5. Namensauflösung geparster Quellen → `table_id`; unbekannte als externe Knoten.
6. VIEW-Kanten (gestrichelt) + Zyklenschutz + Caching.

**Phase 3 – Drilldown & Details**
7. ETL-Kante → `JobDetail`; View-Kante → View-SQL + Spalten-Mapping-Panel.
8. Knoten-Klick → Spaltenliste (`get_columns`).

**Phase 4 – Kompaktmodus & Feinschliff**
9. Miller-Columns-Fallback für schmale Container.
10. Tiefenlimit, manuelles Expand/Collapse, externe-Quellen-Markierung.

---

## 9. Getroffene Entscheidungen

| # | Frage | Entscheidung |
|---|-------|--------------|
| 1 | Startpunkt-Auswahl | **Jedes Objekt in jedem Layer** (Tabelle oder View), nicht nur CONS |
| 2 | Layout-Richtung | **RAW links → CONS rechts** (Lesefluss); Trace bleibt upstream |
| 3 | Lineage-Tiefe Stufe 1 | **Nur Objekt-Ebene** (kein Spalten-Mapping in Phase 1) |
| 4 | View-Quelle | **Live aus `dbc.TablesV`**, Parse-Ergebnis **persistieren** (`META_VIEW_LINEAGE`) |
| 5 | Layer-Modell | DISC hält die fachlichen **Transformations-Views** (Quelle für REUS); REUS = materialisierte **Tabellen**; CONS = **nur Views**, die **direkt auf DISC** zugreifen (REUS wird nicht referenziert) |
| 6 | Seite | **Eigene Seite** `lineage-flow.html`; bestehende `lineage.html` bleibt |
