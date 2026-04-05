from datetime import datetime, timedelta
from contextlib import contextmanager

from src.database import crud
from src.database.session import DatabaseSessionManager
from src.core.openai import token_refresh
from src.core.openai.token_refresh import TokenRefreshResult


def _build_fake_get_db(manager):
    @contextmanager
    def fake_get_db():
        with manager.session_scope() as session:
            yield session

    return fake_get_db


def test_validate_account_uses_existing_access_token_without_refresh(tmp_path, monkeypatch):
    manager = DatabaseSessionManager(f"sqlite:///{tmp_path}/validate-existing.db")
    manager.create_tables()
    manager.migrate_tables()

    with manager.session_scope() as session:
        account = crud.create_account(
            session,
            email="access@example.com",
            email_service="manual",
            access_token="existing-access",
        )
        account_id = account.id

    monkeypatch.setattr(token_refresh, "get_db", _build_fake_get_db(manager))

    validate_calls = []

    def fake_validate(self, access_token):
        validate_calls.append(access_token)
        return True, None

    def fake_refresh(self, account):
        raise AssertionError("refresh should not be called when access_token is valid")

    monkeypatch.setattr(token_refresh.TokenRefreshManager, "validate_token", fake_validate)
    monkeypatch.setattr(token_refresh.TokenRefreshManager, "refresh_account", fake_refresh)

    is_valid, error = token_refresh.validate_account_token(account_id)

    assert is_valid is True
    assert error is None
    assert validate_calls == ["existing-access"]


def test_validate_account_refreshes_when_access_token_missing(tmp_path, monkeypatch):
    manager = DatabaseSessionManager(f"sqlite:///{tmp_path}/validate-refresh.db")
    manager.create_tables()
    manager.migrate_tables()

    with manager.session_scope() as session:
        account = crud.create_account(
            session,
            email="refresh@example.com",
            email_service="manual",
            refresh_token="refresh-token",
            client_id="client-id",
        )
        account_id = account.id

    monkeypatch.setattr(token_refresh, "get_db", _build_fake_get_db(manager))

    def fake_refresh(self, account):
        assert account.email == "refresh@example.com"
        return TokenRefreshResult(
            success=True,
            access_token="new-access",
            refresh_token="new-refresh",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )

    validate_calls = []

    def fake_validate(self, access_token):
        validate_calls.append(access_token)
        return True, None

    monkeypatch.setattr(token_refresh.TokenRefreshManager, "refresh_account", fake_refresh)
    monkeypatch.setattr(token_refresh.TokenRefreshManager, "validate_token", fake_validate)

    is_valid, error = token_refresh.validate_account_token(account_id)

    assert is_valid is True
    assert error is None
    assert validate_calls == ["new-access"]

    with manager.session_scope() as session:
        reloaded = crud.get_account_by_id(session, account_id)
        assert reloaded is not None
        assert reloaded.access_token == "new-access"
        assert reloaded.refresh_token == "new-refresh"
        assert reloaded.last_refresh is not None
        assert reloaded.expires_at is not None


def test_validate_account_reports_missing_tokens_for_password_only_import(tmp_path, monkeypatch):
    manager = DatabaseSessionManager(f"sqlite:///{tmp_path}/validate-password-only.db")
    manager.create_tables()
    manager.migrate_tables()

    with manager.session_scope() as session:
        account = crud.create_account(
            session,
            email="password-only@example.com",
            email_service="manual",
            password="secret-pass",
            source="manual",
        )
        account_id = account.id

    monkeypatch.setattr(token_refresh, "get_db", _build_fake_get_db(manager))

    is_valid, error = token_refresh.validate_account_token(account_id)

    assert is_valid is False
    assert error == "账号没有可验证的 access_token，且缺少 session_token / refresh_token"
