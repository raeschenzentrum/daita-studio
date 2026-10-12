"""
Environments API
================

Liefert die auswaehlbaren Metadaten-Umgebungen fuer den Web-UI-Switch
(niemals Host/User/Passwort - nur id+label).
"""
from fastapi import APIRouter, Depends

from ..config import list_environments, get_default_env_id
from ..auth.dependencies import get_current_user

router = APIRouter(prefix="/api/environments", tags=["environments"])


@router.get("")
def get_environments(_user=Depends(get_current_user)):
    """Liste aller Umgebungen + Default-ID (fuer den Fall ohne X-Env-Id-Header)."""
    return {
        "environments": list_environments(),
        "default_id": get_default_env_id(),
    }
