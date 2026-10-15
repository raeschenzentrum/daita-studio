# Prompt: daita-studio auf Air-Gapped-Server deployen

> Diesen Prompt einem Coding-Agent (Copilot / Claude / …) geben, der auf dem
> **Entwicklungsrechner MIT Internet** arbeitet und Zugriff auf das Repo hat.
> Der Zielserver ist **air-gapped (kein Internet, kein npm)**. Nur SSH/SCP/USB
> zum Zielserver verfügbar.

---

## Zielsystem-Profil (verifiziert 2026-07-20 auf dem Server)

| Punkt | Ist-Wert | Konsequenz |
|-------|----------|-----------|
| OS / Arch | **SLES 15 SP6**, `x86_64`, 64-bit | Plattform-Tag **`manylinux_2_17_x86_64`** (auch 2_28 ok) |
| glibc | **2.38** | manylinux2014- und manylinux_2_28-Wheels laufen |
| Python | **3.11.15** vorhanden unter `/usr/bin/python3.11` (System-`python3` = 3.6.15, **zu alt, nicht nutzen**) | venv auf **3.11**, Wheels für **`cp311`** ziehen |
| **uv** | **VORHANDEN** unter dem `tdops`-User: `/var/opt/teradata/tdops/.local/bin/uv` = **v0.9.24** (nicht im root-PATH → als `tdops` arbeiten oder vollen Pfad nutzen) | uv-Binary muss **nicht** zwingend ins Bundle; optional matching-Version als Fallback |
| **pip** | **fehlt** systemweit | Installation **komplett über uv** (uv braucht kein System-pip) |
| venv-Modul | vorhanden | `uv venv --python /usr/bin/python3.11` |
| Teradata-Client | `bteq`, `tbuild`, `tdload` vorhanden (`fastexport` fehlt) | BTEQ/TPT-Weg für Metadaten möglich; Python-`teradatasql`-Weg bleibt empfohlen |
| ODBC | nicht geprüft | nur relevant, falls externe Quellsysteme (MSSQL) angebunden werden |
| Teradata-Erreichbarkeit | noch nicht geprüft | vor Go-Live `bash -c 'echo > /dev/tcp/<HOST>/1025'` testen |

**Feste Entscheidungen daraus:** Ziel-Python = **3.11**, Wheel-Tags = **`cp311` / `manylinux_2_17_x86_64`**,
Installer = **uv 0.9.24 (bereits auf dem Ziel, `tdops`-User)**. Betrieb als `tdops` ausführen
(dort liegen uv, venv-Zielpfad und TPT-Tools).

> ⚠️ uv-Gotcha: `uv version` erwartet ein `pyproject.toml`; die uv-Eigenversion holt man mit `uv self version`.

---

## Rolle & Auftrag

Du bist DevOps-Engineer. Bringe die Anwendung **daita-studio** (FastAPI-Backend +
statisches Frontend, Teradata-Metadaten-Plattform) auf einen **air-gapped Linux-Server**.
Es gibt **keinen Internetzugang** auf dem Ziel, **kein npm**, **keinen Build-Schritt**.
Alle Abhängigkeiten müssen vorab auf dem Dev-Rechner beschafft und offline übertragen werden.

Arbeite in zwei Phasen:
1. **PREP** (auf dem Dev-Rechner mit Internet): Artefakte beschaffen und bündeln.
2. **DEPLOY** (auf dem Ziel, offline): Entpacken, installieren, konfigurieren, Metadaten importieren, starten.

**Wichtige Regel:** Bevor du auf dem Ziel etwas Änderndes tust (DDL, DB-Import, Dienste starten),
beschreibe den Schritt und warte auf OK. Read-only-Analyse ist frei.

---

## Fakten zur Anwendung (verifiziert im Repo)

| Punkt | Wert |
|-------|------|
| **Python** | `requires-python = ">=3.10"` (`pyproject.toml`). Auf dem **Ziel: 3.11.15** → dafür bauen. `bin/setup.sh` sucht `python3.12 → 3.11 → 3.10 → python3`. |
| **Paketmanager** | Ziel nutzt **uv 0.9.24** (bereits vorhanden unter `tdops`, pip fehlt). `pyproject.toml` hat `[tool.uv]` mit Hinweis `uv sync --offline`. **Keine `uv.lock` im Repo** → Lock vorab erzeugen. |
| **Backend-Framework** | FastAPI, Start via `uvicorn app.main:app` |
| **Frontend** | Statisches HTML/CSS/JS, **kein Node/npm**, kein Build. Ausgeliefert via `python -m http.server` |
| **Backend-Port** | `9021` (aus `cfg/config.yml → server.backend_port`) |
| **Frontend-Port** | `8021` (aus `cfg/config.yml → server.frontend_port`) |
| **Startskripte** | `bin/setup.sh` (Install, unterstützt `--offline` + `./wheels/`), `bin/start.sh` (start/stop/status) |
| **Venv-Pfad** | Default shared `/mnt/user/venv/daita-lakehouse`, alternativ `--local .venv` |

### Backend-Dependencies (`backend/requirements.txt` / `pyproject.toml`)
```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
pydantic>=2.9.2
sqlglot>=28.6.0
requests>=2.32.5
python-multipart>=0.0.12
PyYAML>=6.0
httpx>=0.27.0
teradatasql>=20.0.0
```

---

## ⚠️ Bekannte Air-Gapped-Fallstricke (ZWINGEND behandeln)

1. **Mermaid wird per CDN geladen** — `frontend/app.js` (Zeile 1) enthält:
   ```javascript
   import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
   ```
   → Offline **nicht** erreichbar, Diagramme brechen. **In PREP** die Datei
   `mermaid.esm.min.mjs` herunterladen, nach `frontend/vendor/` legen und den Import
   in `app.js` auf den lokalen Pfad umbiegen (z. B. `./vendor/mermaid.esm.min.mjs`).
   Prüfe zusätzlich alle Frontend-Dateien (`*.html`, `*.js`) auf weitere
   `https://`-Referenzen (CDNs, Fonts) und lokalisiere sie ebenfalls.

   **Bereits lokal:** Apache ECharts für die Dashboards liegt unter
   `frontend/vendor/echarts/echarts.min.js` (Version in `VERSION`, Lizenz in
   `LICENSE`/`NOTICE`) und braucht keinen Download.

2. **`teradatasql`** braucht ggf. plattformspezifische Wheels → beim Download die
   Zielplattform beachten (siehe PREP-Schritt zu `pip download`).

3. **Credentials-Config `cfg/database.yml` ist `.gitignore`d** → existiert nicht im
   Repo-Clone. Auf dem Ziel aus `cfg/database.yml.template` erzeugen und ausfüllen.

4. **Optionale LLM-Features** (SQL-Review) nutzen Ollama/LLM-Farm über HTTP.
   Wenn auf dem Ziel nicht vorhanden: in `cfg/conversion_config.yaml` `llm_review_enabled: false`
   setzen. `sqlglot`-Konvertierung läuft lokal ohne Netz.

---

## PHASE 1 — PREP (Dev-Rechner MIT Internet)

Ziel-Tags stehen fest: **Python 3.11 / `cp311` / `manylinux_2_17_x86_64`**, Installer **uv 0.9.24 (auf dem Ziel vorhanden)**.

1. **uv-Binary** — auf dem Ziel bereits vorhanden (`/var/opt/teradata/tdops/.local/bin/uv`, v0.9.24).
   Muss also **nicht** zwingend ins Bundle. **Optionaler Fallback** (falls Versions-
   konsistenz gewünscht): passende Version als Standalone-Binary mitliefern:
   ```bash
   curl -L -o uv-target.tar.gz \
     https://github.com/astral-sh/uv/releases/download/0.9.24/uv-x86_64-unknown-linux-gnu.tar.gz
   tar xzf uv-target.tar.gz        # -> uv-x86_64-unknown-linux-gnu/uv
   ```

2. **Lockfile erzeugen** (reproduzierbare Auflösung):
   ```bash
   cd daita-studio
   uv lock                          # erzeugt uv.lock aus pyproject.toml
   ```

3. **Wheels für das Ziel beschaffen** (cp311, manylinux) — als Offline-Quelle:
   ```bash
   # Variante A: mit uv (empfohlen, nutzt uv.lock)
   uv export --frozen --no-emit-project -o requirements.lock.txt
   pip download -r requirements.lock.txt -d ./wheels/ \
     --only-binary=:all: \
     --python-version 311 --implementation cp --abi cp311 \
     --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64
   ```
   Binäre Pakete, die zwingend als cp311-Wheel vorliegen müssen: `pydantic-core`,
   `PyYAML`, `teradatasql`, sowie durch `uvicorn[standard]`: `uvloop`, `httptools`,
   `watchfiles`. Falls ein Paket **nur** ein neueres Tag hat, das zweite `--platform`
   (2_28) greift — glibc 2.38 auf dem Ziel deckt beide ab.
   **Kontrolle:** `ls wheels/ | wc -l` und stichprobenartig auf `cp311`/`manylinux`
   im Dateinamen prüfen; reine `py3-none-any`-Wheels (fastapi, sqlglot, requests,
   httpx, python-multipart, starlette, anyio …) sind plattformneutral und ok.

4. **Mermaid + weitere CDN-Assets lokalisieren** (siehe Fallstrick 1).
   Download nach `frontend/vendor/`, Import in `frontend/app.js` anpassen,
   lokal im Browser gegen einen Test-Server verifizieren.

5. **Bundle schnüren** (alles, was das Ziel braucht):
   - kompletter `daita-studio/`-Baum **inkl.** `wheels/`, `uv.lock`,
     lokalisiertem `frontend/vendor/mermaid...`
   - uv liegt auf dem Ziel bereits vor — uv-Binary nur bei gewünschter Versionsfixierung mitgeben
   - **ohne** Secrets im Klartext — `cfg/database.yml` NICHT einpacken
   ```bash
   tar czf daita-studio-airgap.tgz daita-studio/
   sha256sum daita-studio-airgap.tgz > daita-studio-airgap.tgz.sha256
   ```

6. **Teradata-Metadaten exportieren** (Quell-Teradata → Datei), siehe Abschnitt
   „Metadaten-Export/Import" unten. Export-Dateien dem Bundle beilegen.

---

## PHASE 2 — DEPLOY (Zielserver SLES 15 SP6, OFFLINE)

1. **Übertragen & prüfen:** Bundle per SCP/USB kopieren, `sha256sum -c` verifizieren, entpacken.

2. **Offline installieren mit uv** (als `tdops`-User; System hat kein pip):
   ```bash
   # als tdops arbeiten (dort liegt uv, venv-Ziel, TPT-Tools)
   export PATH="/var/opt/teradata/tdops/.local/bin:$PATH"
   uv self version                             # erwartet 0.9.24

   cd daita-studio
   # venv explizit auf Python 3.11 des Ziels
   uv venv --python /usr/bin/python3.11 /mnt/user/venv/daita-lakehouse

   # Offline aus dem Wheel-Verzeichnis installieren (KEIN Netzzugriff)
   uv pip install --python /mnt/user/venv/daita-lakehouse/bin/python \
     --no-index --find-links ./wheels -r requirements.lock.txt
   ```
   Verifizieren: `.../bin/python --version` == 3.11.x und
   `.../bin/python -c "import fastapi, teradatasql, pydantic, uvicorn, yaml, sqlglot"`
   ohne Fehler.
   > Hinweis: `bin/setup.sh --offline` ist auf pip ausgelegt — da pip fehlt, hier den
   > uv-Weg oben verwenden statt `setup.sh`.

3. **Konfiguration setzen:**
   - `cfg/database.yml` aus `cfg/database.yml.template` erstellen und ausfüllen:
     Teradata `host/user/password`, `transaction_mode`, `metadata.schema` (Default `MDP01_META`),
     ggf. `source_systems`.
   - `cfg/config.yml`: Ports (`9021`/`8021`) und Pfade prüfen.
   - `frontend/config.js`: `backend_url` auf die **erreichbare Ziel-IP:Port** setzen
     (nicht `localhost`, wenn Clients extern zugreifen), z. B. `http://<ZIEL_IP>:9021`.
   - `cfg/connections.json` / `cfg/conversion_config.yaml`: LLM-Backends anpassen
     oder `llm_review_enabled: false`, wenn kein LLM erreichbar.

4. **Teradata-Metadaten importieren** (Datei → Ziel-Teradata), siehe unten.
   Auf dem Ziel muss das Meta-Schema (Default `MDP01_META`) existieren und die
   `META_*`-Tabellen müssen vorhanden sein, bevor Daten geladen werden.

5. **Starten & verifizieren:**
   ```bash
   ./bin/start.sh start
   ./bin/start.sh status
   ```
   `bin/start.sh` nutzt den Venv-Pfad `/mnt/user/venv/daita-lakehouse` (siehe Skript) —
   sicherstellen, dass das oben erzeugte venv dort liegt.
   Health-Checks:
   - Backend/API-Docs: `http://<ZIEL_IP>:9021/docs`
   - Frontend: `http://<ZIEL_IP>:8021/`
   - Metadaten-Dashboard: `http://<ZIEL_IP>:8021/metadata-dashboard.html`
   - Logs: `log/studio-backend.log`, `log/studio-frontend.log`
   - Mermaid-Diagramme im Browser prüfen (kein CDN-404 in der Konsole).

---

## Teradata-Metadaten: Export (Quelle) → Import (Ziel)

**Meta-Schema:** Default `MDP01_META` (konfigurierbar über `cfg/database.yml → metadata.schema`).

**Zu übertragende Tabellen** (aus `backend/app/services/meta_service.py`):
```
META_LAYER          -- Layer-Definitionen (zuerst, wird referenziert)
META_AREA           -- Subject Areas
META_DATABASE       -- logische Datenbanken
META_TABLE          -- Tabellen
META_COLUMN         -- Spalten
META_INDEX          -- Indizes (falls vorhanden)
META_FOREIGN_KEY    -- FK-Beziehungen (zuletzt, referenziert Tabellen/Spalten)
```
> Reihenfolge wegen Referenzintegrität beachten: erst `LAYER/AREA`, dann `DATABASE`,
> `TABLE`, `COLUMN`, `INDEX`, zuletzt `FOREIGN_KEY`.

### Empfohlener Export-Weg (Teradata-Bordmittel oder Python)
> **Auf dem Ziel verifiziert vorhanden:** `bteq`, `tbuild`, `tdload` (`fastexport` fehlt).
> Damit ist Variante A grundsätzlich nutzbar; für einen sauberen 1:1-Transport ist
> Variante B (Python) aber robuster und dialektunabhängig — **empfohlen**.

- **Variante A – TPT/BTEQ (Client-Tools auf dem Ziel vorhanden):**
  Pro Tabelle DDL (`SHOW TABLE MDP01_META.<T>`) sichern **und** Daten exportieren
  (`tbuild` TPT Export bzw. `bteq .EXPORT`) als portables Format; Import via
  `tdload`/`tbuild`. `fastexport` steht **nicht** zur Verfügung — kein FastExport-Job.
- **Variante B – Python mit `teradatasql` (empfohlen für Air-Gapped):**
  Auf dem Dev-Rechner (mit Zugriff auf Quell-Teradata) je Tabelle
  `SELECT * FROM MDP01_META.<T>` lesen und als CSV/NDJSON schreiben; zusätzlich
  `SHOW TABLE ...` für die DDL. Import auf dem Ziel per `teradatasql`-Batch-Insert.
  Nutzt exakt den Treiber, der ohnehin im venv liegt — keine zusätzlichen Binaries.

**Konkret zu erledigen:**
1. Vom Agenten ein kleines, **wiederverwendbares** Export-Skript vorschlagen
   (nutzt `cfg/database.yml` der Quelle, `teradatasql`), das die o. g. Tabellen als
   Dateien ablegt (`export/meta/<T>.ddl` + `<T>.csv`/`.ndjson`).
2. Ein passendes **Import-Skript** für das Ziel vorschlagen, das
   a) das Meta-Schema anlegt (falls fehlend), b) die DDL ausführt,
   c) die Daten in obiger Reihenfolge lädt (Batch-Insert), d) Zeilenzahlen
   Quelle↔Ziel gegenprüft.
3. **Hinweis:** Es existiert bereits `backend/app/services/import_service.py`, das
   physische Tabellen aus `DBC.TablesV/ColumnsV` **ins** Meta-Schema importiert —
   das ist ein **anderer** Use-Case (Reverse-Engineering aus dem DWH), NICHT der
   1:1-Transport eines bestehenden Meta-Standes. Für den Server-Umzug ist der
   direkte `META_*`-Datentransport oben der richtige Weg.

**Vor jeder DDL/INSERT-Ausführung auf dem Ziel: Schritt beschreiben und OK abwarten.**

---

## Abnahme-Checkliste

- [ ] venv mit Python ≥3.10 erstellt, alle Pakete offline installiert (kein Netz-Zugriff nötig)
- [ ] `frontend/app.js` nutzt lokales Mermaid, keine `https://`-CDN-Referenzen mehr
- [ ] `cfg/database.yml` gesetzt, Teradata-Verbindung erfolgreich (API antwortet)
- [ ] `frontend/config.js → backend_url` auf erreichbare Ziel-IP
- [ ] Meta-Schema + `META_*`-Tabellen auf dem Ziel vorhanden, Daten importiert, Zeilenzahlen == Quelle
- [ ] Backend `:9021/docs` und Frontend `:8021/` erreichbar
- [ ] Metadaten-Dashboard zeigt Layer/Areas/Tabellen korrekt an
- [ ] LLM-Features entweder lokal erreichbar oder sauber deaktiviert
