# Paket-Deployment (tools/paket)

Pakete bringen daita-studio und die Inhalte eines Einsatzes auf einen Zielserver ohne Netzverbindung zur Entwicklung. Konzept und Regeln: [`docs/PAKET_DEPLOYMENT_KONZEPT.md`](../../docs/PAKET_DEPLOYMENT_KONZEPT.md).

| Datei | Aufgabe | läuft auf |
|---|---|---|
| `paket_format.py` | ZIP mit `manifest.json` und `pruefsummen.sha256`, Werte-Serialisierung, Zerlegen von `SHOW TABLE`/`SHOW VIEW` | beiden |
| `meta_modell.py` | welche META-Tabellen transportiert werden, ID und fachlicher Schlüssel je Tabelle, Laufzeit-Spalten, `META_DEPLOY` | beiden |
| `studio_umgebung.py` | liest `cfg/config.yml`, `cfg/environments.yml` (sonst `cfg/database.yml`) wie das Backend | beiden |
| `export.py` | Export je Teil (Bibliothek); aufgerufen vom Aufrufskript im Kunden-Workspace | Entwicklung |
| `einspielen.py` | Plan, Einspielen, Protokoll, Rücknahme | Ziel |
| `abnahme.py` | Abnahmeprüfung (auch einzeln) | Ziel |

## Teile eines Pakets

| Teil | Inhalt | Einspielen |
|---|---|---|
| `software` | versionierte Dateien von daita-studio ohne Standort-Konfiguration (`cfg/*.yml`, `frontend/config.js`), ohne `etl/jobs`, `etl/sql_templates`; gepinnte Abhängigkeiten, Wheels (cp311, manylinux) | Dateien abgleichen; Wheels per `uv pip install --no-index` in die venv, mit der der Einspieler läuft, wenn sich die Abhängigkeiten geändert haben |
| `metaschema` | `SHOW TABLE/VIEW` des Meta-Schemas | fehlende Tabellen anlegen, neue Spalten per `ALTER`, Views ersetzen |
| `rechte` | Rollen, GRANTs, Rollen an User, Lese-User | `CREATE ROLE` falls fehlend, GRANTs (wiederholbar), Lese-User mit Passwort, das auf dem Ziel entsteht |
| `strukturen` | `SHOW TABLE/VIEW` der Datenbanken des Einsatzes; Voraussetzungen (z. B. RAW-Tabellen nur geprüft); Startdaten | wie `metaschema`; befüllte Tabellen werden nie geleert |
| `vorlagen` | `META_ETL_JOB_TEMPLATE`, `META_ETL_JOB_STEP_TEMPLATE`, `etl/sql_templates/` | Zeilen abgleichen (IDs 1:1), Dateien abgleichen |
| `jobs` | META-Inhalt (Tabellen, Spalten, Jobs, Steps, …), Step-Dateien `etl/jobs/<env>/<job_id>/` | Zeilen abgleichen (IDs 1:1), Dateien in den Ordner der Ziel-Umgebung |
| `dashboards` | Dashboard-Ablage des Kunden-Workspace | Dateien in den Pfad `dashboards:` der Ziel-Umgebung |

Reihenfolge beim Einspielen: software → metaschema → rechte → strukturen → vorlagen → jobs → dashboards → Abnahme.

## Ablauf

**1. Bauen (Entwicklung)** – mit dem Aufrufskript des Kunden-Workspace, z. B.

```
python <kunde>-lakehouse/deploy/paket_<kunde>.py              # Gesamtpaket
python <kunde>-lakehouse/deploy/paket_<kunde>.py --teil jobs  # Teilpaket
```

Vorher committen: der Teil `software` nimmt nur versionierte Dateien; die Version im Manifest trägt ein `+`, wenn ein Arbeitsbaum Änderungen hat.

**2. Übertragen** – ZIP und `.sha256` auf das Ziel; `sha256sum -c <paket>.zip.sha256`.

**3. Erstes Mal auf dem Ziel** – der Einspieler ist Teil der Software. Fehlt `tools/paket/` in der Installation, die Dateien aus dem Paket holen (im daita-studio-Root der Installation):

```
python -c "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); [z.extract(n, 'tmp_paket') for n in z.namelist() if n.startswith('software/code/tools/paket/')]" <paket.zip>
mkdir -p tools/paket && cp tmp_paket/software/code/tools/paket/* tools/paket/ && rm -r tmp_paket
```

**4. Einspielen (Ziel)** – Rollen, GRANTs, Views in CON und Tabellen im Meta-Schema brauchen meist mehr Rechte als der Betriebs-User von daita-studio. Dafür in `cfg/environments.yml` bei der Ziel-Umgebung einen eigenen User eintragen (wie `dashboards_db`):

```
    einspielen_db:
      user: '<admin-user>'
      password: '<passwort>'
```

Der Plan prüft die nötigen Rechte (`CREATE TABLE`, `DROP TABLE`, `CREATE/DROP VIEW`, `INSERT/UPDATE/DELETE` im Meta-Schema, `CREATE USER`) vorab; Rechte, die der Teil `rechte` desselben Pakets vergibt, zählen mit. `CREATE ROLE` und `GRANT … WITH GRANT OPTION` sind vorab nicht prüfbar.

Dann im Ordner `tools/paket` der Installation, mit deren venv-Python:

```
python einspielen.py <paket.zip>                 # Plan: was ändert sich, Konflikte, Hinweise
python einspielen.py <paket.zip> --ausfuehren    # einspielen, danach Abnahme
```

Optionen: `--teil <teil>` (mehrfach), `--loeschen` (was im Umfang nicht mehr im Paket ist, entfernen), `--leere-neu` (geänderte leere Tabellen neu anlegen). Bei Konflikten wird nichts eingespielt.

Je Lauf entsteht `log/paket/<lauf-id>/` mit `einspielen.log`, Sicherungen, `ruecknahme.json` und `abnahmebericht.txt` (Text ohne Fachdaten, darf zurück an die Entwicklung). Ausgeführte Läufe stehen in `<Meta-Schema>.META_DEPLOY`. Ein neu angelegter Lese-User legt seine Zugangsdaten als `lese_user_<user>.secret` in den Protokollordner: in `cfg/environments.yml` unter `dashboards_db` eintragen, dann die Datei löschen.

**5. Rücknahme** – schrittweise, in umgekehrter Reihenfolge:

```
python einspielen.py --zuruecknehmen <lauf-id>               # Plan
python einspielen.py --zuruecknehmen <lauf-id> --ausfuehren
```

META-Zeilen, Dateien und Views kommen auf den Vorher-Stand; neue Tabellen werden entfernt, solange sie leer sind. Neue Spalten, Python-Pakete und Rechte werden nicht automatisch zurückgenommen (das Protokoll nennt die Anweisungen).

## Regeln, die der Einspieler durchsetzt

- **IDs 1:1:** Eine Zeile mit gleicher ID und anderem fachlichem Schlüssel oder gleichem Schlüssel und anderer ID ist ein Konflikt. Identity-Spalten müssen `GENERATED BY DEFAULT` sein.
- **Zielbetrieb bleibt unberührt:** Läufe, Ladestände, Benutzer, Zeitplan, `META_VIEW_LINEAGE` (Cache) und Laufzeit-Spalten (`row_count` …).
- **Befüllte Tabellen:** neue Spalten per `ALTER`, `VARCHAR` verlängern per `ALTER`; jede andere Änderung ist ein Konflikt („Migration nötig“).
- **Rechte:** fehlende Rechte des Einspiel-Users sind Konflikte im Plan, nicht Fehler mitten im Lauf. `META_DEPLOY` wird angelegt, wenn möglich; sonst steht der Lauf nur im Protokollordner.
- **Leserechte:** Views, die der Einspiel-User nach dem Rollenkonzept nicht lesen darf, meldet die Abnahme als „nicht prüfbar“; `*_ACCESS`-Views prüft sie zusätzlich mit dem Lese-User aus `dashboards_db`.

## Noch nicht umgesetzt

- Migrationen befüllter Tabellen aus dem Kunden-Workspace (`migrationen/`) – heute Konflikt mit Anleitung.
- Rendern jedes Steps über die Template-Engine in der Abnahme.
- Delta-Pakete (Teil `software` ohne Wheels ist möglich, wenn sich die Abhängigkeiten nicht geändert haben).
