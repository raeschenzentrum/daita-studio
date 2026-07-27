#!/usr/bin/env python3
"""
import_meta.py – Importiert einen META-Schema-Export in eine Ziel-Teradata.

Läuft auf dem AIR-GAPPED ZIELSERVER. Liest den mit export_meta.py erzeugten
Ordner (manifest.json + ddl/ + data/) und lädt die gewählten Tabellen in das
Ziel-Schema. Reihenfolge FK-sicher (Eltern vor Kindern).

Tabellen-Auswahl (an der QUELLE oder hier möglich):
  --tables    nur diese importieren (Whitelist)
  --exclude   diese auslassen (Blacklist)

Sicherheit / Vorsicht:
  * Ohne --create-tables werden bestehende Zieltabellen VORAUSGESETZT.
  * --truncate löscht vorhandene Daten der Zieltabelle vor dem Insert.
  * --dry-run zeigt nur, was passieren würde (keine DB-Änderung).

Beispiele
---------
  # Vorschau
  python import_meta.py --in ./meta_export --dry-run

  # Nur ausgewählte Tabellen in bestehendes Schema laden
  python import_meta.py --in ./meta_export --tables META_LAYER,META_AREA,META_TABLE

  # Tabellen anlegen (aus mitgelieferter DDL) und Daten laden, Ziel-Schema abweichend
  python import_meta.py --in ./meta_export --create-tables --schema MDP01_META \
      --host <ziel-td> --user tdops --password ***

  # Alles außer Index-Tabellen, vorher leeren
  python import_meta.py --in ./meta_export --exclude META_INDEX,META_INDEX_COLUMN --truncate
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import _meta_common as mc


def retarget_ddl(ddl: str, source_schema: str, target_schema: str) -> str:
    """Ersetzt den Quell-Schema-Qualifier in der DDL durch das Ziel-Schema."""
    if source_schema.upper() == target_schema.upper():
        return ddl
    pattern = re.compile(re.escape(source_schema) + r"\.", re.IGNORECASE)
    return pattern.sub(target_schema + ".", ddl)


def table_exists(cur, schema: str, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM DBC.TablesV WHERE DatabaseName = ? AND TableName = ?",
        (schema, table),
    )
    return cur.fetchone()[0] > 0


def load_rows(data_file: Path):
    """Liest NDJSON und liefert Listen deserialisierter Werte."""
    with open(data_file, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            values = json.loads(line)
            yield [mc.deserialize_value(v) for v in values]


def import_table(cur, target_schema: str, entry: dict, in_dir: Path, args) -> tuple[int, str]:
    """Importiert eine Tabelle. Rückgabe: (eingefügte_zeilen, status)."""
    table = entry["name"]
    columns = entry["columns"]
    expected = entry["rowcount"]
    data_file = in_dir / "data" / f"{table}.ndjson"

    if not data_file.exists():
        return 0, f"Datendatei fehlt ({data_file.name})"

    # --- Tabelle ggf. anlegen ---
    if args.create_tables and not table_exists(cur, target_schema, table):
        ddl_file = in_dir / "ddl" / f"{table}.sql"
        if not ddl_file.exists():
            return 0, "DDL fehlt, kann Tabelle nicht anlegen"
        ddl = retarget_ddl(
            ddl_file.read_text(encoding="utf-8"),
            args.source_schema,
            target_schema,
        )
        if args.dry_run:
            print(f"    [dry-run] würde Tabelle {target_schema}.{table} anlegen")
        else:
            cur.execute(ddl)

    # --- vorhandene Daten leeren ---
    if args.truncate and not args.dry_run:
        if table_exists(cur, target_schema, table):
            cur.execute(f"DELETE FROM {target_schema}.{table}")

    # --- Insert vorbereiten ---
    collist = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(["?"] * len(columns))
    insert_sql = f'INSERT INTO {target_schema}.{table} ({collist}) VALUES ({placeholders})'

    if args.dry_run:
        return expected, f"[dry-run] {expected:,} Zeilen bereit"

    inserted = 0
    batch: list[list] = []
    for row in load_rows(data_file):
        batch.append(row)
        if len(batch) >= args.batch_size:
            cur.executemany(insert_sql, batch)
            inserted += len(batch)
            batch = []
    if batch:
        cur.executemany(insert_sql, batch)
        inserted += len(batch)

    # --- Verifikation ---
    cur.execute(f"SELECT COUNT(*) FROM {target_schema}.{table}")
    actual = cur.fetchone()[0]
    if actual == expected:
        status = "OK"
    else:
        status = f"WARNUNG Zeilen Ziel={actual} != Quelle={expected}"
    return inserted, status


def main() -> int:
    ap = argparse.ArgumentParser(description="META-Schema-Export in Teradata importieren")
    ap.add_argument("--config", help="Pfad zu database.yml (Default: daita-studio/cfg/database.yml)")
    ap.add_argument("--in", dest="in_dir", required=True, help="Export-Ordner (mit manifest.json)")
    ap.add_argument("--schema", help="Ziel-Schema (Default: source_schema aus Manifest)")
    ap.add_argument("--tables", help="Nur diese Tabellen importieren (kommagetrennt)")
    ap.add_argument("--exclude", help="Diese Tabellen auslassen (kommagetrennt)")
    ap.add_argument("--create-tables", action="store_true", help="Fehlende Tabellen aus DDL anlegen")
    ap.add_argument("--truncate", action="store_true", help="Zieltabelle vor Insert leeren")
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nichts schreiben")
    ap.add_argument("--host")
    ap.add_argument("--user")
    ap.add_argument("--password")
    ap.add_argument("--database")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    manifest = mc.read_manifest(in_dir)
    args.source_schema = manifest["source_schema"]

    cfg = mc.load_db_config(
        args.config,
        {
            "host": args.host,
            "user": args.user,
            "password": args.password,
            "database": args.database,
            "schema": args.schema,
        },
    )
    target_schema = args.schema or cfg["schema"] or args.source_schema
    if not args.dry_run and (not cfg["host"] or not cfg["user"]):
        print("FEHLER: host/user fehlen (weder in database.yml noch als Argument).")
        return 2

    only = mc.parse_list(args.tables)
    exclude = mc.parse_list(args.exclude)

    by_name = {e["name"]: e for e in manifest["tables"]}
    chosen = mc.select_tables(list(by_name.keys()), only, exclude)
    ordered = mc.order_for_import(chosen)

    print(f"Quelle-Schema: {args.source_schema}   Ziel-Schema: {target_schema}")
    print(f"{len(ordered)} von {manifest['table_count']} Tabellen werden importiert"
          f"{' (DRY-RUN)' if args.dry_run else ''}:\n")
    print("  Reihenfolge:", " -> ".join(ordered), "\n")

    if args.dry_run:
        for table in ordered:
            entry = by_name[table]
            print(f"  {table:<24} {entry['rowcount']:>10,} Zeilen")
        print("\n[dry-run] Keine Änderungen vorgenommen.")
        return 0

    results = []
    with mc.connect(cfg) as conn:
        for table in ordered:
            entry = by_name[table]
            with conn.cursor() as cur:
                try:
                    inserted, status = import_table(cur, target_schema, entry, in_dir, args)
                    print(f"  ✓ {table:<24} {inserted:>10,} eingefügt   [{status}]")
                    results.append((table, inserted, status))
                except Exception as exc:  # noqa: BLE001
                    print(f"  ! FEHLER bei {table}: {exc}")
                    results.append((table, 0, f"FEHLER: {exc}"))

    problems = [r for r in results if r[2] != "OK"]
    total = sum(r[1] for r in results)
    print(f"\nFertig: {len(results)} Tabellen, {total:,} Zeilen eingefügt.")
    if problems:
        print("Hinweise/Probleme:")
        for name, _, status in problems:
            print(f"  - {name}: {status}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
