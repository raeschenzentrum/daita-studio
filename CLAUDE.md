# daita-studio

## Was das ist

- **Kundenunabhängiges Python-Framework** (Backend + Frontend) zur metadatengetriebenen Generierung von DWH-/Lakehouse-Load-Strecken auf Teradata; entwickelt per Vibe Coding.
- Kernprinzip: **Jobs → Job-Steps → Step-Templates** mit Variablen (Attribute/Attributslisten der jeweiligen Tabelle). Die Metadaten liegen in der Teradata-DB des jeweiligen Einsatzes (Meta-Schema, z. B. `MDP01_META`).
- **Strikt kundenneutral halten:** daita-studio kann bei anderen Kunden mit völlig anderen Business-Objekten eingesetzt werden. Framework-Code und Step-Templates dürfen keine Kundenfachlichkeit (Tabellennamen, Schemas, Business-Regeln) hart verdrahten — alles Kundenspezifische kommt aus Metadaten/Parametern.

## Verzeichnisse (Auswahl)

- `backend/`, `frontend/` — die Anwendung (u. a. `backend/app/services/template_engine.py` = `${PARAM}`-Rendering)
- `etl/sql_templates/` — die generischen Step-Templates je Kategorie (SCD2, Staging, Keys, …)
- `etl/jobs/{job_id}/{step_id}.json` — Job-/Step-Parameter (Achtung: inhaltlich kundenspezifisch; Auslagerung in ein Kunden-Workspace ist ein offener Punkt)
- `docs/PLAN_GUI_INTEGRATION.md` — Plan, den Layer-Bulk-Export als GUI-Funktion auszubauen
- `sql/generated/`, `ddl/generated/`, `tpt/generated/` — Generat-Ausgaben (gitignored)

## Kundenprojekt MDP01 (getrennt!)

Die **kundenspezifischen Artefakte** (generierte SQL-Exporte, DWH-Erkenntnisdokument, Qualitätslisten/Reporting) liegen **nicht** hier, sondern im Schwester-Repo **`../mdp01-lakehouse/`**:

- `../daita-docs/20_projekt_mdp01/ERKENNTNISSE_MVP_ETL.md` — Erkenntnisse aus dem MVP, Zielbild Zeitstempel/Historisierung, offene Entscheidungen. **Vor Architektur-Arbeit am Kundenprojekt lesen.**
- `mdp01-lakehouse/docs/AUSFUEHRUNG.md` — Ausführung der generierten Skripte
- `mdp01-lakehouse/sql/export_layers/` — die Generate
- `mdp01-lakehouse/reporting/` — Qualitätsliste QL1 (SQL + R)

Erkenntnisse aus dem Kundenprojekt, die das **Framework** betreffen (z. B. neue Template-Typen wie `RAW_TO_DISC_APPEND`, Delta-Steps, Delete-Erkennung), werden hier generisch umgesetzt.

## Arbeitsumgebung

- Repos liegen in einem **Linux-Remote-Container** (Zugriff per SSH vom Mac des Users); Code-Remotes auf GitHub (`raeschenzentrum/…`), private/Kunden-Repos im Homelab-Gitea (`192.168.113.121:3000/raes/…`).
- Teradata-Zugriff im Tooling via **MCP-Teradata**.
- **Doku-Vault `../daita-docs/`** (Wegweiser: `daita-docs/README.md`): Teradata-Theorie in `10_wissen/teradata/`, DWH-/ETL-Patterns in `10_wissen/patterns/`. Beim Umsetzen von Kundenprojekt-Erkenntnissen zuerst die **Projekt-Entscheidungen und Standards** prüfen: `20_projekt_mdp01/adr/` (ADRs) und `20_projekt_mdp01/konventionen/` (z. B. Namenskonvention, Datatype-Guidelines).

## Konventionen

- **Sprache:** Deutsch (Doku, Fach-Kommentare).
- **Tonalität in Bewertungen/Doku:** Der Code ist ein MVP; Erkenntnisse werden diskutiert und fließen in die Zielarchitektur ein. Formulieren als „Erkenntnis / Handlungsbedarf", nicht „Befund / Defekt / Schweregrad"; keine Schuldzuweisungen; Begründungen knapp; kein „bewusst" für MVP-Entscheidungen — stattdessen „bekannter offener Punkt / Übergangslösung / spätere Ausbaustufe".
