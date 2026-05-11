import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.core.config import Settings, get_settings
from app.models import Incident, IncidentUpdate, Reporter, User, UserSession  # noqa: F401
from app.services.sessions import create_session, get_valid_session, hash_session_token, utc_now


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
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/incidents")
    monkeypatch.setenv("API_KEYS", "service-token:admin")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://incidents.example.com")

    with pytest.raises(ValueError, match="Production auth settings missing"):
        Settings.from_env()


@pytest.mark.asyncio
async def test_auth_me_returns_service_principal_for_api_key(client: AsyncClient):
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer local-dev-token"})

    assert response.status_code == 200
    assert response.json() == {
        "actor_type": "service",
        "subject": "api-key",
        "role": "admin",
        "display_name": None,
        "email": None,
    }


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
        "role": "responder",
        "display_name": "Ada Lovelace",
        "email": "ada@example.com",
    }


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

    response = await client.post("/api/v1/auth/logout", cookies={settings.session_cookie_name: token})

    assert response.status_code == 204

    async for session in app.dependency_overrides[get_db_session]():
        stored = await session.get(UserSession, session_id)
        assert stored is not None
        assert stored.revoked_at is not None
        assert await get_valid_session(session, token, settings, update_last_seen=False) is None
        break
