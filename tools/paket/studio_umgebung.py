"""
Konfiguration der daita-studio-Installation lesen, so wie das Backend sie
auflöst (backend/app/config.py): install_root, paths.*, Umgebungen aus
cfg/environments.yml (ohne Datei: Umgebung "default" aus cfg/database.yml).

Bewusst ohne Import von app.config, damit Export und Einspieler ohne
laufendes Backend arbeiten. Python 3.6 kompatibel.
"""
from pathlib import Path

import yaml

STUDIO_ROOT = Path(__file__).resolve().parents[2]


def _yaml(pfad):
    if pfad.exists():
        with open(str(pfad), encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class Studio:
    def __init__(self, root=STUDIO_ROOT):
        self.root = Path(root).resolve()
        cfg_dir = self.root / "cfg"
        config = _yaml(cfg_dir / "config.yml")
        database = _yaml(cfg_dir / "database.yml")
        envs = _yaml(cfg_dir / "environments.yml").get("environments") or []
        self.install_root = Path(config.get("install_root") or str(self.root))
        self.paths = config.get("paths") or {}
        self.umgebungen = {e["id"]: e for e in envs if e.get("id")}
        self.quelle_umgebungen = "cfg/environments.yml"
        if not self.umgebungen:
            td = database.get("teradata") or {}
            self.umgebungen = {"default": {
                "id": "default", "host": td.get("host", ""), "user": td.get("user", ""),
                "password": td.get("password", ""),
                "schema": (database.get("metadata") or {}).get("schema", "MDP01_META"),
            }}
            self.quelle_umgebungen = "cfg/database.yml (keine cfg/environments.yml)"

    def pfad(self, schluessel, standard):
        p = Path(self.paths.get(schluessel, standard))
        return p if p.is_absolute() else self.install_root / p

    def umgebung(self, env_id):
        return self.umgebungen.get(env_id)

    def etl_jobs(self, env_id):
        return self.pfad("etl_jobs", "etl/jobs") / env_id

    def sql_templates(self):
        return self.pfad("sql_templates", "ddl/sql_templates")

    def dashboards(self, env_id):
        p = (self.umgebung(env_id) or {}).get("dashboards")
        if not p:
            return self.pfad("dashboards", "cfg/dashboards_beispiel")
        p = Path(p)
        return p if p.is_absolute() else self.install_root / p

    def zugang(self, env_id, eigener=None):
        """(host, user, password) der Umgebung; mit eigener (z. B. "einspielen_db"
        oder "dashboards_db") dessen User, falls in der Umgebung eingetragen."""
        e = self.umgebung(env_id)
        if not e:
            raise KeyError("Umgebung {} fehlt in {}".format(env_id, self.quelle_umgebungen))
        z = (e.get(eigener) or {}) if eigener else {}
        if z.get("user") and z.get("password"):
            return z.get("host") or e["host"], z["user"], z["password"]
        return e["host"], e["user"], e["password"]

    def verbinden(self, env_id, eigener=None):
        import teradatasql
        host, user, password = self.zugang(env_id, eigener)
        return teradatasql.connect(host=host, user=user, password=password)
