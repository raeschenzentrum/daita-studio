"""
FastAPI-Dependencies für RBAC
=============================

- get_current_user  : validiert das Bearer-Token, liefert den Payload
- require_role(name): Factory für rollenbasierte Endpunkt-Absicherung
- rbac_guard        : methoden-basierter Standard-Schutz für bestehende Router
                      (GET/HEAD → Viewer, POST/PUT/PATCH → Editor, DELETE → Admin)
"""
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import TOKEN_SECRET, AUTH_MODULE_PERMS, AUTH_DEFAULT_PERM
from .security import role_at_least, verify_token

logger = logging.getLogger(__name__)

# auto_error=False → wir liefern eigene, einheitliche 401-Fehler
_bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, username: str, role: str):
        self.username = username
        self.role = role


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nicht angemeldet",
            headers={"WWW-Authenticate": "Bearer"},
        )
    valid, payload = verify_token(credentials.credentials, TOKEN_SECRET)
    if not valid or payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token ungültig oder abgelaufen",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return CurrentUser(username=payload.get("sub", ""), role=payload.get("role", ""))


def require_role(required_role: str):
    """Factory: erzwingt mindestens die angegebene Rolle."""

    def _dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not role_at_least(user.role, required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rolle '{required_role}' erforderlich (vorhanden: '{user.role}')",
            )
        return user

    return _dependency


# Methode → benötigte Mindestrolle
_METHOD_ROLE = {
    "GET": "Viewer",
    "HEAD": "Viewer",
    "POST": "Editor",
    "PUT": "Editor",
    "PATCH": "Editor",
    "DELETE": "Admin",
}


def rbac_guard(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """
    Standard-Schutz für alle bestehenden Router.
    Leitet die Mindestrolle aus der HTTP-Methode ab.
    (OPTIONS-Preflight wird von der CORS-Middleware behandelt und erreicht
    diese Dependency nicht.)
    """
    required = _METHOD_ROLE.get(request.method, "Admin")
    if not role_at_least(user.role, required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Rolle '{required}' erforderlich (vorhanden: '{user.role}')",
        )
    return user


# ---------------------------------------------------------------------------
# Modul-spezifischer Guard – nutzt die Rechte-Matrix aus cfg/config.yml
# HTTP-Methode -> Aktion, Aktion + Modul -> benötigte Mindestrolle.
# ---------------------------------------------------------------------------
_METHOD_ACTION = {
    "GET": "view",
    "HEAD": "view",
    "POST": "edit",
    "PUT": "edit",
    "PATCH": "edit",
    "DELETE": "delete",
}


def required_role_for(module: str, action: str) -> str:
    """Mindestrolle für (Modul, Aktion): Modul-Eintrag > default > Fallback."""
    module_perms = AUTH_MODULE_PERMS.get(module, {}) or {}
    return module_perms.get(action) or AUTH_DEFAULT_PERM.get(action) or "Admin"


def module_guard(module: str):
    """
    Factory: erzeugt einen Router-Guard für ein bestimmtes Modul.
    Die konkrete Mindestrolle je Aktion kommt aus der Matrix in cfg/config.yml
    (auth.modules) – dadurch pro Modul einstellbar, ohne Code-Änderung.
    """

    def _dependency(
        request: Request,
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        action = _METHOD_ACTION.get(request.method, "delete")
        required = required_role_for(module, action)
        if not role_at_least(user.role, required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Modul '{module}': Aktion '{action}' erfordert Rolle "
                    f"'{required}' (vorhanden: '{user.role}')"
                ),
            )
        return user

    return _dependency
