"""
Auth-Service – Benutzerverwaltung gegen Teradata (MDP01_META.META_USER)
=======================================================================

Direkter SQL-Zugriff via teradatasql (kein ORM) – konsistent mit den
übrigen Services in daita-studio.
"""
import logging
from typing import List, Optional

import teradatasql

from ..config import TERADATA_CONFIG, META_SCHEMA
from .models import UserPublic
from .security import hash_password, verify_password

logger = logging.getLogger(__name__)

_TABLE = "META_USER"


class AuthService:
    def __init__(self):
        self.db = TERADATA_CONFIG
        self.schema = META_SCHEMA

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def _get_connection(self):
        conn = teradatasql.connect(
            host=self.db.get("host"),
            user=self.db.get("user"),
            password=self.db.get("password"),
            connect_timeout=self.db.get("connect_timeout", 10000),
        )
        try:
            cur = conn.cursor()
            cur.execute("SET TIME ZONE 'Europe/Berlin'")
        except Exception:
            pass
        return conn

    @property
    def _fq_table(self) -> str:
        return f"{self.schema}.{_TABLE}"

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def ensure_table(self) -> None:
        """Legt META_USER an, falls sie noch nicht existiert (idempotent)."""
        ddl = f"""
        CREATE TABLE {self._fq_table} (
            USER_ID       INTEGER GENERATED ALWAYS AS IDENTITY
                          (START WITH 1 INCREMENT BY 1 MINVALUE 1
                           MAXVALUE 2147483647 NO CYCLE) NOT NULL,
            USERNAME      VARCHAR(128) CHARACTER SET UNICODE NOT CASESPECIFIC NOT NULL,
            PASSWORD_HASH VARCHAR(256) CHARACTER SET LATIN NOT CASESPECIFIC NOT NULL,
            USER_ROLE     VARCHAR(16)  CHARACTER SET LATIN NOT CASESPECIFIC NOT NULL,
            IS_ACTIVE     BYTEINT NOT NULL DEFAULT 1,
            CREATED_AT    TIMESTAMP(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0),
            UPDATED_AT    TIMESTAMP(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0)
        )
        UNIQUE PRIMARY INDEX (USERNAME)
        """
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(ddl)
            conn.commit()
            logger.info("Tabelle %s angelegt", self._fq_table)
        except teradatasql.OperationalError as exc:
            # 3803: Table already exists
            if "3803" in str(exc):
                logger.debug("Tabelle %s existiert bereits", self._fq_table)
            else:
                raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def _row_to_public(self, row) -> UserPublic:
        return UserPublic(
            user_id=int(row[0]),
            username=row[1],
            role=row[2],
            is_active=bool(row[3]),
            created_at=str(row[4]) if row[4] is not None else None,
            updated_at=str(row[5]) if row[5] is not None else None,
        )

    def get_by_username_raw(self, username: str) -> Optional[dict]:
        """Interne Sicht INKL. Passwort-Hash (für Login)."""
        sql = (
            f"SELECT USER_ID, USERNAME, PASSWORD_HASH, USER_ROLE, IS_ACTIVE "
            f"FROM {self._fq_table} WHERE USERNAME = ?"
        )
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, [username])
            row = cur.fetchone()
            if not row:
                return None
            return {
                "user_id": int(row[0]),
                "username": row[1],
                "password_hash": row[2],
                "role": row[3],
                "is_active": bool(row[4]),
            }
        finally:
            conn.close()

    def get_by_username(self, username: str) -> Optional[UserPublic]:
        sql = (
            f"SELECT USER_ID, USERNAME, USER_ROLE, IS_ACTIVE, CREATED_AT, UPDATED_AT "
            f"FROM {self._fq_table} WHERE USERNAME = ?"
        )
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, [username])
            row = cur.fetchone()
            return self._row_to_public(row) if row else None
        finally:
            conn.close()

    def list_users(self) -> List[UserPublic]:
        sql = (
            f"SELECT USER_ID, USERNAME, USER_ROLE, IS_ACTIVE, CREATED_AT, UPDATED_AT "
            f"FROM {self._fq_table} ORDER BY USERNAME"
        )
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql)
            return [self._row_to_public(r) for r in cur.fetchall()]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """Prüft Credentials. Rückgabe: User-dict bei Erfolg, sonst None."""
        user = self.get_by_username_raw(username)
        if not user or not user["is_active"]:
            return None
        if not verify_password(password, user["password_hash"]):
            return None
        return user

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def create_user(self, username: str, password: str, role: str) -> UserPublic:
        sql = (
            f"INSERT INTO {self._fq_table} (USERNAME, PASSWORD_HASH, USER_ROLE) "
            f"VALUES (?, ?, ?)"
        )
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, [username, hash_password(password), role])
            conn.commit()
        finally:
            conn.close()
        created = self.get_by_username(username)
        if created is None:
            raise RuntimeError("Benutzer konnte nach dem Anlegen nicht gelesen werden")
        return created

    def update_user(
        self,
        username: str,
        password: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[UserPublic]:
        sets = []
        params: list = []
        if password is not None:
            sets.append("PASSWORD_HASH = ?")
            params.append(hash_password(password))
        if role is not None:
            sets.append("USER_ROLE = ?")
            params.append(role)
        if is_active is not None:
            sets.append("IS_ACTIVE = ?")
            params.append(1 if is_active else 0)

        if not sets:
            return self.get_by_username(username)

        sets.append("UPDATED_AT = CURRENT_TIMESTAMP(0)")
        sql = f"UPDATE {self._fq_table} SET {', '.join(sets)} WHERE USERNAME = ?"
        params.append(username)

        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
        finally:
            conn.close()
        return self.get_by_username(username)


# Singleton + FastAPI-Dependency-Provider
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
