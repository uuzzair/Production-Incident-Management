from dataclasses import replace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.responses import RedirectResponse
from authlib.integrations.base_client.errors import OAuthError

from app.api.routes import auth as auth_routes
from app.services import oidc as oidc_service
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import Incident, IncidentUpdate, Reporter, User, UserSession  # noqa: F401
from app.services.sessions import create_session, get_valid_session, hash_csrf_token, hash_session_token, utc_now


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_get_db_session():
        async with SessionLocal() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    await engine.dispose()


def oidc_test_settings() -> Settings:
    return replace(
        get_settings(),
        oidc_issuer_url="https://idp.example",
        oidc_client_id="client-id",
        oidc_client_secret="client-secret",
        oidc_redirect_uri="http://testserver/api/v1/auth/callback",
        auth_success_redirect_url="http://localhost:5173",
        secure_cookies=False,
    )


PRODUCTION_CONFIG_ENV = {
    "ENVIRONMENT": "staging",
    "DATABASE_URL": "postgresql+asyncpg://user:pass@db.example.com/incidents",
    "API_KEYS": "service-token:admin",
    "CORS_ALLOWED_ORIGINS": "https://incidents.example.com",
    "CORS_ALLOW_CREDENTIALS": "true",
    "OIDC_ISSUER_URL": "https://idp.example.com",
    "OIDC_CLIENT_ID": "client-id",
    "OIDC_CLIENT_SECRET": "client-secret",
    "OIDC_REDIRECT_URI": "https://api.example.com/api/v1/auth/callback",
    "AUTH_SUCCESS_REDIRECT_URL": "https://incidents.example.com",
    "SESSION_SECRET_KEY": "x" * 32,
    "SECURE_COOKIES": "true",
}


CONFIG_ENV_KEYS = {
    *PRODUCTION_CONFIG_ENV.keys(),
    "SESSION_COOKIE_SECRET",
    "CORS_ALLOWED_ORIGIN_REGEX",
}


def clear_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def set_production_config(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    clear_config_env(monkeypatch)
    values = {**PRODUCTION_CONFIG_ENV, **overrides}
    for key, value in values.items():
        monkeypatch.setenv(key, value)


class FakeOidcClient:
    def __init__(
        self,
        claims: dict[str, str] | None = None,
        *,
        callback_error: bool = False,
        id_token_error: bool = False,
        include_id_token: bool = True,
    ):
        self.claims = claims or {}
        self.callback_error = callback_error
        self.id_token_error = id_token_error
        self.include_id_token = include_id_token

    async def authorize_redirect(self, request, redirect_uri: str, nonce: str):
        assert redirect_uri == "http://testserver/api/v1/auth/callback"
        assert nonce
        return RedirectResponse("https://idp.example/authorize?state=fake-state")

    async def authorize_access_token(self, request):
        if self.callback_error:
            raise OAuthError(error="invalid_state", description="Invalid state")
        token = {"userinfo": self.claims}
        if self.include_id_token:
            token["id_token"] = "fake-id-token"
        return token

    async def parse_id_token(self, request, token):
        if self.id_token_error:
            raise OAuthError(error="invalid_token", description="Invalid ID token")
        return self.claims


@pytest.mark.asyncio
async def test_write_endpoints_require_api_key(client: AsyncClient):
    response = await client.post("/api/v1/reporters/", json={"name": "Ada"})

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "http_error"
    assert body["error"]["message"] == "Missing API key"


@pytest.mark.asyncio
async def test_invalid_api_key_fails(client: AsyncClient):
    response = await client.post(
        "/api/v1/reporters/",
        headers={"Authorization": "Bearer invalid-token"},
        json={"name": "Ada"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid API key"


def test_production_requires_oidc_and_session_settings(monkeypatch: pytest.MonkeyPatch):
    clear_config_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@db.example.com/incidents")
    monkeypatch.setenv("API_KEYS", "service-token:admin")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://incidents.example.com")

    with pytest.raises(ValueError, match="Production auth settings missing"):
        Settings.from_env()


def test_production_rejects_localhost_redirect_urls(monkeypatch: pytest.MonkeyPatch):
    set_production_config(
        monkeypatch,
        OIDC_REDIRECT_URI="https://localhost/api/v1/auth/callback",
    )

    with pytest.raises(ValueError, match="OIDC_REDIRECT_URI"):
        Settings.from_env()

    set_production_config(
        monkeypatch,
        AUTH_SUCCESS_REDIRECT_URL="http://localhost:5173",
    )

    with pytest.raises(ValueError, match="AUTH_SUCCESS_REDIRECT_URL"):
        Settings.from_env()


def test_production_rejects_non_https_redirect_urls(monkeypatch: pytest.MonkeyPatch):
    set_production_config(
        monkeypatch,
        OIDC_REDIRECT_URI="http://api.example.com/api/v1/auth/callback",
    )

    with pytest.raises(ValueError, match="OIDC_REDIRECT_URI"):
        Settings.from_env()

    set_production_config(
        monkeypatch,
        AUTH_SUCCESS_REDIRECT_URL="http://incidents.example.com",
    )

    with pytest.raises(ValueError, match="AUTH_SUCCESS_REDIRECT_URL"):
        Settings.from_env()


def test_production_rejects_wildcard_cors_with_credentials(monkeypatch: pytest.MonkeyPatch):
    set_production_config(
        monkeypatch,
        CORS_ALLOWED_ORIGINS="*",
        CORS_ALLOW_CREDENTIALS="true",
    )

    with pytest.raises(ValueError, match="wildcard"):
        Settings.from_env()


def test_production_rejects_weak_default_session_secret(monkeypatch: pytest.MonkeyPatch):
    set_production_config(monkeypatch, SESSION_SECRET_KEY="short")

    with pytest.raises(ValueError, match="SESSION_SECRET_KEY"):
        Settings.from_env()


def test_production_rejects_local_development_api_key(monkeypatch: pytest.MonkeyPatch):
    set_production_config(monkeypatch, API_KEYS="local-dev-token:admin")

    with pytest.raises(ValueError, match="local development token"):
        Settings.from_env()


def test_local_config_still_uses_safe_defaults(monkeypatch: pytest.MonkeyPatch):
    clear_config_env(monkeypatch)

    settings = Settings.from_env()

    assert settings.environment == "local"
    assert settings.session_cookie_secret == "local-session-secret-change-me"
    assert settings.secure_cookies is False
    assert settings.cors_allowed_origin_regex is not None


def test_session_cookie_secret_alias_still_works(monkeypatch: pytest.MonkeyPatch):
    set_production_config(monkeypatch)
    monkeypatch.delenv("SESSION_SECRET_KEY")
    monkeypatch.setenv("SESSION_COOKIE_SECRET", "y" * 32)

    settings = Settings.from_env()

    assert settings.session_cookie_secret == "y" * 32


@pytest.mark.asyncio
async def test_auth_me_returns_service_principal_for_api_key(client: AsyncClient):
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer local-dev-token"})

    assert response.status_code == 200
    assert response.json() == {
        "actor_type": "service",
        "subject": "api-key",
        "user_id": None,
        "role": "admin",
        "display_name": None,
        "email": None,
        "is_active": None,
    }


@pytest.mark.asyncio
async def test_auth_login_redirects_to_oidc_provider(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth_routes, "get_settings", oidc_test_settings)
    monkeypatch.setattr(oidc_service, "get_oidc_client", lambda settings: FakeOidcClient())

    response = await client.get("/api/v1/auth/login", follow_redirects=False)

    assert response.status_code in {302, 307}
    assert response.headers["location"] == "https://idp.example/authorize?state=fake-state"


@pytest.mark.asyncio
async def test_auth_callback_creates_user_session_cookie_and_readonly_role(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = oidc_test_settings()
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(
        oidc_service,
        "get_oidc_client",
        lambda configured_settings: FakeOidcClient(
            {
                "sub": "oidc|new-user",
                "email": "New.User@Example.com",
                "name": "New User",
            }
        ),
    )

    response = await client.get("/api/v1/auth/callback?code=fake&state=fake", follow_redirects=False)

    assert response.status_code in {302, 307}
    assert response.headers["location"] == "http://localhost:5173"
    set_cookie = response.headers["set-cookie"]
    assert settings.session_cookie_name in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Secure" not in set_cookie

    session_token = response.cookies[settings.session_cookie_name]
    me_response = await client.get("/api/v1/auth/me", cookies={settings.session_cookie_name: session_token})

    assert me_response.status_code == 200
    assert me_response.json() == {
        "actor_type": "user",
        "subject": "oidc|new-user",
        "user_id": me_response.json()["user_id"],
        "role": "readonly",
        "display_name": "New User",
        "email": "new.user@example.com",
        "is_active": True,
    }


@pytest.mark.asyncio
async def test_auth_callback_updates_existing_user_without_changing_role(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = oidc_test_settings()
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(
        oidc_service,
        "get_oidc_client",
        lambda configured_settings: FakeOidcClient(
            {
                "sub": "oidc|existing",
                "email": "updated@example.com",
                "name": "Updated Name",
            }
        ),
    )

    async for session in app.dependency_overrides[get_db_session]():
        user = User(
            oidc_subject="oidc|existing",
            email="old@example.com",
            display_name="Old Name",
            role="responder",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        await session.commit()
        break

    response = await client.get("/api/v1/auth/callback?code=fake&state=fake", follow_redirects=False)

    assert response.status_code in {302, 307}
    session_token = response.cookies[settings.session_cookie_name]
    me_response = await client.get("/api/v1/auth/me", cookies={settings.session_cookie_name: session_token})
    assert me_response.json()["role"] == "responder"
    assert me_response.json()["email"] == "updated@example.com"
    assert me_response.json()["display_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_auth_callback_rejects_invalid_state(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = oidc_test_settings()
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(
        oidc_service,
        "get_oidc_client",
        lambda configured_settings: FakeOidcClient(callback_error=True),
    )

    response = await client.get("/api/v1/auth/callback?code=fake&state=bad")

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "OIDC callback validation failed"
    assert settings.session_cookie_name not in response.cookies


@pytest.mark.asyncio
async def test_auth_callback_rejects_missing_or_invalid_id_token(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = oidc_test_settings()
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(
        oidc_service,
        "get_oidc_client",
        lambda configured_settings: FakeOidcClient(include_id_token=False),
    )

    missing_id_token = await client.get("/api/v1/auth/callback?code=fake&state=fake")

    assert missing_id_token.status_code == 401
    assert missing_id_token.json()["error"]["message"] == "OIDC provider did not return an ID token"

    monkeypatch.setattr(
        oidc_service,
        "get_oidc_client",
        lambda configured_settings: FakeOidcClient(id_token_error=True),
    )
    invalid_id_token = await client.get("/api/v1/auth/callback?code=fake&state=fake")

    assert invalid_id_token.status_code == 401
    assert invalid_id_token.json()["error"]["message"] == "OIDC ID token validation failed"


@pytest.mark.asyncio
async def test_auth_callback_rejects_inactive_user(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = oidc_test_settings()
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(
        oidc_service,
        "get_oidc_client",
        lambda configured_settings: FakeOidcClient(
            {
                "sub": "oidc|inactive-callback",
                "email": "inactive-callback@example.com",
            }
        ),
    )

    async for session in app.dependency_overrides[get_db_session]():
        user = User(
            oidc_subject="oidc|inactive-callback",
            email="inactive-callback@example.com",
            role="readonly",
            is_active=False,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        await session.commit()
        break

    response = await client.get("/api/v1/auth/callback?code=fake&state=fake")

    assert response.status_code == 403
    assert response.json()["error"]["message"] == "User is inactive"
    assert settings.session_cookie_name not in response.cookies


@pytest.mark.asyncio
async def test_auth_callback_rejects_missing_subject_or_email(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = oidc_test_settings()
    monkeypatch.setattr(auth_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(
        oidc_service,
        "get_oidc_client",
        lambda configured_settings: FakeOidcClient({"email": "missing-subject@example.com"}),
    )

    missing_subject = await client.get("/api/v1/auth/callback?code=fake&state=fake")
    assert missing_subject.status_code == 401
    assert missing_subject.json()["error"]["message"] == "OIDC subject is required"

    monkeypatch.setattr(
        oidc_service,
        "get_oidc_client",
        lambda configured_settings: FakeOidcClient({"sub": "oidc|missing-email"}),
    )
    missing_email = await client.get("/api/v1/auth/callback?code=fake&state=fake")

    assert missing_email.status_code == 401
    assert missing_email.json()["error"]["message"] == "OIDC email is required"


@pytest.mark.asyncio
async def test_legacy_unversioned_routes_are_not_mounted(client: AsyncClient):
    response = await client.get("/incidents/")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reporter_names_are_normalized_for_duplicates(client: AsyncClient):
    headers = {"Authorization": "Bearer local-dev-token"}

    first = await client.post("/api/v1/reporters/", headers=headers, json={"name": "Ada Lovelace"})
    second = await client.post("/api/v1/reporters/", headers=headers, json={"name": "  ada   lovelace  "})

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["name"] == "Ada Lovelace"


@pytest.mark.asyncio
async def test_incident_workflow_is_paginated_and_filterable(client: AsyncClient):
    headers = {"Authorization": "Bearer local-dev-token"}

    reporter_response = await client.post(
        "/api/v1/reporters/",
        headers=headers,
        json={"name": "Ada Lovelace"},
    )
    assert reporter_response.status_code == 201

    create_response = await client.post(
        "/api/v1/incidents/",
        headers=headers,
        json={
            "title": "Payment gateway latency",
            "created_by": "Ada Lovelace",
            "severity": "critical",
            "description": "Checkout is slow",
        },
    )
    assert create_response.status_code == 201
    incident = create_response.json()
    assert incident["reporter_id"] == reporter_response.json()["id"]

    list_response = await client.get("/api/v1/incidents/?severity=critical&limit=10&offset=0")
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["pagination"] == {"limit": 10, "offset": 0, "total": 1}
    assert body["items"][0]["title"] == "Payment gateway latency"

    update_response = await client.post(
        f"/api/v1/incidents/{incident['id']}/updates",
        headers=headers,
        json={"message": "Mitigation started"},
    )
    assert update_response.status_code == 201

    resolve_response = await client.patch(f"/api/v1/incidents/{incident['id']}/resolve", headers=headers)
    assert resolve_response.status_code == 200
    assert resolve_response.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_invalid_incident_filters_return_validation_error(client: AsyncClient):
    response = await client.get("/api/v1/incidents/?severity=urgent")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_session_token_is_hashed_and_auth_me_returns_user(client: AsyncClient):
    settings = get_settings()

    async for session in app.dependency_overrides[get_db_session]():
        user = User(
            oidc_subject="oidc|ada",
            email="ada@example.com",
            display_name="Ada Lovelace",
            role="responder",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token, user_session = await create_session(session, user, settings)
        break

    assert user_session.session_token_hash != token
    assert user_session.session_token_hash == hash_session_token(token, settings)

    response = await client.get("/api/v1/auth/me", cookies={settings.session_cookie_name: token})

    assert response.status_code == 200
    assert response.json() == {
        "actor_type": "user",
        "subject": "oidc|ada",
        "user_id": response.json()["user_id"],
        "role": "responder",
        "display_name": "Ada Lovelace",
        "email": "ada@example.com",
        "is_active": True,
    }


@pytest.mark.asyncio
async def test_session_role_authorizes_existing_role_dependencies(client: AsyncClient):
    settings = get_settings()

    async for session in app.dependency_overrides[get_db_session]():
        user = User(
            oidc_subject="oidc|reporter",
            email="reporter@example.com",
            role="reporter",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token, _ = await create_session(session, user, settings)
        break

    csrf_response = await client.get("/api/v1/auth/csrf", cookies={settings.session_cookie_name: token})
    csrf_token = csrf_response.json()["csrf_token"]
    create_response = await client.post(
        "/api/v1/reporters/",
        cookies={settings.session_cookie_name: token},
        headers={"X-CSRF-Token": csrf_token},
        json={"name": "Session Reporter"},
    )
    update_response = await client.post(
        "/api/v1/incidents/1/updates",
        cookies={settings.session_cookie_name: token},
        headers={"X-CSRF-Token": csrf_token},
        json={"message": "not allowed"},
    )

    assert create_response.status_code == 201
    assert update_response.status_code == 403


@pytest.mark.asyncio
async def test_session_auth_post_requires_csrf(client: AsyncClient):
    settings = get_settings()

    async for session in app.dependency_overrides[get_db_session]():
        user = User(
            oidc_subject="oidc|csrf-required",
            email="csrf-required@example.com",
            role="reporter",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token, _ = await create_session(session, user, settings)
        break

    response = await client.post(
        "/api/v1/reporters/",
        cookies={settings.session_cookie_name: token},
        json={"name": "No Csrf"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["message"] == "Invalid CSRF token"


@pytest.mark.asyncio
async def test_session_auth_post_with_csrf_succeeds_and_token_is_hashed(client: AsyncClient):
    settings = get_settings()

    async for session in app.dependency_overrides[get_db_session]():
        user = User(
            oidc_subject="oidc|csrf-valid",
            email="csrf-valid@example.com",
            role="reporter",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token, user_session = await create_session(session, user, settings)
        session_id = user_session.id
        break

    csrf_response = await client.get("/api/v1/auth/csrf", cookies={settings.session_cookie_name: token})
    csrf_token = csrf_response.json()["csrf_token"]

    assert csrf_response.status_code == 200
    async for session in app.dependency_overrides[get_db_session]():
        stored = await session.get(UserSession, session_id)
        assert stored is not None
        assert stored.csrf_token_hash != csrf_token
        assert stored.csrf_token_hash == hash_csrf_token(csrf_token, settings)
        break

    response = await client.post(
        "/api/v1/reporters/",
        cookies={settings.session_cookie_name: token},
        headers={"X-CSRF-Token": csrf_token},
        json={"name": "With Csrf"},
    )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_invalid_csrf_fails(client: AsyncClient):
    settings = get_settings()

    async for session in app.dependency_overrides[get_db_session]():
        user = User(
            oidc_subject="oidc|csrf-invalid",
            email="csrf-invalid@example.com",
            role="reporter",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token, _ = await create_session(session, user, settings)
        break

    await client.get("/api/v1/auth/csrf", cookies={settings.session_cookie_name: token})
    response = await client.post(
        "/api/v1/reporters/",
        cookies={settings.session_cookie_name: token},
        headers={"X-CSRF-Token": "wrong-token"},
        json={"name": "Bad Csrf"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["message"] == "Invalid CSRF token"


@pytest.mark.asyncio
async def test_get_requests_do_not_require_csrf(client: AsyncClient):
    settings = get_settings()

    async for session in app.dependency_overrides[get_db_session]():
        user = User(
            oidc_subject="oidc|csrf-get",
            email="csrf-get@example.com",
            role="readonly",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token, _ = await create_session(session, user, settings)
        break

    response = await client.get("/api/v1/auth/me", cookies={settings.session_cookie_name: token})

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_expired_session_fails(client: AsyncClient):
    settings = get_settings()

    async for session in app.dependency_overrides[get_db_session]():
        user = User(
            oidc_subject="oidc|expired",
            email="expired@example.com",
            role="readonly",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token, user_session = await create_session(session, user, settings)
        user_session.expires_at = utc_now().replace(year=2000)
        await session.commit()
        break

    response = await client.get("/api/v1/auth/me", cookies={settings.session_cookie_name: token})

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Missing API key"


@pytest.mark.asyncio
async def test_inactive_user_session_fails(client: AsyncClient):
    settings = get_settings()

    async for session in app.dependency_overrides[get_db_session]():
        user = User(
            oidc_subject="oidc|inactive",
            email="inactive@example.com",
            role="readonly",
            is_active=False,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token, _ = await create_session(session, user, settings)
        break

    response = await client.get("/api/v1/auth/me", cookies={settings.session_cookie_name: token})

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Missing API key"


@pytest.mark.asyncio
async def test_revoked_session_fails(client: AsyncClient):
    settings = get_settings()

    async for session in app.dependency_overrides[get_db_session]():
        user = User(
            oidc_subject="oidc|revoked",
            email="revoked@example.com",
            role="readonly",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token, user_session = await create_session(session, user, settings)
        user_session.revoked_at = utc_now()
        await session.commit()
        break

    response = await client.get("/api/v1/auth/me", cookies={settings.session_cookie_name: token})

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Missing API key"


@pytest.mark.asyncio
async def test_logout_revokes_session(client: AsyncClient):
    settings = get_settings()

    async for session in app.dependency_overrides[get_db_session]():
        user = User(
            oidc_subject="oidc|logout",
            email="logout@example.com",
            role="readonly",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token, user_session = await create_session(session, user, settings)
        session_id = user_session.id
        break

    csrf_response = await client.get("/api/v1/auth/csrf", cookies={settings.session_cookie_name: token})
    csrf_token = csrf_response.json()["csrf_token"]
    response = await client.post(
        "/api/v1/auth/logout",
        cookies={settings.session_cookie_name: token},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 204
    assert settings.session_cookie_name in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]

    async for session in app.dependency_overrides[get_db_session]():
        stored = await session.get(UserSession, session_id)
        assert stored is not None
        assert stored.revoked_at is not None
        assert stored.csrf_token_hash is None
        assert await get_valid_session(session, token, settings, update_last_seen=False) is None
        break


@pytest.mark.asyncio
async def test_logout_without_csrf_fails_and_does_not_revoke_session(client: AsyncClient):
    settings = get_settings()

    async for session in app.dependency_overrides[get_db_session]():
        user = User(
            oidc_subject="oidc|logout-no-csrf",
            email="logout-no-csrf@example.com",
            role="readonly",
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token, user_session = await create_session(session, user, settings)
        session_id = user_session.id
        break

    response = await client.post("/api/v1/auth/logout", cookies={settings.session_cookie_name: token})

    assert response.status_code == 403
    async for session in app.dependency_overrides[get_db_session]():
        stored = await session.get(UserSession, session_id)
        assert stored is not None
        assert stored.revoked_at is None
        break
