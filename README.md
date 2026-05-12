# FastAPI Incidents

Incident reporting application split into separate production-oriented folders:

- `backend/`: FastAPI API with async SQLAlchemy, Alembic migrations, repositories, services, and structured JSON logging.
- `frontend/`: Vue 3 + Vite incident reporting console.

## Backend

From the project root:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8001
```

Or from inside `backend/`:

```powershell
cd C:\OfficeWork\Python-Scripts\fastapi_incidents\backend
..\venv\Scripts\python.exe -m pip install -r requirements.txt
..\venv\Scripts\python.exe -m alembic upgrade head
..\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

Local service automation can still use an API key. The default local key is `local-dev-token`; send it as `Authorization: Bearer local-dev-token` or `X-API-Key: local-dev-token`.

## Frontend

```powershell
cd C:\OfficeWork\Python-Scripts\fastapi_incidents\frontend
npm install
npm run dev
```

The frontend reads `VITE_API_URL` from `frontend/.env.local`. For local development, use:

```powershell
VITE_API_URL=http://127.0.0.1:8000/api/v1
```

The frontend never reads or embeds API tokens. Browser login redirects to the backend `/api/v1/auth/login` endpoint and uses the backend session cookie after OIDC login completes.

## Docker

```powershell
docker compose up --build
```

This local compose file starts PostgreSQL, runs backend migrations, serves the API on `http://127.0.0.1:8001`, and serves the frontend on `http://127.0.0.1:8080`.
The containerized frontend is built without any browser-embedded API token. Write actions use backend session cookies after OIDC login and include a session-bound CSRF token.

For staging/production, provide OIDC, database, CORS, API key, and `SESSION_SECRET_KEY` values through deployment environment variables or a secret manager. Do not commit real secrets to this repository.

Required staging/production backend environment shape:

```env
ENVIRONMENT=staging
DATABASE_URL=postgresql+asyncpg://<user>:<redacted>@<host>:5432/<db>
CORS_ALLOWED_ORIGINS=https://<frontend-host>
CORS_ALLOW_CREDENTIALS=true
API_KEYS=<redacted-service-token>:admin
OIDC_ISSUER_URL=https://<issuer-host>
OIDC_CLIENT_ID=<redacted-client-id>
OIDC_CLIENT_SECRET=<redacted-client-secret>
OIDC_REDIRECT_URI=https://<backend-host>/api/v1/auth/callback
AUTH_SUCCESS_REDIRECT_URL=https://<frontend-host>
SESSION_SECRET_KEY=<redacted-strong-random-secret>
SECURE_COOKIES=true
```

## Notes

The previous root-level FastAPI modules were removed from active use. Some old local artifacts such as SQLite files, logs, `configs/`, `routes/`, and `__pycache__/` may remain if Windows has them locked or permission-protected; the production app entrypoint is now `backend/app/main.py`.
