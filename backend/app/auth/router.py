"""
Auth-Router – Login und Benutzerverwaltung
==========================================

Öffentlich:
    POST /api/auth/login        → Token anfordern

Angemeldet (jede Rolle):
    GET  /api/auth/me           → eigener Benutzer

Nur Admin:
    GET  /api/auth/users        → Benutzer auflisten
    POST /api/auth/users        → Benutzer anlegen
    PUT  /api/auth/users/{name} → Benutzer ändern (Passwort/Rolle/aktiv)
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import TOKEN_TTL_HOURS, TOKEN_SECRET
from .dependencies import CurrentUser, get_current_user, require_role
from .models import (
    CreateUserRequest,
    LoginRequest,
    TokenResponse,
    UpdateUserRequest,
    UserPublic,
)
from .security import create_token
from .service import AuthService, get_auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    service: AuthService = Depends(get_auth_service),
):
    user = service.authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Benutzername oder Passwort falsch",
        )
    ttl_seconds = int(TOKEN_TTL_HOURS) * 3600
    token = create_token(user["username"], user["role"], TOKEN_SECRET, ttl_seconds)
    return TokenResponse(
        access_token=token,
        expires_in=ttl_seconds,
        username=user["username"],
        role=user["role"],
    )


@router.get("/me", response_model=dict)
async def me(current: CurrentUser = Depends(get_current_user)):
    return {"username": current.username, "role": current.role}


@router.get("/users", response_model=List[UserPublic])
async def list_users(
    _: CurrentUser = Depends(require_role("Admin")),
    service: AuthService = Depends(get_auth_service),
):
    return service.list_users()


@router.post("/users", response_model=UserPublic, status_code=201)
async def create_user(
    body: CreateUserRequest,
    _: CurrentUser = Depends(require_role("Admin")),
    service: AuthService = Depends(get_auth_service),
):
    if service.get_by_username(body.username) is not None:
        raise HTTPException(status_code=409, detail="Benutzername existiert bereits")
    return service.create_user(body.username, body.password, body.role)


@router.put("/users/{username}", response_model=UserPublic)
async def update_user(
    username: str,
    body: UpdateUserRequest,
    _: CurrentUser = Depends(require_role("Admin")),
    service: AuthService = Depends(get_auth_service),
):
    if service.get_by_username(username) is None:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    updated = service.update_user(
        username,
        password=body.password,
        role=body.role,
        is_active=body.is_active,
    )
    return updated
