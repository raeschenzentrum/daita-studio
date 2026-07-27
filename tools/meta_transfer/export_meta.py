#!/usr/bin/env python3
"""
export_meta.py – Exportiert das komplette META-Schema aus Teradata in Files.

Läuft an der QUELLE (Rechner mit Zugriff auf die Quell-Teradata). Erzeugt einen
transportierbaren Ordner mit:

    <out>/
      manifest.json            # Schema, Tabellenliste, Spalten, Zeilenzahlen
      ddl/<TABLE>.sql          # SHOW TABLE Ausgabe je Tabelle
      data/<TABLE>.ndjson      # eine JSON-Zeile (Werte-Array) pro Datensatz

Die Tabellen werden DYNAMISCH aus dem Data Dictionary entdeckt (DBC.TablesV),
d.h. das komplette Schema wird erfasst – nicht nur eine fest verdrahtete Liste.

Beispiele
---------
  # Alles aus dem in cfg/database.yml konfigurierten Meta-Schema exportieren
  python export_meta.py --out ./meta_export

  # Nur bestimmte Tabellen
  python export_meta.py --out ./meta_export --tables META_LAYER,META_AREA,META_TABLE

  # Alles außer großen/ungewollten Tabellen
  python export_meta.py --out ./meta_export --exclude META_INDEX,META_INDEX_COLUMN

  # Anderes Schema / andere Verbindung ohne database.yml
  python export_meta.py --out ./meta_export --schema MDP01_META \
      --host 192.168.114.21 --user tdops --password ***
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _meta_common as mc


def discover_tables(cur, schema: str) -> list[str]:
    """Alle Tabellen (inkl. NoPI) des Schemas aus dem Data Dictionary."""
    cur.execute(
        "SELECT TRIM(TableName) FROM DBC.TablesV "
        "WHERE DatabaseName = ? AND TableKind IN ('T','O') "
        "ORDER BY TableName",
        (schema,),
    )
    return [row[0] for row in cur.fetchall()]


def export_table(cur, schema: str, table: str, ddl_dir: Path, data_dir: Path) -> dict:
    """Exportiert DDL + Daten einer Tabelle. Gibt Manifest-Eintrag zurück."""
    # --- DDL ---
    try:
        cur.execute(f"SHOW TABLE {schema}.{table}")
        ddl = "".join(str(r[0]) for r in cur.fetchall())
        (ddl_dir / f"{table}.sql").write_text(ddl, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"  ! DDL für {table} nicht exportierbar: {exc}")

    # --- Daten ---
    cur.execute(f"SELECT * FROM {schema}.{table}")
    columns = [d[0] for d in cur.description]

    rowcount = 0
    with open(data_dir / f"{table}.ndjson", "w", encoding="utf-8") as fh:
        while True:
            batch = cur.fetchmany(5000)
            if not batch:
                break
            for row in batch:
                values = [mc.serialize_value(v) for v in row]
                fh.write(json.dumps(values, ensure_ascii=False))
                fh.write("\n")
                rowcount += 1

    print(f"  ✓ {table:<24} {rowcount:>10,} Zeilen, {len(columns)} Spalten")
    return {"name": table, "columns": columns, "rowcount": rowcount}


def main() -> int:
    ap = argparse.ArgumentParser(description="META-Schema aus Teradata exportieren")
    ap.add_argument("--config", help="Pfad zu database.yml (Default: daita-studio/cfg/database.yml)")
    ap.add_argument("--out", required=True, help="Zielordner für den Export")
    ap.add_argument("--schema", help="Meta-Schema (überschreibt database.yml)")
    ap.add_argument("--tables", help="Nur diese Tabellen (kommagetrennt)")
    ap.add_argument("--exclude", help="Diese Tabellen ausschließen (kommagetrennt)")
    ap.add_argument("--host")
    ap.add_argument("--user")
    ap.add_argument("--password")
    ap.add_argument("--database")
    args = ap.parse_args()

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
    schema = cfg["schema"]
    if not cfg["host"] or not cfg["user"]:
        print("FEHLER: host/user fehlen (weder in database.yml noch als Argument).")
        return 2

    out_dir = Path(args.out)
    ddl_dir = out_dir / "ddl"
    data_dir = out_dir / "data"
    for d in (ddl_dir, data_dir):
        d.mkdir(parents=True, exist_ok=True)

    only = mc.parse_list(args.tables)
    exclude = mc.parse_list(args.exclude)

    print(f"Verbinde mit {cfg['host']} … Schema: {schema}")
    with mc.connect(cfg) as conn:
        with conn.cursor() as cur:
            all_tables = discover_tables(cur, schema)
            if not all_tables:
                print(f"FEHLER: Keine Tabellen in {schema} gefunden.")
                return 1
            tables = mc.select_tables(all_tables, only, exclude)
            print(f"{len(tables)} von {len(all_tables)} Tabellen werden exportiert.\n")

            entries = []
            for table in tables:
                try:
                    entries.append(export_table(cur, schema, table, ddl_dir, data_dir))
                except Exception as exc:  # noqa: BLE001
                    print(f"  ! FEHLER bei {table}: {exc}")

    manifest = {
        "source_schema": schema,
        "exported_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "table_count": len(entries),
        "tables": entries,
    }
    mc.write_manifest(out_dir, manifest)

    total = sum(e["rowcount"] for e in entries)
    print(f"\nFertig: {len(entries)} Tabellen, {total:,} Zeilen -> {out_dir}")
    print("Manifest:", out_dir / "manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
