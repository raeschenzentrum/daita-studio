# daita-modeler – Copilot Instructions

> Workflow-Gates (erst fragen / auf OK warten) sind global in User Memory definiert.
> Diese Datei enthält nur **projektspezifische** Regeln.

---

## Was ist daita-modeler?

**Visuelles ERD-Tool** für Teradata-DWH-Projekte.
Liest Metadaten aus konfigurierbarem META-Schema, stellt Tabellen und logische
Beziehungen als interaktives Diagramm dar.

| Komponente | Detail |
|------------|--------|
| Backend | FastAPI, Port **8003** |
| Frontend | Vanilla JS + **JointJS** (ERD-Canvas) |
| Venv | `/mnt/user/venv/daita-lakehouse` |
| Meta-Schema | `MDP01_META` (konfigurierbar in `cfg/modeler.yml`) |

---

## Architektur

```
Frontend (HTML/JS, Port 8003)
    │
    │ REST API
    ▼
Backend (FastAPI, Port 8003)
    │
    │ SQL
    ▼
Teradata
  ├── MDP01_META.*            ← Metadaten (konfigurierbar)
  └── DBC.TablesV / ColumnsV  ← Import-Quelle
```

### Strikte Trennung

| Layer | Verantwortung |
|-------|---------------|
| **Backend** | ALLE Logik, Validierung, Business Rules, REST API |
| **Frontend** | NUR GUI, keine Logik, ruft nur Backend-APIs auf |

---

## Teradata Regeln

**❌ GIBT ES NICHT:**
- `TOP n` → stattdessen `SAMPLE n` am Ende der Query
- `DROP TABLE IF EXISTS` → Try/Except verwenden

**✅ IMMER:**
- Nach DDL: `conn.commit()` (sonst Error 3722)
- Spalten in DDLs: GROSSBUCHSTABEN

---

## Konfiguration

| Datei | Inhalt |
|-------|--------|
| `cfg/database.yml` | Teradata-Verbindung (nicht in Git!) |
| `cfg/modeler.yml` | Meta-Schema, Tabellennamen, Diagram-Storage |

**Pfad-Handling:**
```python
# ✅ RICHTIG – zentral in config.py
from app.config import META_SCHEMA, DIAGRAM_PATH

# ❌ FALSCH
Path(__file__).parent.parent / "diagrams"
```

---

## Frontend – JointJS

- ERD-Canvas basiert auf **JointJS 3.x** (MIT-Lizenz)
- Liegt unter `frontend/vendor/jointjs.min.js` (einmalig per curl geladen)
- **Kein npm, kein Build-Schritt** – reines Vanilla JS
- Alle JS-Dateien werden vom FastAPI-Static-Files-Handler serviert

---

## Task-Management

- Neue Anforderungen → `BACKLOG.md` unter offenem Milestone eintragen
- Milestones: DM0 (Gerüst) → DM1 (Meta lesen) → DM2 (Canvas) → DM3 (FK) → DM4 (Import) → DM5 (Areas) → DM6 (Layout/Export)
- Aktueller Status immer in `BACKLOG.md` nachführen
