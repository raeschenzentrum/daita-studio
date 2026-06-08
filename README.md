# daita-studio

**Modeler • ETL Orchestrator • Metadata Platform** für Teradata DWH-Projekte.

Zusammenführung von `metadaita` (ETL, Lineage, Jobs) und `daita-modeler` (ERD-Canvas, Reverse Engineering).

## Services

| Service | Port |
|---------|------|
| Backend (FastAPI) | 8015 |
| Frontend (HTTP) | 9015 |

## Start

```bash
./bin/start.sh start|stop|restart|status
```

## Konfiguration

- `cfg/database.yml` – Teradata Credentials
- `cfg/config.yml` – Pfade und Ports
- `cfg/parameter_rules.yml` – ETL-Parameter-Generierungsregeln
