"""
Pydantic-Modelle für das Auth-Modul
"""
from typing import Optional
from pydantic import BaseModel, Field

from .security import ROLES


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    username: str
    role: str


class UserPublic(BaseModel):
    """Öffentliche Sicht auf einen Benutzer (ohne Passwort-Hash)."""
    user_id: int
    username: str
    role: str
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=8)
    role: str = Field(..., pattern="^(Viewer|Editor|Admin)$")


class UpdateUserRequest(BaseModel):
    """Alle Felder optional – nur gesetzte Werte werden geändert."""
    password: Optional[str] = Field(default=None, min_length=8)
    role: Optional[str] = Field(default=None, pattern="^(Viewer|Editor|Admin)$")
    is_active: Optional[bool] = None
