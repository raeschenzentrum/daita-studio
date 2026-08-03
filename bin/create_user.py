#!/usr/bin/env python3
"""
create_user.py – Benutzer für daita-studio anlegen/ändern/auflisten
===================================================================

Wird benötigt, um den ersten Admin anzulegen (danach geht die Verwaltung
über die Weboberfläche / API).

Beispiele:
    # Tabelle sicherstellen + ersten Admin anlegen (Passwort wird abgefragt)
    python bin/create_user.py create --username admin --role Admin

    # Benutzer auflisten
    python bin/create_user.py list

    # Passwort/Rolle/Status ändern
    python bin/create_user.py update --username maria --role Editor
    python bin/create_user.py update --username maria --deactivate

Das Passwort wird niemals als Argument übergeben, sondern interaktiv
(verdeckt) abgefragt.
"""
import argparse
import getpass
import sys
from pathlib import Path

# backend/ in den Importpfad legen (dort liegt das Package "app")
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

from app.auth.service import get_auth_service  # noqa: E402
from app.auth.security import ROLES  # noqa: E402


def _prompt_password() -> str:
    while True:
        pw1 = getpass.getpass("Passwort (min. 8 Zeichen): ")
        if len(pw1) < 8:
            print("  Zu kurz – mindestens 8 Zeichen.")
            continue
        pw2 = getpass.getpass("Passwort wiederholen: ")
        if pw1 != pw2:
            print("  Passwörter stimmen nicht überein.")
            continue
        return pw1


def cmd_create(args):
    service = get_auth_service()
    service.ensure_table()
    if service.get_by_username(args.username) is not None:
        print(f"❌ Benutzer '{args.username}' existiert bereits.")
        return 1
    password = _prompt_password()
    user = service.create_user(args.username, password, args.role)
    print(f"✅ Benutzer angelegt: {user.username} (Rolle: {user.role})")
    return 0


def cmd_list(args):
    service = get_auth_service()
    service.ensure_table()
    users = service.list_users()
    if not users:
        print("(keine Benutzer)")
        return 0
    print(f"{'USER':<24} {'ROLLE':<8} {'AKTIV':<6} ANGELEGT")
    print("-" * 60)
    for u in users:
        print(f"{u.username:<24} {u.role:<8} {'ja' if u.is_active else 'nein':<6} {u.created_at or ''}")
    return 0


def cmd_update(args):
    service = get_auth_service()
    service.ensure_table()
    if service.get_by_username(args.username) is None:
        print(f"❌ Benutzer '{args.username}' nicht gefunden.")
        return 1
    password = None
    if args.set_password:
        password = _prompt_password()
    is_active = None
    if args.activate:
        is_active = True
    elif args.deactivate:
        is_active = False
    updated = service.update_user(
        args.username, password=password, role=args.role, is_active=is_active
    )
    print(f"✅ Benutzer aktualisiert: {updated.username} "
          f"(Rolle: {updated.role}, aktiv: {'ja' if updated.is_active else 'nein'})")
    return 0


def main():
    parser = argparse.ArgumentParser(description="daita-studio Benutzerverwaltung")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Benutzer anlegen")
    p_create.add_argument("--username", required=True)
    p_create.add_argument("--role", required=True, choices=ROLES)
    p_create.set_defaults(func=cmd_create)

    p_list = sub.add_parser("list", help="Benutzer auflisten")
    p_list.set_defaults(func=cmd_list)

    p_update = sub.add_parser("update", help="Benutzer ändern")
    p_update.add_argument("--username", required=True)
    p_update.add_argument("--role", choices=ROLES, default=None)
    p_update.add_argument("--set-password", action="store_true",
                          help="Neues Passwort interaktiv setzen")
    p_update.add_argument("--activate", action="store_true", help="Benutzer aktivieren")
    p_update.add_argument("--deactivate", action="store_true", help="Benutzer sperren")
    p_update.set_defaults(func=cmd_update)

    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Fehler: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
