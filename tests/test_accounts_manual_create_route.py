import asyncio
from contextlib import contextmanager

import pytest
from fastapi import HTTPException

import src.web.routes.accounts as accounts_routes
from src.database import crud
from src.database.session import DatabaseSessionManager
from src.web.routes.accounts import AccountCreateRequest


def _build_fake_get_db(manager):
    @contextmanager
    def fake_get_db():
        with manager.session_scope() as session:
            yield session

    return fake_get_db


def test_manual_create_account_persists_password_and_tokens(tmp_path, monkeypatch):
    manager = DatabaseSessionManager(f"sqlite:///{tmp_path}/manual-create.db")
    manager.create_tables()
    manager.migrate_tables()

    monkeypatch.setattr(accounts_routes, "get_db", _build_fake_get_db(manager))

    response = asyncio.run(
        accounts_routes.create_manual_account(
            AccountCreateRequest(
                email="manual@example.com",
                password="secret-pass",
                access_token="access-token",
                refresh_token="refresh-token",
                client_id="client-id",
                account_id="acct-123",
                workspace_id="ws-123",
                cookies="a=b; c=d",
            )
        )
    )

    assert response.email == "manual@example.com"
    assert response.password == "secret-pass"
    assert response.client_id == "client-id"
    assert response.account_id == "acct-123"
    assert response.workspace_id == "ws-123"
    assert response.status == "active"

    with manager.session_scope() as session:
        account = crud.get_account_by_email(session, "manual@example.com")
        assert account is not None
        assert account.email_service == "manual"
        assert account.source == "manual"
        assert account.access_token == "access-token"
        assert account.refresh_token == "refresh-token"
        assert account.token_sync_status == "pending"


def test_manual_create_account_requires_password_token_or_cookies(tmp_path, monkeypatch):
    manager = DatabaseSessionManager(f"sqlite:///{tmp_path}/manual-create-invalid.db")
    manager.create_tables()
    manager.migrate_tables()

    monkeypatch.setattr(accounts_routes, "get_db", _build_fake_get_db(manager))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            accounts_routes.create_manual_account(
                AccountCreateRequest(
                    email="empty@example.com",
                )
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "至少提供密码、任意一种 Token 或 Cookies 之一"


def test_manual_create_account_rejects_duplicate_email(tmp_path, monkeypatch):
    manager = DatabaseSessionManager(f"sqlite:///{tmp_path}/manual-create-duplicate.db")
    manager.create_tables()
    manager.migrate_tables()

    with manager.session_scope() as session:
        crud.create_account(
            session,
            email="dup@example.com",
            email_service="manual",
            password="existing",
            source="manual",
        )

    monkeypatch.setattr(accounts_routes, "get_db", _build_fake_get_db(manager))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            accounts_routes.create_manual_account(
                AccountCreateRequest(
                    email="dup@example.com",
                    password="new-password",
                )
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "账号已存在: dup@example.com"
