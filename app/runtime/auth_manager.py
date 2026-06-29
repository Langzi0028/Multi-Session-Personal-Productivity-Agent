from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from app.contracts import UserPublic, utc_now_iso
from app.storage.sqlite_store import SQLiteStore


class AuthValidationError(ValueError):
    pass


class DuplicateUsernameError(ValueError):
    pass


class AuthManager:
    TOKEN_TTL_DAYS = 7
    PASSWORD_ITERATIONS = 200_000
    _USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def register_user(self, username: str, password: str) -> UserPublic:
        normalized = self._normalize_username(username)
        self._validate_password(password)
        existing = self.store.query_one("SELECT user_id FROM users WHERE username = ?", (normalized,))
        if existing is not None:
            raise DuplicateUsernameError(f"Username already exists: {normalized}")
        salt = secrets.token_bytes(16)
        now = utc_now_iso()
        user = UserPublic(user_id=f"user_{uuid.uuid4().hex[:16]}", username=normalized)
        self.store.execute(
            """
            INSERT INTO users (user_id, username, password_hash, password_salt, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user.user_id, user.username, self._hash_password(password, salt), salt.hex(), now, now),
        )
        return user

    def authenticate_user(self, username: str, password: str) -> UserPublic | None:
        try:
            normalized = self._normalize_username(username)
        except AuthValidationError:
            return None
        row = self.store.query_one("SELECT * FROM users WHERE username = ?", (normalized,))
        if row is None:
            return None
        expected_hash = row["password_hash"]
        salt = bytes.fromhex(row["password_salt"])
        candidate_hash = self._hash_password(password, salt)
        if not hmac.compare_digest(candidate_hash, expected_hash):
            return None
        return UserPublic(user_id=row["user_id"], username=row["username"])

    def issue_token(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = utc_now_iso()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=self.TOKEN_TTL_DAYS)).replace(microsecond=0).isoformat()
        self.store.execute(
            """
            INSERT INTO auth_tokens (token_hash, user_id, created_at, expires_at, revoked_at)
            VALUES (?, ?, ?, ?, NULL)
            """,
            (self._hash_token(token), user_id, now, expires_at),
        )
        return token

    def get_user_for_token(self, token: str) -> UserPublic | None:
        if not token:
            return None
        row = self.store.query_one(
            """
            SELECT users.user_id, users.username, auth_tokens.expires_at, auth_tokens.revoked_at
            FROM auth_tokens
            JOIN users ON users.user_id = auth_tokens.user_id
            WHERE auth_tokens.token_hash = ?
            """,
            (self._hash_token(token),),
        )
        if row is None or row["revoked_at"] is not None:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at < datetime.now(timezone.utc):
            return None
        return UserPublic(user_id=row["user_id"], username=row["username"])

    def revoke_token(self, token: str) -> None:
        if not token:
            return
        self.store.execute(
            "UPDATE auth_tokens SET revoked_at = ? WHERE token_hash = ?",
            (utc_now_iso(), self._hash_token(token)),
        )

    def _normalize_username(self, username: str) -> str:
        normalized = username.strip().lower()
        if not self._USERNAME_RE.match(normalized):
            raise AuthValidationError("用户名只能包含 3-32 位小写字母、数字、下划线、点或短横线")
        return normalized

    def _validate_password(self, password: str) -> None:
        if len(password) < 8 or len(password) > 128:
            raise AuthValidationError("密码长度必须为 8-128 位")

    def _hash_password(self, password: str, salt: bytes) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self.PASSWORD_ITERATIONS,
        ).hex()

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
