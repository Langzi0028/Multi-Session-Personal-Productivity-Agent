import pytest

from app.contracts import UserPublic
from app.runtime.auth_manager import AuthManager, AuthValidationError, DuplicateUsernameError
from app.storage.sqlite_store import SQLiteStore


def build_auth_manager() -> AuthManager:
    store = SQLiteStore(":memory:")
    store.init_schema()
    return AuthManager(store)


def test_register_user_stores_hashed_password_not_plaintext():
    manager = build_auth_manager()

    user = manager.register_user("Alice", "password123")

    assert isinstance(user, UserPublic)
    assert user.username == "alice"
    row = manager.store.query_one("SELECT * FROM users WHERE user_id = ?", (user.user_id,))
    assert row is not None
    assert row["password_hash"] != "password123"
    assert row["password_salt"]


def test_authenticate_user_accepts_correct_password_and_rejects_wrong_password():
    manager = build_auth_manager()
    user = manager.register_user("alice", "password123")

    assert manager.authenticate_user("ALICE", "password123") == user
    assert manager.authenticate_user("alice", "wrong-password") is None


def test_duplicate_username_is_rejected():
    manager = build_auth_manager()
    manager.register_user("alice", "password123")

    with pytest.raises(DuplicateUsernameError):
        manager.register_user(" Alice ", "different123")


def test_invalid_username_or_password_is_rejected():
    manager = build_auth_manager()

    with pytest.raises(AuthValidationError):
        manager.register_user("ab", "password123")
    with pytest.raises(AuthValidationError):
        manager.register_user("alice", "short")


def test_issued_token_resolves_user_until_revoked():
    manager = build_auth_manager()
    user = manager.register_user("alice", "password123")

    token = manager.issue_token(user.user_id)

    assert token
    assert manager.get_user_for_token(token) == user
    manager.revoke_token(token)
    assert manager.get_user_for_token(token) is None
