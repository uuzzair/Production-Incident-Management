# Incident Reporting Backend

Production-oriented FastAPI backend using async SQLAlchemy, Alembic migrations, a repository layer, a service layer, and JSON structured request logging.

## Local setup

```powershell
cd C:\OfficeWork\Python-Scripts\fastapi_incidents\backend
..\venv\Scripts\python.exe -m pip install -r requirements.txt
..\venv\Scripts\python.exe -m alembic upgrade head
..\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

For local API smoke tests, install the dev requirements:

```powershell
..\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Configuration

Environment variables:

- `DATABASE_URL`: async SQLAlchemy URL. By default, the app uses the absolute path `backend/data/incidents.db`, regardless of the shell folder you start Uvicorn from.
- `CORS_ALLOWED_ORIGINS`: comma-separated frontend origins
- `CORS_ALLOWED_ORIGIN_REGEX`: optional regex for local Vite ports
- `CORS_ALLOW_CREDENTIALS`: set to `true` only when using cookie/session auth
- `API_KEYS`: comma-separated `token:role` entries. Roles are `admin`, `responder`, `reporter`, and `readonly`.
- `MAX_PAGE_LIMIT`: maximum accepted incident page size
- `LOG_LEVEL`: default `INFO`
- `ENVIRONMENT`: default `local`
- `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI`: required in production for browser user authentication. The backend login/callback flow is implemented and the frontend calls it.
- `OIDC_AUTHORIZATION_URL`: optional authorization endpoint override. This is mainly useful for local Docker, where the backend fetches OIDC metadata through a container-reachable URL but the browser must be redirected to `127.0.0.1`.
- `OIDC_BACKCHANNEL_ISSUER_URL`: optional local Docker backchannel realm URL for token and JWKS calls. Keep `OIDC_ISSUER_URL` as the public issuer that appears in ID tokens.
- `SESSION_COOKIE_NAME`, `SESSION_SECRET_KEY`, `SESSION_EXPIRY_HOURS`: backend session-cookie settings. `SESSION_SECRET_KEY` must be explicitly set to a strong value in production. `SESSION_COOKIE_SECRET` remains a backward-compatible alias.
- `CSRF_COOKIE_NAME`: reserved for the next auth phase.
- `SECURE_COOKIES`: defaults to `false` locally and must be `true` in production.
- `AUTH_SUCCESS_REDIRECT_URL`: frontend URL to redirect to after successful OIDC login; must be HTTPS and non-local outside local/dev/test.

Production-like environments are any `ENVIRONMENT` value outside `local`, `dev`, `development`, and `test`. They fail fast unless OIDC settings, explicit HTTPS CORS origins, non-local HTTPS redirect URLs, non-SQLite `DATABASE_URL`, strong session secret, secure cookies, and non-local API keys are configured.

## Local Keycloak

The root `docker-compose.yml` includes a local-only Keycloak service for end-to-end OIDC validation. It imports `keycloak/realms/incidents-local-realm.json`.

Safe development credentials:

- Admin console: `http://127.0.0.1:8082/admin`
- Admin user/password: `admin` / `admin`
- Realm: `incidents-local`
- Client ID/secret: `fastapi-incidents` / `local-keycloak-secret`
- Test user/password: `readonly` / `readonly`

When the backend runs inside Compose, use:

```env
OIDC_ISSUER_URL=http://127.0.0.1:8082/realms/incidents-local
OIDC_BACKCHANNEL_ISSUER_URL=http://host.docker.internal:8082/realms/incidents-local
OIDC_CLIENT_ID=fastapi-incidents
OIDC_CLIENT_SECRET=local-keycloak-secret
OIDC_REDIRECT_URI=http://127.0.0.1:8001/api/v1/auth/callback
OIDC_AUTHORIZATION_URL=http://127.0.0.1:8082/realms/incidents-local/protocol/openid-connect/auth
AUTH_SUCCESS_REDIRECT_URL=http://127.0.0.1:8080
SESSION_SECRET_KEY=local-compose-session-secret-change-me
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080
CORS_ALLOW_CREDENTIALS=true
SECURE_COOKIES=false
```

When the backend runs directly on your host and only Keycloak runs in Docker, use `OIDC_ISSUER_URL=http://localhost:8082/realms/incidents-local` and leave `OIDC_BACKCHANNEL_ISSUER_URL` empty.

## API

- `GET /health`
- `GET /ready`
- `GET /api/v1/auth/login`
- `GET /api/v1/auth/callback`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/csrf`
- `POST /api/v1/auth/logout`
- `POST /api/v1/incidents/`
- `GET /api/v1/incidents/?status=open&severity=critical&limit=50&offset=0`
- `GET /api/v1/incidents/{incident_id}`
- `POST /api/v1/incidents/{incident_id}/updates`
- `PATCH /api/v1/incidents/{incident_id}/resolve`
- `GET /api/v1/reporters/`
- `POST /api/v1/reporters/`

Write endpoints require `Authorization: Bearer <token>`, `X-API-Key: <token>`, or a valid backend session cookie. Browser session writes must also send `X-CSRF-Token`; API-key auth remains for service automation only.
