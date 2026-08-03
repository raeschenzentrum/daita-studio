"""
Auth-Modul für daita-studio
============================

RBAC (Role-Based Access Control) mit drei festen Rollen:
- Viewer : lesender Zugriff (GET/HEAD)
- Editor : Viewer + schreibend (POST/PUT/PATCH)
- Admin  : Editor + löschend (DELETE) + Benutzerverwaltung

Bewusst OHNE externe Abhängigkeiten (kein PyJWT/passlib) – nur Python-Stdlib,
da das Zielsystem offline ist und keine zusätzlichen Pakete erlaubt sind.
"""

from .security import (
    hash_password,
    verify_password,
    create_token,
    verify_token,
    ROLES,
    role_at_least,
)

__all__ = [
    "hash_password",
    "verify_password",
    "create_token",
    "verify_token",
    "ROLES",
    "role_at_least",
]
