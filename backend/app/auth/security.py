"""
Security-Primitive für das Auth-Modul
=====================================

Nur Python-Standardbibliothek:
- Passwort-Hashing:  hashlib.pbkdf2_hmac (PBKDF2-HMAC-SHA256)
- Token:             selbst-signiertes, zustandsloses Token (JWT-ähnlich),
                     signiert mit hmac/SHA-256 über ein geheimes Secret.

Es wird bewusst KEIN PyJWT verwendet, weil das Zielsystem offline ist und
keine zusätzlichen Pip-Pakete installiert werden dürfen.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Rollen-Hierarchie (Index = Rangordnung)
# ---------------------------------------------------------------------------
ROLES = ["Viewer", "Editor", "Admin"]
_ROLE_RANK = {name: idx for idx, name in enumerate(ROLES)}

# PBKDF2-Parameter
_PBKDF2_ALGO = "sha256"
_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16


# ===========================================================================
# Rollen-Hilfsfunktionen
# ===========================================================================
def role_at_least(user_role: Optional[str], required_role: str) -> bool:
    """True, wenn user_role mindestens den Rang von required_role hat."""
    if user_role not in _ROLE_RANK or required_role not in _ROLE_RANK:
        return False
    return _ROLE_RANK[user_role] >= _ROLE_RANK[required_role]


# ===========================================================================
# Passwort-Hashing (PBKDF2-HMAC-SHA256)
# Format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
# ===========================================================================
def hash_password(password: str, iterations: int = _PBKDF2_ITERATIONS) -> str:
    if not password:
        raise ValueError("Passwort darf nicht leer sein")
    salt = os.urandom(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(_PBKDF2_ALGO, password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_{_PBKDF2_ALGO}${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Konstantzeit-Vergleich gegen einen gespeicherten Hash."""
    try:
        algo_part, iter_str, salt_hex, hash_hex = stored_hash.split("$")
        algo = algo_part.replace("pbkdf2_", "")
        iterations = int(iter_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac(algo, password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk, expected)


# ===========================================================================
# Token (zustandslos, selbst-signiert)
# Aufbau:  base64url(payload_json) . base64url(hmac_sha256_signature)
# Payload: { "sub": username, "role": role, "iat": <unix>, "exp": <unix> }
# ===========================================================================
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(message: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()


def create_token(username: str, role: str, secret: str, ttl_seconds: int) -> str:
    now = int(time.time())
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + int(ttl_seconds),
        # jti macht identische Payloads unterscheidbar / erschwert Replays
        "jti": secrets.token_hex(8),
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(payload_b64.encode("ascii"), secret)
    return f"{payload_b64}.{_b64url_encode(signature)}"


def verify_token(token: str, secret: str) -> Tuple[bool, Optional[dict]]:
    """
    Prüft Signatur und Ablaufzeit.
    Rückgabe: (gültig, payload | None)
    """
    if not token or "." not in token:
        return False, None
    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except ValueError:
        return False, None

    expected_sig = _sign(payload_b64.encode("ascii"), secret)
    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception:
        return False, None

    if not hmac.compare_digest(expected_sig, actual_sig):
        return False, None

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        return False, None

    if int(payload.get("exp", 0)) < int(time.time()):
        return False, None

    return True, payload
